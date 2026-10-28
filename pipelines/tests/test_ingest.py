

"""Tests for the lake-to-warehouse jobs, against a real local S3 server and a real Postgres."""

import json
import os
import socket
from datetime import date

import psycopg
import pytest
from botocore.exceptions import ClientError
from moto.server import ThreadedMotoServer
from psycopg import sql

from ingest import load_events, upload
from ingest.settings import database_url, lake_bucket, lake_client

DAY = date(2026, 10, 27)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module", autouse=True)
def s3_server():
    """moto's S3 server on this machine, standing in for SeaweedFS."""
    port = free_port()
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=port)
    server.start()
    os.environ["LAKE_URL"] = f"http://127.0.0.1:{port}"
    yield
    server.stop()


@pytest.fixture
def lake(monkeypatch):
    """An empty bucket of its own for each test."""
    monkeypatch.setenv("LAKE_BUCKET", f"test-lake-{free_port()}")
    client = lake_client()
    client.create_bucket(Bucket=lake_bucket())
    return client


@pytest.fixture
def schema():
    """A schema of its own for each test, dropped afterwards, so tests never touch raw."""
    name = f"raw_test_{free_port()}"
    yield name
    with psycopg.connect(database_url(), autocommit=True) as conn:
        conn.execute(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(name)))


def line(event_id, event_type="app_opened", **changes) -> str:
    event = {
        "event_id": event_id,
        "user_key": "sim:00001",
        "event_type": event_type,
        "occurred_at": "2026-10-27T05:31:12Z",
        "received_at": "2026-10-27T05:31:14Z",
        "properties": {},
        "source": "synthetic",
    }
    event.update(changes)
    return json.dumps(event)


def put(client, key, *lines):
    client.put_object(Bucket=lake_bucket(), Key=key, Body="\n".join(lines) + "\n")


def query(schema, text, *args):
    with psycopg.connect(database_url()) as conn:
        return conn.execute(sql.SQL(text).format(s=sql.Identifier(schema)), args).fetchall()


def test_a_day_of_files_becomes_rows(lake, schema):
    put(lake, "events/dt=2026-10-27/synthetic.jsonl", line("sim-1"), line("sim-2"))
    put(lake, "events/dt=2026-10-27/app-abc.jsonl",
        line("app-7", "reminder_snoozed", user_key="app:3", source="app",
             properties={"minutes": 10}))

    totals = load_events.run([DAY], schema)

    assert totals == {"days": 1, "read": 3, "loaded": 3, "rejected": 0, "readers": 0}
    rows = query(schema, "select event_id, source, properties, dt from {s}.events order by 1")
    assert rows[0] == ("app-7", "app", {"minutes": 10}, DAY)
    assert [r[0] for r in rows] == ["app-7", "sim-1", "sim-2"]


def test_times_keep_their_time_zone(lake, schema):
    put(lake, "events/dt=2026-10-27/a.jsonl", line("e1", occurred_at="2026-10-27T06:31:12+01:00"))
    load_events.run([DAY], schema)
    (occurred,) = query(schema, "select occurred_at from {s}.events")[0]
    assert occurred.isoformat().startswith("2026-10-27T05:31:12")  # the same moment, in UTC


def test_loading_a_day_again_replaces_it(lake, schema):
    put(lake, "events/dt=2026-10-27/a.jsonl", line("e1"), line("e2"))
    load_events.run([DAY], schema)
    load_events.run([DAY], schema)
    assert query(schema, "select count(*) from {s}.events") == [(2,)]


def test_a_day_mirrors_the_lake_when_files_change(lake, schema):
    put(lake, "events/dt=2026-10-27/a.jsonl", line("e1"), line("e2"))
    load_events.run([DAY], schema)
    put(lake, "events/dt=2026-10-27/a.jsonl", line("e1"))  # the file now holds one event
    load_events.run([DAY], schema)
    assert query(schema, "select event_id from {s}.events") == [("e1",)]


def test_other_days_are_left_alone(lake, schema):
    put(lake, "events/dt=2026-10-26/a.jsonl", line("old"))
    put(lake, "events/dt=2026-10-27/a.jsonl", line("new"))
    load_events.run([date(2026, 10, 26), DAY], schema)
    load_events.run([DAY], schema)
    assert query(schema, "select event_id from {s}.events order by 1") == [("new",), ("old",)]


