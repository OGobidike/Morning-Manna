"""Reader personas (Card 7.6): the groups come from habits alone, and the grade is honest."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import MetaData, create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import personas as p  # noqa: E402
import personas_charts as charts  # noqa: E402

# Three made-up kinds of reader: (weekday time, weekend time, weekend share, spread)
KINDS = {
    "early_riser": (331, 341, 0.29, 11),
    "commuter": (472, 442, 0.21, 25),
    "weekend_reader": (499, 496, 0.48, 40),
}


def pretend_habits(per_kind: int = 120, seed: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    """Habits like fct_reader_habits', and the answer key, kept apart as in the real thing."""
    rng = np.random.default_rng(seed)
    rows, truth = [], {}
    for kind, (weekday, weekend, share, spread) in KINDS.items():
        for i in range(per_kind):
            key = f"{kind}:{i}"
            reads = int(rng.integers(5, 40))
            weekend_reads = max(1, int(round(reads * share)))
            rows.append(
                {
                    "user_key": key,
                    "source": "synthetic",
                    "reads": reads,
                    "weekday_reads": reads - weekend_reads,
                    "weekend_reads": weekend_reads,
                    "weekday_minute": rng.normal(weekday, 12),
                    "weekend_minute": rng.normal(weekend, 12),
                    "weekend_share": float(np.clip(rng.normal(share, 0.05), 0, 1)),
                    "read_minute_spread": abs(rng.normal(spread, 4)),
                }
            )
            truth[key] = kind
    return pd.DataFrame(rows), pd.Series(truth)


def test_the_halves_are_fixed_and_about_even():
    keys = [f"synthetic:{i}" for i in range(2000)]
    halves = [p.half(k) for k in keys]
    assert halves == [p.half(k) for k in keys]  # the same every run
    assert 0.45 < np.mean(halves) < 0.55


def test_only_readers_with_a_habit_to_show_are_grouped():
    habits, _ = pretend_habits(per_kind=5)
    habits.loc[0, "reads"] = 4  # too few days
    habits.loc[1, "weekend_reads"] = 0  # never read at a weekend
    habits.loc[2, "read_minute_spread"] = None
    kept = set(p.eligible(habits).user_key)
    assert not kept & {habits.user_key[0], habits.user_key[1], habits.user_key[2]}
    assert len(kept) == len(habits) - 3


def test_it_finds_three_kinds_and_numbers_them_earliest_first():
    habits, truth = pretend_habits()
    found = p.find(habits)
    assert found.k == 3 and max(found.silhouette, key=found.silhouette.get) == 3
    centres = p.describe(found)
    assert list(centres.weekday_minute) == sorted(centres.weekday_minute)
    assert centres.label[0].startswith("05:")  # group 1 is the early one
    groups = p.assign(found, habits)
    assert p.grade(groups, truth[habits.user_key]) > 0.95


def test_the_grade_ignores_what_the_groups_are_called():
    truth = pd.Series(["a", "a", "b", "b", "c", "c"])
    assert p.grade(np.array([1, 1, 2, 2, 3, 3]), truth) == 1.0
    assert p.grade(np.array([3, 3, 1, 1, 2, 2]), truth) == 1.0  # same groups, other numbers
    assert p.grade(np.array([1, 2, 3, 1, 2, 3]), truth) < 0.1  # no better than chance


def test_the_model_never_sees_the_persona():
    """fct_reader_habits has no persona column, and the habits the model uses don't either."""
    assert "persona" not in p.FEATURES
    sql = Path(p.__file__).parents[1] / "analytics" / "models" / "marts" / "fct_reader_habits.sql"
    query = sql.read_text().split("\nwith ", 1)[1]  # past the comment that explains why
    assert "persona" not in query


@pytest.fixture
def warehouse(tmp_path):
    return create_engine(f"sqlite:///{tmp_path / 'personas.db'}")


def test_saving_replaces_every_readers_group(warehouse):
    habits, _ = pretend_habits(per_kind=20)
    found = p.find(habits)
    groups = p.assign(found, habits)
    p.save(warehouse, habits, groups, found, schema=None)
    p.save(warehouse, habits.head(10), groups[:10], found, schema=None)  # a later, smaller run
    table = p.personas_table(MetaData(), schema=None)
    with warehouse.connect() as connection:
        rows = pd.DataFrame(connection.execute(select(table)).mappings().all())
    assert len(rows) == 10 and rows.group_label.str.contains("weekdays").all()


def test_clarity_and_the_charts(tmp_path):
    habits, truth = pretend_habits()
    readers = p.eligible(habits)
    readers["half"] = [p.half(k) for k in readers.user_key]
    found = p.find(readers[readers.half == 0])
    readers["group"] = p.assign(found, readers)
    check = readers[readers.half == 1]
    result = p.Result(found, readers, 1.0, p.grade(check.group.values, truth[check.user_key]), 1.0)
    table = p.clarity(habits, truth, found)
    assert set(table.reads) <= set(p.BAND_NAMES) and (table.readers > 0).all()
    figures = [charts.habit_map(result, truth), charts.graded(result, truth), charts.clarity(table)]
    assert all(figure.data and figure.layout.title.text for figure in figures)
