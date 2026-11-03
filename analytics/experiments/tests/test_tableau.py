"""The Tableau files, built from small made-up tables (no warehouse needed)."""

from datetime import date, timedelta

import pandas as pd
import pytest

import analyze
import tableau


def readers(days: list[int], per_day: int = 10) -> pd.DataFrame:
    """per_day readers in each group joining on each listed day; all of them reached day 7."""
    start = date(2026, 8, 1)
    rows = [
        {
            "reminder_variant": group,
            "signed_up_on": start + timedelta(days=d),
            "can_have_day_7": True,
            "read_day_1": n % 2 == 0,
            "read_day_7": n % 3 == 0,
            "first_week_opened": 4,
            "first_week_finished": 3,
        }
        for d in days
        for group in ("A", "B")
        for n in range(per_day)
    ]
    return pd.DataFrame(rows)


def test_the_look_fills_in_days_nobody_joined():
    look = tableau.look_table(readers([0, 1, 3]), per_group=25)
    a = look[look.group == "A: Good morning"]
    assert list(a.signup_day) == [date(2026, 8, d) for d in (1, 2, 3, 4)]
    assert list(a.new_readers) == [10, 10, 0, 10]
    assert list(a.readers_so_far) == [10, 20, 20, 30]


def test_the_look_marks_one_day_for_each_group():
    look = tableau.look_table(readers([0, 1, 3]), per_group=25)
    marked = look[look.is_the_look]
    # 25 readers each are first reached on the 4th of August
    assert list(marked.signup_day) == [date(2026, 8, 4)] * 2
    assert set(marked.group) == set(tableau.GROUPS.values())


def test_the_result_matches_the_analysis_in_points():
    people = readers(list(range(10)))
    result = tableau.result_table(people, truth=0.055, per_group=50).set_index("measure")
    counted, _ = analyze.at_the_look(people, per_group=50)
    a, b = analyze.tally(counted, "A"), analyze.tally(counted, "B")
    day_7 = analyze.compare(a["day_7"], a["readers"], b["day_7"], b["readers"])
    row = result.loc["Day-7 return"]
    assert row.difference_points == round(day_7.difference * 100, 2)
    assert (row.a_successes, row.a_total) == (a["day_7"], a["readers"])
    assert row.truth_points == 5.5 and pd.isna(row.guardrail_floor_points)
    assert result.loc["Finish rate"].guardrail_floor_points == -2.0
    assert list(result.role) == ["Decides", "Guardrail", "Guardrail"]


def test_the_drill_answers_each_question_only_where_it_applies():
    runs = pd.DataFrame(
        {
            "seed": [1, 2, 1, 2],
            "lift": [0.0, 0.0, 0.1, 0.1],
            "estimate": [0.001, -0.05, 0.06, 0.01],
            "low": [-0.03, -0.08, 0.03, -0.02],
            "high": [0.03, -0.02, 0.09, 0.04],
            "p_value": [0.9, 0.002, 0.0001, 0.5],
            "decision": [
                "Keep wording A: no clear difference",
                "Keep wording A: B did worse",
                "Switch every reader to wording B",
                "Keep wording A: no clear difference",
            ],
        }
    )
    table = tableau.drill_table(runs, truth=0.055)
    aa, ab = table.iloc[:2], table.iloc[2:]
    assert list(aa.false_alarm) == [False, True] and ab.false_alarm.isna().all()
    assert list(ab.found_b) == [True, False] and aa.found_b.isna().all()
    assert list(ab.interval_holds_truth) == [True, False]
    assert list(table.truth_points) == [0.0, 0.0, 5.5, 5.5]
    assert list(table.estimate_points) == [0.1, -5.0, 6.0, 1.0]


def test_no_result_before_the_look():
    with pytest.raises(ValueError, match="No look yet"):
        tableau.result_table(readers([0, 1]), truth=0.055, per_group=100)


def test_nothing_that_names_a_reader_leaves_the_warehouse():
    people = readers([0, 1, 3]).assign(user_key="sim:00001")
    look = tableau.look_table(people, per_group=25)
    result = tableau.result_table(people, truth=0.055, per_group=25)
    for table in (look, result):
        assert "user_key" not in table.columns
