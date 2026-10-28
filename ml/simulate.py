

"""Pretend readers for Morning Manna: about 5,000 of them, reading (or not) for 90 days.

There are no real users yet, so the data pipeline, the dashboards and the models need practice
data. This makes it, with habits that look like people's: early risers, commuters who read on the
train, weekend readers, weekday dips, streaks that break, and readers who drift away.

Every reader and event is marked "synthetic", and none of it goes near the app's own tables.

Run it:
    python ml/simulate.py                      # 5,000 readers, the 90 days up to yesterday
    python ml/simulate.py --readers 200 --days 30 --end 2026-10-27 --seed 7

It writes a little data lake, laid out the way S3 will hold it:
    data/lake/readers/synthetic.jsonl                   one line per reader
    data/lake/events/dt=2026-10-27/synthetic.jsonl      one line per event, by the day it arrived
"""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

# The event types the API accepts (backend/app/schemas.py, EventType)
EVENT_TYPES = (
    "app_opened",
    "notification_opened",
    "reading_opened",
    "reading_completed",
    "reminder_snoozed",
)

# The reading plan has 30 days; a reader who finishes starts it again
PLAN_DAYS = 30

PERSONAS = ("early_riser", "commuter", "weekend_reader")
PERSONA_SHARE = (0.35, 0.40, 0.25)

# Where pretend readers live, and how many live there
TIMEZONES = ("Africa/Lagos", "America/New_York", "Europe/London", "Asia/Manila", "America/Chicago")
TIMEZONE_SHARE = (0.30, 0.25, 0.20, 0.15, 0.10)

# Usual wake time for each persona: (mean, spread) in minutes after midnight
WAKE_TIME = {"early_riser": (315, 25), "commuter": (390, 30), "weekend_reader": (435, 45)}

# How likely each persona is to read on each weekday, Monday first
WEEKDAY_FACTOR = {
    "early_riser": (1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.85),
    "commuter": (1.0, 1.0, 1.0, 1.0, 0.95, 0.6, 0.5),
    "weekend_reader": (0.45, 0.4, 0.4, 0.45, 0.5, 1.0, 1.0),
}

# Minutes after waking that a reader opens the passage: (mean, spread) on (weekdays, weekends)
READ_DELAY = {
    "early_riser": ((10, 8), (20, 15)),
    "commuter": ((75, 20), (40, 30)),
    "weekend_reader": ((60, 45), (60, 45)),
}


@dataclass
class Reader:
    """One pretend reader, as the lake's readers file stores them."""

    user_key: str
    persona: str
    timezone: str
    wake_time: str  # "05:15", the reader's local time
    signed_up_on: str  # "2026-08-14"
    reminders_on: bool
    source: str = "synthetic"


