

"""Tests for the pretend-reader generator: it must be repeatable, valid, and behave like people."""

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simulate as sim  # noqa: E402

END = date(2026, 10, 27)


@pytest.fixture(scope="module")
def data():
    # 400 readers over 60 days: big enough to show habits, small enough to run in a second
    return sim.simulate(readers=400, days=60, end=END, seed=7)


def test_same_seed_gives_the_same_data():
    first = sim.simulate(readers=50, days=20, end=END, seed=3)
    second = sim.simulate(readers=50, days=20, end=END, seed=3)
    assert first[1] == second[1]
    assert first[0] == second[0]


def test_another_seed_gives_other_data():
    assert sim.simulate(50, 20, END, 3)[1] != sim.simulate(50, 20, END, 4)[1]


def test_events_are_ones_the_api_accepts(data):
    _, events = data
    assert {e["event_type"] for e in events} == set(sim.EVENT_TYPES)
    for e in events:
        # Times carry a time zone (the "Z" means UTC), as the API requires
        assert e["occurred_at"].endswith("Z") and e["received_at"].endswith("Z")
        assert e["occurred_at"] <= e["received_at"]
        assert e["source"] == "synthetic"


def test_event_ids_are_unique(data):
    _, events = data
    assert len({e["event_id"] for e in events}) == len(events)


def test_nothing_happens_before_signing_up_or_arrives_after_the_end(data):
    readers, events = data
    joined = {r.user_key: date.fromisoformat(r.signed_up_on) for r in readers}
    for e in events:
        # Joining day is the reader's local date; in UTC it can still be the day before
        earliest = joined[e["user_key"]] - timedelta(days=1)
        assert date.fromisoformat(e["occurred_at"][:10]) >= earliest
        assert e["received_at"][:10] <= END.isoformat()


def test_a_reading_finishes_after_it_starts(data):
    _, events = data
    opened = {}
    for e in sorted(events, key=lambda e: e["occurred_at"]):
        key = (e["user_key"], e["properties"].get("day_number"))
        if e["event_type"] == "reading_opened":
            opened[key] = e["occurred_at"]
        if e["event_type"] == "reading_completed":
            assert key in opened and opened[key] <= e["occurred_at"]


def completions_by_weekday(data, persona):
    readers, events = data
    who = {r.user_key: r for r in readers}
    counts = [0] * 7
    for e in events:
        reader = who[e["user_key"]]
        if e["event_type"] == "reading_completed" and reader.persona == persona:
            moment = datetime.fromisoformat(e["occurred_at"]).astimezone(
                sim.ZoneInfo(reader.timezone))
            counts[moment.weekday()] += 1
    return counts


def test_commuters_read_less_at_weekends(data):
    counts = completions_by_weekday(data, "commuter")
    assert sum(counts[:5]) / 5 > 1.3 * sum(counts[5:]) / 2


def test_weekend_readers_read_more_at_weekends(data):
    counts = completions_by_weekday(data, "weekend_reader")
    assert sum(counts[5:]) / 2 > 1.5 * sum(counts[:5]) / 5


def test_streaks_break_and_readers_drift_away(data):
    readers, events = data
    days = {}
    for e in events:
        if e["event_type"] == "reading_completed":
            days.setdefault(e["user_key"], set()).add(e["occurred_at"][:10])
    # Most readers who read more than once miss at least one day in between
    gappy = [
        len(d) < (date.fromisoformat(max(d)) - date.fromisoformat(min(d))).days + 1
        for d in days.values() if len(d) > 1
    ]
    assert sum(gappy) / len(gappy) > 0.5
    # Fewer readers are still reading in the last week than ever read at all
    last_week = {k for k, d in days.items() if max(d) >= "2026-10-21"}
    assert len(last_week) < 0.8 * len(days)


def test_write_lake_lays_out_files_by_arrival_day(tmp_path, data):
    readers, events = data
    summary = sim.write_lake(readers, events, tmp_path)
    assert summary == {"readers": 400, "events": len(events), "days": summary["days"]}

    lines = (tmp_path / "readers" / "synthetic.jsonl").read_text().splitlines()
    assert len(lines) == 400 and json.loads(lines[0])["user_key"] == "sim:00001"

    written = 0
    for path in (tmp_path / "events").glob("dt=*/synthetic.jsonl"):
        day = path.parent.name.removeprefix("dt=")
        for line in path.read_text().splitlines():
            assert json.loads(line)["received_at"][:10] == day
            written += 1
    assert written == len(events)


def test_writing_again_replaces_instead_of_adding(tmp_path, data):
    readers, events = data
    sim.write_lake(readers, events, tmp_path)
    sim.write_lake(readers, events, tmp_path)
    total = sum(
        len(p.read_text().splitlines()) for p in (tmp_path / "events").glob("dt=*/*.jsonl")
    )
    assert total == len(events)


def test_a_new_run_clears_only_the_old_pretend_files(tmp_path):
    # An app file sitting in the lake, as the API will write them in Card 5.2
    app_file = tmp_path / "events" / "dt=2026-01-01" / "app-batch.jsonl"
    app_file.parent.mkdir(parents=True)
    app_file.write_text("{}\n")

    sim.write_lake(*sim.simulate(30, 20, END, 1), tmp_path)
    sim.write_lake(*sim.simulate(30, 10, date(2026, 9, 1), 1), tmp_path)

    pretend_days = sorted(p.parent.name for p in (tmp_path / "events").glob("dt=*/synthetic.jsonl"))
    assert all(day <= "dt=2026-09-01" for day in pretend_days)  # none left from the first run
    assert app_file.read_text() == "{}\n"  # the app's file is untouched
