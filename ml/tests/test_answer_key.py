"""The models' answer key: each reader's true chance of finishing a reading, every day."""

import gzip
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simulate as sim  # noqa: E402

END = date(2026, 10, 27)


def run(readers: int = 300, days: int = 40, seed: int = 5):
    truth: list[dict] = []
    people, events = sim.simulate(readers, days, END, seed, truth)
    return people, events, truth


def test_collecting_the_answer_key_changes_no_event():
    _, without = sim.simulate(300, 40, END, 5)
    _, with_key, truth = run()
    assert with_key == without and truth


def test_one_row_per_reader_for_every_day_from_joining_to_the_end():
    people, _, truth = run()
    days = {(r["user_key"], r["day"]) for r in truth}
    assert len(days) == len(truth)  # no reader-day twice
    for reader in people:
        joined = date.fromisoformat(reader.signed_up_on)
        expected = (END - joined).days + 1
        assert sum(r["user_key"] == reader.user_key for r in truth) == expected


def test_chances_are_real_probabilities():
    _, _, truth = run()
    assert all(0 <= r["finish_chance"] <= 0.98 * sim.FINISH_CHANCE for r in truth)
    assert any(r["finish_chance"] == 0 for r in truth)  # some readers leave in 40 days


def test_nobody_finishes_a_reading_on_a_day_the_truth_says_is_impossible():
    people, events, truth = run()
    zone = {r.user_key: ZoneInfo(r.timezone) for r in people}
    finished = {
        (
            e["user_key"],
            datetime.fromisoformat(e["occurred_at"])
            .astimezone(zone[e["user_key"]])
            .date()
            .isoformat(),
        )
        for e in events
        if e["event_type"] == "reading_completed"
    }
    impossible = {(r["user_key"], r["day"]) for r in truth if r["finish_chance"] == 0}
    assert impossible and not impossible & finished


def test_the_truth_adds_up_to_what_happened():
    # Over many reader-days, the expected number of finished readings (the sum of the
    # chances) should match the number actually finished, within chance
    _, events, truth = run(readers=1500, days=60, seed=11)
    expected = sum(r["finish_chance"] for r in truth)
    finished = sum(e["event_type"] == "reading_completed" for e in events)
    assert abs(finished - expected) / expected < 0.02


def test_the_file_is_the_same_bytes_every_time(tmp_path):
    _, _, truth = run(readers=50, days=10)
    first, second = tmp_path / "a.csv.gz", tmp_path / "b.csv.gz"
    assert sim.write_answer_key(truth, first) == len(truth)
    sim.write_answer_key(truth, second)
    assert first.read_bytes() == second.read_bytes()
    lines = gzip.decompress(first.read_bytes()).decode().splitlines()
    assert lines[0] == "user_key,day,finish_chance" and len(lines) == len(truth) + 1


def test_a_short_stay_has_one_row_per_day_in_order():
    reader = sim.Reader(
        "sim:00009",
        "commuter",
        "Europe/London",
        "06:30",
        (END - timedelta(days=5)).isoformat(),
        True,
        "A",
    )
    truth: list[dict] = []
    sim.simulate_reader(reader, END, 3, truth)
    assert [r["day"] for r in truth] == [
        (END - timedelta(days=n)).isoformat() for n in range(5, -1, -1)
    ]
