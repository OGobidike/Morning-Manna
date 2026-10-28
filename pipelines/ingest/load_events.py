

"""Load events from the lake into the warehouse: one day's files become rows in raw.events.

Run from anywhere (with the lake and Postgres running):
    python -m ingest.load_events --date 2026-10-27     # one day
    python -m ingest.load_events --all                 # every day in the lake

Loading a day again replaces that day, so re-runs never count anything twice. Lines that
can't be used are rejected and counted, never loaded. Every run is logged in raw.load_runs.
"""

import argparse
import json
from datetime import date, datetime

import psycopg
from psycopg import sql

from ingest.settings import database_url, lake_bucket, lake_client

# The event types the API accepts (backend/app/schemas.py)
EVENT_TYPES = {
    "app_opened",
    "notification_opened",
    "reading_opened",
    "reading_completed",
    "reminder_snoozed",
}
FIELDS = ("event_id", "user_key", "event_type", "occurred_at", "received_at", "source")

# The warehouse's raw layer: the lake's lines as rows, nothing cleaned or changed yet
TABLES = """
create schema if not exists {schema};

create table if not exists {schema}.events (
    event_id    text primary key,
    user_key    text not null,
    event_type  text not null,
    occurred_at timestamptz not null,
    received_at timestamptz not null,
    properties  jsonb not null,
    source      text not null,
    dt          date not null,          -- the lake folder it came from (the day it arrived)
    file_key    text not null,          -- the exact file, to trace any row back to the lake
    loaded_at   timestamptz not null default now()
);
create index if not exists events_dt on {schema}.events (dt);

create table if not exists {schema}.readers (
    user_key     text primary key,
    persona      text,
    timezone     text not null,
    wake_time    text not null,
    signed_up_on date not null,
    reminders_on boolean not null,
    source       text not null,
    loaded_at    timestamptz not null default now()
);

create table if not exists {schema}.load_runs (
    id            serial primary key,
    pipeline      text not null,
    status        text not null,        -- running, then success or failed
    started_at    timestamptz not null default now(),
    finished_at   timestamptz,
    rows_read     integer not null default 0,
    rows_loaded   integer not null default 0,
    rows_rejected integer not null default 0,
    error         text
);
"""


def create_tables(conn, schema: str) -> None:
    """Make the raw schema and its tables, if they don't exist yet."""
    conn.execute(sql.SQL(TABLES).format(schema=sql.Identifier(schema)))


def parse_line(line: str, dt: date, key: str) -> tuple | None:
    """One lake line as a row for raw.events, or None if it can't be used."""
    try:
        event = json.loads(line)
        if not all(isinstance(event.get(field), str) for field in FIELDS):
            return None  # a field is missing, or isn't text
        if event["event_type"] not in EVENT_TYPES:
            return None
        occurred = datetime.fromisoformat(event["occurred_at"])
        received = datetime.fromisoformat(event["received_at"])
        if occurred.tzinfo is None or received.tzinfo is None:
            return None  # a time with no time zone is ambiguous
        properties = event.get("properties", {})
        if not isinstance(properties, dict):
            return None
    except (json.JSONDecodeError, ValueError, AttributeError):
        return None  # not JSON, not an object, or a time that isn't a time
    return (
        event["event_id"],
        event["user_key"],
        event["event_type"],
        occurred,
        received,
        json.dumps(properties),
        event["source"],
        dt,
        key,
    )


def read_day(client, bucket: str, dt: date) -> tuple[list[tuple], int, int]:
    """Every usable row in one day's folder, plus how many lines were read and rejected."""
    rows, seen, read, rejected = [], set(), 0, 0
    prefix = f"events/dt={dt.isoformat()}/"
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            if not item["Key"].endswith(".jsonl"):
                continue
            body = client.get_object(Bucket=bucket, Key=item["Key"])["Body"].read().decode()
            for line in body.splitlines():
                if not line.strip():
                    continue
                read += 1
                row = parse_line(line, dt, item["Key"])
                # The same event twice (e.g. a file copied twice) is only loaded once
                if row is None or row[0] in seen:
                    rejected += 1
                    continue
                seen.add(row[0])
                rows.append(row)
    return rows, read, rejected