def test_unusable_lines_are_rejected_and_counted(lake, schema):
    put(
        lake,
        "events/dt=2026-10-27/a.jsonl",
        line("good"),
        "this is not json",
        line("odd-type", "app_crashed"),
        line("no-zone", occurred_at="2026-10-27T05:31:12"),
        line("bad-time", occurred_at="yesterday"),
        json.dumps({"event_id": "missing-fields"}),
        line("good"),  # the same event twice is loaded once
    )
    totals = load_events.run([DAY], schema)
    assert (totals["read"], totals["loaded"], totals["rejected"]) == (7, 1, 6)
    assert query(schema, "select event_id from {s}.events") == [("good",)]


def test_all_finds_every_day_in_the_lake(lake, schema):
    for day in ("2026-10-25", "2026-10-26", "2026-10-27"):
        put(lake, f"events/dt={day}/a.jsonl", line(f"e-{day}"))
    assert load_events.lake_days(lake, lake_bucket()) == [
        date(2026, 10, 25), date(2026, 10, 26), date(2026, 10, 27)
    ]
    assert load_events.run(None, schema)["days"] == 3


def test_readers_are_loaded_and_updated_not_doubled(lake, schema):
    reader = {"user_key": "sim:00001", "persona": "commuter", "timezone": "Africa/Lagos",
              "wake_time": "06:30", "signed_up_on": "2026-08-01", "reminders_on": True,
              "source": "synthetic"}
    put(lake, "readers/synthetic.jsonl", json.dumps(reader))
    assert load_events.run([], schema)["readers"] == 1
    put(lake, "readers/synthetic.jsonl", json.dumps(reader | {"persona": "early_riser"}))
    load_events.run([], schema)
    assert query(schema, "select user_key, persona from {s}.readers") == [
        ("sim:00001", "early_riser")
    ]


def test_every_run_is_logged(lake, schema):
    put(lake, "events/dt=2026-10-27/a.jsonl", line("e1"), "broken")
    load_events.run([DAY], schema)
    runs = query(schema, "select pipeline, status, rows_read, rows_loaded, rows_rejected,"
                         " finished_at is not null, error from {s}.load_runs")
    assert runs == [("lake_events", "success", 2, 1, 1, True, None)]


def test_a_failed_run_is_logged_and_still_fails(lake, schema, monkeypatch):
    def broken(*args):
        raise RuntimeError("the lake is on fire")

    monkeypatch.setattr(load_events, "read_day", broken)
    with pytest.raises(RuntimeError):
        load_events.run([DAY], schema)
    assert query(schema, "select status, error from {s}.load_runs") == [
        ("failed", "RuntimeError: the lake is on fire")
    ]


def test_upload_keeps_each_file_s_path(lake, tmp_path):
    (tmp_path / "events" / "dt=2026-10-27").mkdir(parents=True)
    (tmp_path / "events" / "dt=2026-10-27" / "synthetic.jsonl").write_text(line("e1") + "\n")
    (tmp_path / "readers").mkdir()
    (tmp_path / "readers" / "synthetic.jsonl").write_text("{}\n")
    (tmp_path / "notes.txt").write_text("not lake data")

    assert upload.upload(tmp_path, lake, lake_bucket()) == 2
    keys = sorted(o["Key"] for o in lake.list_objects_v2(Bucket=lake_bucket())["Contents"])
    assert keys == ["events/dt=2026-10-27/synthetic.jsonl", "readers/synthetic.jsonl"]


class SeaweedLike:
    """A lake client that acts as SeaweedFS did on Kai's PC: its bucket list comes back
    empty, and creating the bucket again answers "you already own it"."""

    def __init__(self, real):
        self.real = real

    def list_buckets(self):
        return {"Buckets": []}

    def create_bucket(self, Bucket):
        error = {"Error": {"Code": "BucketAlreadyOwnedByYou", "Message": "you own it"}}
        raise ClientError(error, "CreateBucket")

    def __getattr__(self, name):
        return getattr(self.real, name)


def test_upload_works_when_the_bucket_already_exists(lake, tmp_path):
    (tmp_path / "readers").mkdir()
    (tmp_path / "readers" / "synthetic.jsonl").write_text("{}\n")
    assert upload.upload(tmp_path, SeaweedLike(lake), lake_bucket()) == 1


def test_other_bucket_errors_still_stop_the_upload(lake, tmp_path):
    class Refusing(SeaweedLike):
        def create_bucket(self, Bucket):
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "CreateBucket")

    with pytest.raises(ClientError):
        upload.upload(tmp_path, Refusing(lake), lake_bucket())
