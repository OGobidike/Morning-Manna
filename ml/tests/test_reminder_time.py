"""The best reminder time (Card 7.7): picks land before the reading, and the replay never peeks."""

import ast
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import MetaData, create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reminder_time as rt  # noqa: E402
import reminder_time_charts as charts  # noqa: E402

# Three made-up kinds of reader: (weekday gap, spread), (weekend gap, spread), weekend reads
KINDS = {
    1: ((10, 8), (20, 15), 0.3),
    2: ((75, 20), (40, 30), 0.2),
    3: ((60, 45), (60, 45), 0.5),
}


def pretend_starts(per_kind: int = 40, days: int = 70, seed: int = 3):
    """Starts like fct_reader_starts', and each reader's kind as 7.6 would have grouped them."""
    rng = np.random.default_rng(seed)
    first = rt.TEST_FROM - timedelta(days=days - 21)
    rows, groups = [], {}
    for kind, (weekday, weekend, _) in KINDS.items():
        for i in range(per_kind):
            key = f"sim:{kind}{i:03d}"
            groups[key] = kind
            for n in range(days):
                day = first + timedelta(days=n)
                at_weekend = day.weekday() >= 5
                if rng.random() > 0.6:
                    continue
                mean, spread = weekend if at_weekend else weekday
                rows.append(
                    {
                        "user_key": key,
                        "source": "synthetic",
                        "local_day": day,
                        "at_weekend": at_weekend,
                        "minutes_after_wake": max(1.0, rng.normal(mean, spread)),
                    }
                )
    starts = pd.DataFrame(rows).sort_values(["user_key", "local_day"], ignore_index=True)
    return starts, pd.Series(groups, name="persona_group")


def test_on_time_means_the_half_hour_before_they_start():
    hits = rt.on_time([20])[0]
    assert hits[rt.GRID == 0] == 1  # 20 minutes early: on time
    assert hits[rt.GRID == 20] == 0  # at the very minute they start: too late
    assert rt.on_time([30])[0][rt.GRID == 0] == 1  # exactly half an hour early still counts
    assert rt.on_time([31])[0][rt.GRID == 0] == 0
    graded = rt.score([20, 50, 5], [0, 0, 10])
    assert graded["on_time"] + graded["late"] + graded["too_early"] == pytest.approx(1, abs=1e-3)
    assert graded["late"] == pytest.approx(1 / 3, abs=1e-3)
    assert graded["too_early"] == pytest.approx(1 / 3, abs=1e-3)


def test_each_group_gets_its_own_best_time():
    starts, groups = pretend_starts()
    profiles = rt.learn_profiles(starts, groups, rt.TEST_FROM)
    best = rt.GRID[profiles.curves.argmax(axis=2)]  # day x group
    assert best[0, 0] == 0  # early risers: at waking
    assert 45 <= best[0, 1] <= 70  # commuters on weekdays: about an hour after
    assert best[1, 1] < best[0, 1]  # commuters read earlier at weekends


def test_the_replay_never_peeks_at_later_reads():
    starts, groups = pretend_starts(per_kind=10)
    profiles = rt.learn_profiles(starts, groups, rt.TEST_FROM)
    before = rt.replay(starts, profiles, k=10)
    changed = starts.copy()
    last = changed.index[changed.user_key == changed.user_key[0]][-1]
    changed.loc[last, "minutes_after_wake"] = 200.0  # a strange last morning
    after = rt.replay(changed, profiles, k=10)
    assert (before.model == after.model).all()  # nothing used that morning before it happened


def test_a_new_reader_gets_the_safe_time_then_their_groups():
    starts, groups = pretend_starts()
    profiles = rt.learn_profiles(starts, groups, rt.TEST_FROM)
    newcomer = pd.DataFrame(
        {
            "user_key": ["sim:new"] * 3,
            "source": "synthetic",
            "local_day": [date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)],
            "at_weekend": False,
            "minutes_after_wake": [78.0, 71.0, 80.0],
        }
    )
    picks = rt.replay(newcomer, profiles, k=np.inf)
    assert picks.model.iloc[0] == 0  # nothing known yet: wake time, never late for an early riser
    assert picks.likely_group.iloc[2] == 2 and 45 <= picks.model.iloc[2] <= 70


def test_tuning_tries_every_k_and_picks_the_best():
    starts, groups = pretend_starts(per_kind=15)
    k, table = rt.tune(starts, groups)
    assert list(table.k) == list(rt.KS)
    assert table.on_time[table.k == k].iloc[0] == table.on_time.max()


def test_the_truth_follows_the_simulators_recipe():
    assert rt.true_pick("early_riser", False, False) == 0
    assert 45 <= rt.true_pick("commuter", False, False) <= 70
    assert rt.true_pick("commuter", True, False) < rt.true_pick("commuter", False, False)


def test_the_model_never_sees_the_persona():
    """fct_reader_starts has no persona, and only the grading reads the answer key."""
    sql = Path(rt.__file__).parents[1] / "analytics" / "models" / "marts" / "fct_reader_starts.sql"
    assert "persona" not in sql.read_text()
    tree = ast.parse(Path(rt.__file__).read_text())
    readers_of_the_key = {
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and re.search(r"\bpersona\b", ast.unparse(node))
    }
    assert readers_of_the_key == {"load_truth", "true_pick", "attach_truth"}


@pytest.fixture
def warehouse(tmp_path):
    return create_engine(f"sqlite:///{tmp_path / 'reminders.db'}")


def test_tonight_and_saving(warehouse):
    starts, groups = pretend_starts(per_kind=10)
    profiles = rt.learn_profiles(starts, groups, rt.TEST_FROM)
    readers = pd.DataFrame(
        {
            "user_key": ["sim:1000", "sim:2000", "sim:new"],
            "source": "synthetic",
            "wake_minute": [330, 1410, 400],
        }
    )
    times = rt.tonight(starts, readers, profiles, k=np.inf).set_index("user_key")
    assert times.weekday_reminder["sim:1000"] == "05:30"  # an early riser: at waking
    assert times.weekday_reminder["sim:2000"] == rt.clock(1410 + times.weekday_gap["sim:2000"])
    assert times.weekday_reminder["sim:2000"].startswith("00:")  # past midnight wraps round
    assert times.reads["sim:new"] == 0 and pd.isna(times.likely_group["sim:new"])
    rt.save(warehouse, times.reset_index(), schema=None)
    rt.save(warehouse, times.reset_index().head(2), schema=None)  # a later, smaller run
    with warehouse.connect() as connection:
        saved = connection.execute(select(rt.times_table(MetaData(), schema=None))).all()
    assert len(saved) == 2


def test_the_charts(tmp_path):
    starts, groups = pretend_starts(per_kind=15)
    profiles = rt.learn_profiles(starts, groups, rt.TEST_FROM)
    replayed = rt.replay(starts, profiles, k=np.inf)
    held_out = replayed[replayed.local_day >= rt.TEST_FROM].assign(
        truth=lambda r: np.where(r.at_weekend, 30, 0)
    )
    board = rt.leaderboard(held_out)
    colours = dict(zip(profiles.groups, charts.PERSONA_COLOURS.values(), strict=True))
    figures = [
        charts.gaps(starts, groups, profiles, colours),
        charts.graded(board),
        charts.learning(held_out),
    ]
    assert all(figure.data and figure.layout.title.text for figure in figures)
