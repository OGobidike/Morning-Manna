"""The answer key's maths, checked on small runs (none of them reveals the real answer)."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import simulate as sim  # noqa: E402
import true_effect as key  # noqa: E402

END = date(2026, 10, 27)


def reader(user_key="sim:00001", timezone="America/New_York", joined="2026-10-01"):
    return sim.Reader(user_key, "commuter", timezone, "06:30", joined, True, "B")


def finished(at, user_key="sim:00001"):
    return {"user_key": user_key, "event_type": "reading_completed", "occurred_at": at}


def test_day_7_is_counted_in_the_reader_s_own_time():
    r = reader(joined="2026-10-01")
    # 23:30 on 8 October in New York is already 9 October in UTC: still the reader's day 7
    assert key.read_on_day_7([r], [finished("2026-10-09T03:30:00Z")]) == {"sim:00001": True}
    # A reading on day 6 doesn't count
    assert key.read_on_day_7([r], [finished("2026-10-07T12:00:00Z")]) == {"sim:00001": False}


def test_no_planted_effect_means_no_true_effect(monkeypatch):
    monkeypatch.setattr(sim, "WORDING_B_LIFT", 0.0)
    people, with_effect, without = key.with_and_without(300, 40, END, 5)
    assert with_effect == without
    effect, margin, n = key.true_effect(people, with_effect, without, END)
    assert (effect, margin) == (0.0, 0.0) and n > 0


def test_the_answer_key_is_put_back(monkeypatch):
    monkeypatch.setattr(sim, "WORDING_B_LIFT", 0.37)
    key.with_and_without(50, 20, END, 5)
    assert sim.WORDING_B_LIFT == 0.37


def test_group_a_is_the_same_in_both_runs(monkeypatch):
    monkeypatch.setattr(sim, "WORDING_B_LIFT", 0.5)  # a big, made-up effect, not the real one
    people, with_effect, without = key.with_and_without(300, 40, END, 5)
    a = [r.user_key for r in people if r.reminder_variant == "A"]
    assert a and all(with_effect[k] == without[k] for k in a)


def test_only_readers_who_had_their_day_7_count():
    people = [reader("sim:00001", joined="2026-10-01"), reader("sim:00002", joined="2026-10-25")]
    with_effect = {"sim:00001": True, "sim:00002": True}
    without = {"sim:00001": False, "sim:00002": False}
    # sim:00002 joined on the 25th, so its day 7 is after the end: it can't count
    assert key.true_effect(people + [reader("sim:00003", joined="2026-10-02")],
                           with_effect | {"sim:00003": False},
                           without | {"sim:00003": False}, END)[2] == 2