def load_day(conn, schema: str, dt: date, rows: list[tuple]) -> None:
    """Replace one day in raw.events with these rows, all in one transaction."""
    table = sql.Identifier(schema, "events")
    with conn.transaction():
        conn.execute(sql.SQL("delete from {} where dt = %s").format(table), [dt])
        copy = sql.SQL(
            "copy {} (event_id, user_key, event_type, occurred_at, received_at, properties,"
            " source, dt, file_key) from stdin"
        ).format(table)
        with conn.cursor().copy(copy) as writer:
            for row in rows:
                writer.write_row(row)


def load_readers(conn, schema: str, client, bucket: str) -> int:
    """Copy the pretend readers' file into raw.readers. Loading again updates, never doubles."""
    try:
        body = client.get_object(Bucket=bucket, Key="readers/synthetic.jsonl")["Body"].read()
    except client.exceptions.NoSuchKey:
        return 0
    readers = [json.loads(line) for line in body.decode().splitlines() if line.strip()]
    query = sql.SQL(
        "insert into {} (user_key, persona, timezone, wake_time, signed_up_on, reminders_on,"
        " source) values (%(user_key)s, %(persona)s, %(timezone)s, %(wake_time)s,"
        " %(signed_up_on)s, %(reminders_on)s, %(source)s)"
        " on conflict (user_key) do update set persona = excluded.persona,"
        " timezone = excluded.timezone, wake_time = excluded.wake_time,"
        " signed_up_on = excluded.signed_up_on, reminders_on = excluded.reminders_on,"
        " source = excluded.source, loaded_at = now()"
    ).format(sql.Identifier(schema, "readers"))
    with conn.transaction():
        conn.cursor().executemany(query, readers)
    return len(readers)


def lake_days(client, bucket: str) -> list[date]:
    """Every day that has a folder in the lake, oldest first."""
    days = []
    pages = client.get_paginator("list_objects_v2").paginate(
        Bucket=bucket, Prefix="events/", Delimiter="/"
    )
    for page in pages:
        for folder in page.get("CommonPrefixes", []):
            name = folder["Prefix"].removeprefix("events/").strip("/")
            if name.startswith("dt="):
                days.append(date.fromisoformat(name.removeprefix("dt=")))
    return sorted(days)


def run(days: list[date] | None = None, schema: str = "raw") -> dict:
    """Load the given days (or every day in the lake), and log the run in raw.load_runs."""
    client, bucket = lake_client(), lake_bucket()
    runs = sql.Identifier(schema, "load_runs")
    with psycopg.connect(database_url(), autocommit=True) as conn:
        create_tables(conn, schema)
        # Log the start straight away, so even a crash leaves a trace
        run_id = conn.execute(
            sql.SQL("insert into {} (pipeline, status) values ('lake_events', 'running')"
                    " returning id").format(runs)
        ).fetchone()[0]

        totals = {"days": 0, "read": 0, "loaded": 0, "rejected": 0, "readers": 0}
        status, error = "failed", None
        try:
            for dt in days if days is not None else lake_days(client, bucket):
                rows, read, rejected = read_day(client, bucket, dt)
                load_day(conn, schema, dt, rows)
                totals["days"] += 1
                totals["read"] += read
                totals["loaded"] += len(rows)
                totals["rejected"] += rejected
            totals["readers"] = load_readers(conn, schema, client, bucket)
            status = "success"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise  # fail loudly: the error still stops the job
        finally:
            conn.execute(
                sql.SQL(
                    "update {} set status = %s, finished_at = now(), rows_read = %s,"
                    " rows_loaded = %s, rows_rejected = %s, error = %s where id = %s"
                ).format(runs),
                [status, totals["read"], totals["loaded"], totals["rejected"], error, run_id],
            )
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description="Load events from the lake into raw.events.")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--date", type=date.fromisoformat, help="one day, e.g. 2026-10-27")
    which.add_argument("--all", action="store_true", help="every day in the lake")
    parser.add_argument("--schema", default="raw")
    args = parser.parse_args()

    totals = run(None if args.all else [args.date], args.schema)
    print(
        f"{totals['days']} days: read {totals['read']:,}, loaded {totals['loaded']:,}, "
        f"rejected {totals['rejected']:,}; {totals['readers']:,} readers"
    )


if __name__ == "__main__":
    main()
