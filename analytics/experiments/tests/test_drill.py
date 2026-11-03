"""The drill, checked by hand on tiny made-up runs, and against the real practice run."""

import pandas as pd
import pytest
import simulate as sim

import drill


def reader(key, joined="2026-10-01", group="B"):
    return sim.Reader(key, "commuter", "America/New_York", "06:30", joined, True, group)


def event(key, kind, at):
    return {"user_key": key, "event_type": kind, "occurred_at": at}


def test_the_table_counts_like_the_warehouse():
    readers = [reader("r1"), reader("r2", joined="2026-10-20")]
    events = [
        # r1, day 1 (2 October in New York): opened and finished
        event("r1", "reading_opened", "2026-10-02T10:00:00Z"),
        event("r1", "reading_completed", "2026-10-02T10:05:00Z"),
        # r1, day 7 (8 October, 23:30 in New York, already the 9th in UTC): finished
        event("r1", "reading_opened", "2026-10-09T03:25:00Z"),
        event("r1", "reading_completed", "2026-10-09T03:30:00Z"),
        # r1, day 3: opened but never finished
        event("r1", "reading_opened", "2026-10-04T10:00:00Z"),
        # The last day with any data is 24 October, so r2 (joined the 20th) has no day 7 yet
        event("r2", "reading_completed", "2026-10-24T12:00:00Z"),
    ]
    table = drill.experiment_table(readers, events).set_index("user_key")
    r1 = table.loc["r1"]
    assert (r1.read_day_1, r1.read_day_7, r1.can_have_day_7) == (True, True, True)
    assert (r1.first_week_opened, r1.first_week_finished) == (3, 2)
    assert not table.loc["r2"].can_have_day_7


def test_the_drill_rebuilds_the_real_practice_run_exactly():
    # Seed 7 with the planted effect is the run the warehouse holds: the drill must reach the
    # same verdict, with the same numbers, as analyze.py on fct_experiment (PR #64)
    run = drill.one_run(7, sim.WORDING_B_LIFT)
    assert run["estimate"] == pytest.approx(649 / 1536 - 626 / 1637)
    assert (round(run["low"], 3), round(run["high"], 3)) == (0.006, 0.074)
    assert run["decision"] == "Switch every reader to wording B"


def test_one_run_puts_the_answer_key_back(monkeypatch):
    monkeypatch.setattr(drill, "READERS", 200)
    before = sim.WORDING_B_LIFT
    # 200 readers never reach the planned look, which the drill reports as "Not yet"
    assert drill.one_run(3, 0.0)["decision"] == "Not yet"
    assert sim.WORDING_B_LIFT == before


def test_the_truth_comes_from_the_twins():
    aa = pd.DataFrame({"seed": [1, 2, 3], "estimate": [0.01, -0.02, 0.00]})
    ab = pd.DataFrame({"seed": [1, 2], "estimate": [0.06, 0.04]})
    # Only seeds with both twins count: (0.06 - 0.01 + 0.04 + 0.02) / 2
    assert drill.true_effect(aa, ab) == pytest.approx(0.055)


def test_the_scorecard_counts_alarms_power_and_coverage():
    aa = pd.DataFrame(
        {
            "decision": ["Keep wording A: no clear difference"] * 18
            + ["Switch every reader to wording B", "Keep wording A: B did worse"],
            "estimate": [0.0] * 20,
            "low": [-0.03] * 20,
            "high": [0.03] * 20,
            "split_p": [0.5] * 20,
        }
    )
    ab = pd.DataFrame(
        {
            "decision": ["Switch every reader to wording B"] * 17
            + ["Keep wording A: no clear difference"] * 3,
            "estimate": [0.06] * 20,
            "low": [0.02] * 19 + [0.07],
            "high": [0.10] * 20,
            "split_p": [0.5] * 20,
        }
    )
    card = drill.summary(aa, ab, truth=0.059)
    assert "any false alarm | about 5% or less | **10.0%** (2 of 20)" in card
    assert "(power) | 80% or more | **85.0%** (17 of 20)" in card
    assert "holds the truth (+5.9 points) | about 95% | **95.0%** (19 of 20)" in card