def utc_text(moment: datetime) -> str:
    """A moment as "2026-10-27T05:31:12Z", the form the API and the lake use."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_readers(count: int, start: date, days: int, seed: int) -> list[Reader]:
    """Invent the readers: who they are, where they live, and when they joined."""
    rng = np.random.default_rng([seed, 0])
    readers = []
    for n in range(count):
        persona = str(rng.choice(PERSONAS, p=PERSONA_SHARE))
        mean, spread = WAKE_TIME[persona]
        # Round to 5 minutes and keep it between 04:30 and 09:00, like a real alarm
        wake = int(np.clip(round(rng.normal(mean, spread) / 5) * 5, 270, 540))
        # More readers join later on, as an app grows (the square root leans towards the end)
        joined = start + timedelta(days=int(days * np.sqrt(rng.random())))
        readers.append(
            Reader(
                user_key=f"sim:{n + 1:05d}",
                persona=persona,
                timezone=str(rng.choice(TIMEZONES, p=TIMEZONE_SHARE)),
                wake_time=f"{wake // 60:02d}:{wake % 60:02d}",
                signed_up_on=joined.isoformat(),
                reminders_on=bool(rng.random() < 0.85),
            )
        )
    return readers


def simulate_reader(reader: Reader, end: date, seed: int) -> list[dict]:
    """Every event one reader sends, from the day they join to the end date."""
    # Each reader gets their own random stream, so adding readers never changes the others
    rng = np.random.default_rng([seed, int(reader.user_key[4:])])
    zone = ZoneInfo(reader.timezone)
    hours, minutes = map(int, reader.wake_time.split(":"))
    wake = time(hours, minutes)

    events: list[dict] = []
    keen = rng.beta(6, 2)  # how much this reader wants the habit at the start (0 to 1)
    fade = rng.uniform(0.990, 0.999)  # how fast that wears off, per day
    streak = 0  # mornings read in a row, up to yesterday
    days_missed = 0
    completed = 0
    day = date.fromisoformat(reader.signed_up_on)
    age = 0  # days since joining

    while day <= end:
        today: list[tuple[str, datetime, dict]] = []  # this morning's events, before sending
        # Some readers leave for good: most likely in the first few days
        if rng.random() < (0.10 if age < 3 else 0.02):
            break

        chance = keen * WEEKDAY_FACTOR[reader.persona][day.weekday()]
        # A habit carries itself: the longer the streak, the likelier today; a gap makes it harder
        if streak:
            chance += min(0.05 * streak, 0.25)
        elif days_missed >= 2:
            chance -= 0.15
        chance = min(max(chance, 0.0), 0.98)

        woke = datetime.combine(day, wake, tzinfo=zone)
        weekend = day.weekday() >= 5
        mean, spread = READ_DELAY[reader.persona][1 if weekend else 0]
        opened = woke + timedelta(minutes=max(1.0, rng.normal(mean, spread)))

        if rng.random() < chance:
            # The morning reminder: sometimes snoozed for 10 minutes first
            if reader.reminders_on and rng.random() < 0.12:
                today.append(("reminder_snoozed", woke + timedelta(minutes=1), {"minutes": 10}))
                opened += timedelta(minutes=10)
            # Tapping the reminder opens the app; otherwise the reader opens it themselves
            if reader.reminders_on and rng.random() < 0.55:
                today.append(("notification_opened", opened, {}))
            today.append(("app_opened", opened, {}))

            day_number = completed % PLAN_DAYS + 1
            started = opened + timedelta(seconds=float(rng.uniform(3, 30)))
            today.append(("reading_opened", started, {"day_number": day_number}))
            # Most readers finish the passage, a few minutes later
            if rng.random() < 0.9:
                took = timedelta(minutes=float(np.clip(rng.normal(4, 1.5), 1, 15)))
                today.append(("reading_completed", started + took, {"day_number": day_number}))
                completed += 1
                streak, days_missed = streak + 1, 0
            else:
                streak, days_missed = 0, days_missed + 1
        else:
            # A missed morning: now and then the reader still peeks at the app
            if rng.random() < 0.05:
                today.append(("app_opened", opened, {}))
            streak, days_missed = 0, days_missed + 1

        events.extend(send(reader, today, rng))

        keen *= fade
        day += timedelta(days=1)
        age += 1

    return events


def send(reader: Reader, today: list[tuple[str, datetime, dict]],
         rng: np.random.Generator) -> list[dict]:
    """A morning's events as the lake stores them: what happened, when, and when it arrived."""
    if not today:
        return []
    # The phone sends what's waiting together. Usually within seconds; now and then it was
    # offline, and the whole morning arrives together, half a day or more later
    offline = rng.random() < 0.03
    if offline:
        arrival = max(at for _, at, _ in today) + timedelta(hours=float(rng.uniform(12, 30)))
    sent = []
    for event_type, at, properties in today:
        received = arrival if offline else at + timedelta(seconds=float(rng.uniform(0.5, 5)))
        sent.append({
            "user_key": reader.user_key,
            "event_type": event_type,
            "occurred_at": utc_text(at),
            "received_at": utc_text(received),
            "properties": properties,
            "source": "synthetic",
        })
    return sent


def simulate(readers: int, days: int, end: date, seed: int) -> tuple[list[Reader], list[dict]]:
    """All the readers and all their events, oldest first. The same seed gives the same data."""
    start = end - timedelta(days=days - 1)
    people = make_readers(readers, start, days, seed)
    events = [e for reader in people for e in simulate_reader(reader, end, seed)]
    # Phones still offline at the end send their mornings after it: leave those out
    events = [e for e in events if e["received_at"][:10] <= end.isoformat()]
    events.sort(key=lambda e: (e["received_at"], e["user_key"], e["occurred_at"]))
    for n, e in enumerate(events, start=1):
        e["event_id"] = f"sim-{n:08d}"
    return people, events


def write_lake(readers: list[Reader], events: list[dict], out: Path) -> dict:
    """Write the readers file and one events file per arrival day. Running again replaces them."""
    readers_file = out / "readers" / "synthetic.jsonl"
    readers_file.parent.mkdir(parents=True, exist_ok=True)
    readers_file.write_text("".join(json.dumps(asdict(r)) + "\n" for r in readers))

    # Clear out the last run's pretend events first (only ours: the app's own files stay)
    for old in out.glob("events/dt=*/synthetic.jsonl"):
        old.unlink()

    by_day: dict[str, list[dict]] = {}
    for e in events:
        by_day.setdefault(e["received_at"][:10], []).append(e)
    for dt, day_events in by_day.items():
        path = out / "events" / f"dt={dt}" / "synthetic.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(e) + "\n" for e in day_events))

    return {"readers": len(readers), "events": len(events), "days": len(by_day)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Make pretend Morning Manna readers and events.")
    parser.add_argument("--readers", type=int, default=5000)
    parser.add_argument("--days", type=int, default=90)
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    parser.add_argument("--end", type=date.fromisoformat, default=yesterday,
                        help="last day to simulate, e.g. 2026-10-27 (default: yesterday)")
    parser.add_argument("--seed", type=int, default=7, help="same seed, same data")
    parser.add_argument("--out", type=Path, default=Path("data/lake"))
    args = parser.parse_args()

    readers, events = simulate(args.readers, args.days, args.end, args.seed)
    summary = write_lake(readers, events, args.out)
    print(f"{summary['readers']:,} readers, {summary['events']:,} events "
          f"over {summary['days']} days, written to {args.out}/")


if __name__ == "__main__":
    main()
