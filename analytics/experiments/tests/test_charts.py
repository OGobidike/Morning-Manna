"""The experiment's charts, drawn from small made-up tables (no warehouse needed)."""

from datetime import date, timedelta

import pandas as pd

import analyze
import charts


def comparison(difference: float, low: float, high: float) -> analyze.Comparison:
    return analyze.Comparison(0.40, 0.40 + difference, difference, 2.0, 0.04, low, high)


def results(low: float = 0.006, high: float = 0.074) -> dict[str, analyze.Comparison]:
    return {
        "Day-7 return": comparison(0.040, low, high),
        "Day-1 return": comparison(0.048, 0.013, 0.082),
        "Finish rate": comparison(0.002, -0.009, 0.012),
    }


def readers(per_day: int, days: int) -> pd.DataFrame:
    """per_day readers in each group joining every day; all of them reached day 7."""
    start = date(2026, 8, 1)
    rows = [
        {
            "reminder_variant": group,
            "signed_up_on": start + timedelta(days=d),
            "can_have_day_7": True,
        }
        for d in range(days)
        for group in ("A", "B")
        for _ in range(per_day)
    ]
    return pd.DataFrame(rows)


def test_the_result_says_whether_the_truth_is_inside_the_interval():
    inside = charts.the_result(results(), truth=0.055)
    outside = charts.the_result(results(high=0.050), truth=0.055)
    assert "sits inside" in inside.layout.title.text
    assert "falls outside" in outside.layout.title.text


def test_the_result_draws_every_measure_and_the_truth_on_day_7():
    fig = charts.the_result(results(), truth=0.055)
    measures = [t for t in fig.data if t.name != "the truth"]
    assert [t.y[0] for t in measures] == ["Finish rate", "Day-1 return", "Day-7 return"]
    truth = next(t for t in fig.data if t.name == "the truth")
    assert truth.y[0] == "Day-7 return" and abs(truth.x[0] - 5.5) < 1e-9
    # The interval runs from +0.6 to +7.4 points around the +4.0 dot
    day_7 = measures[-1]
    assert abs(day_7.error_x.arrayminus[0] - 3.4) < 1e-9
    assert abs(day_7.error_x.array[0] - 3.4) < 1e-9


def test_the_look_climbs_to_the_planned_size_and_marks_the_day():
    fig = charts.the_look(readers(per_day=10, days=30), per_group=100)
    a, b = fig.data
    assert (a.name, b.name) == ("Group A", "Group B")
    assert list(a.y[:3]) == [10, 20, 30] and a.y[-1] == 300
    # 100 readers each on the 10th day, 10 August
    assert "on 10 August" in fig.layout.title.text
    assert any(s.type == "line" and s.x0 == pd.Timestamp(2026, 8, 10) for s in fig.layout.shapes)


def test_the_look_says_not_yet_when_the_groups_are_too_small():
    fig = charts.the_look(readers(per_day=1, days=5), per_group=100)
    assert "not yet" in fig.layout.title.text
    assert not any(s.x0 == s.x1 for s in fig.layout.shapes)  # no upright line for the look


def test_the_drill_shows_both_sets_of_runs_in_their_own_colours():
    runs = pd.DataFrame(
        {
            "lift": [0.0] * 6 + [0.1] * 3,
            "estimate": [-0.02, -0.01, 0.0, 0.0, 0.01, 0.02, 0.04, 0.05, 0.07],
        }
    )
    fig = charts.the_drill(runs, real=0.040, truth=0.055)
    no_effect, with_effect = fig.data
    assert no_effect.name.startswith("6 runs") and with_effect.name.startswith("3 runs")
    assert no_effect.marker.color == charts.NO_EFFECT and with_effect.marker.color == charts.B
    labels = [a.text for a in fig.layout.annotations]
    assert "our run: +4.0" in labels and "the truth: +5.5" in labels


def test_words_are_written_in_ink_not_in_a_group_s_colour():
    figs = [
        charts.the_result(results(), truth=0.055),
        charts.the_look(readers(per_day=10, days=30), per_group=100),
    ]
    for fig in figs:
        for note in fig.layout.annotations:
            assert note.font.color in (charts.INK, charts.MUTED)
        for trace in fig.data:
            if trace.textfont and trace.textfont.color:
                assert trace.textfont.color == charts.INK


def test_a_wide_interval_still_fits_on_the_chart():
    wide = results() | {"Finish rate": comparison(0.002, -0.06, 0.13)}
    left, right = charts.the_result(wide, truth=0.055).layout.xaxis.range
    assert left <= -6 and right >= 13
