"""The pictures' rules, checked on small hand-made tables: no database needed."""

import numpy as np
import pandas as pd

import app as dashboard
import charts
import data


def days_for(joined: list[int], read: list[int]) -> pd.DataFrame:
    """Daily totals for consecutive days from Monday 26 October 2026."""
    rows = pd.DataFrame(
        {
            "local_day": pd.date_range("2026-10-26", periods=len(joined)),
            "persona": "commuter",
            "readers_so_far": joined,
            "active_readers": read,
            "opened_reading": read,
            "finished_reading": read,
        }
    )
    return data.daily_totals(rows)


def test_days_with_few_readers_are_left_blank():
    # Monday has 5 readers (too few to trust), Tuesday 50
    fig = charts.reading_rhythm(days_for([5, 50], [5, 10]), "commuter")
    cells = np.array(fig.data[0].z, dtype=float)
    assert np.isnan(cells[0, 0])  # Monday: blank, not a loud 100%
    assert cells[1, 0] == 0.2  # Tuesday: 10 of 50


def test_a_chart_with_only_tiny_groups_says_so():
    fig = charts.reading_rhythm(days_for([3, 4], [3, 4]), "app")
    assert fig.layout.annotations[0].text == "Too few readers to show yet"


def test_small_cohorts_are_left_blank():
    weeks = pd.DataFrame(
        {
            "cohort_week": pd.to_datetime(["2026-10-05", "2026-10-12"]).date,
            "readers": [8, 40],
            **{f"day_{d}_eligible": [8, 40] for d in (1, 7, 30)},
            **{f"day_{d}_returned": [4, 10] for d in (1, 7, 30)},
            **{f"day_{d}_rate": [0.5, 0.25] for d in (1, 7, 30)},
        }
    )
    cells = np.array(charts.who_comes_back(weeks, "all").data[0].z, dtype=float)
    assert np.isnan(cells[0]).all()  # 8 readers: blank
    assert (cells[1] == 0.25).all()


def test_colour_follows_the_persona():
    for persona in ("all", "commuter"):
        fig = charts.finish_rate(days_for([50] * 10, [40] * 10), persona)
        assert fig.data[1].line.color == charts.COLOURS[persona]


def test_a_tiny_change_reads_as_steady():
    assert dashboard.change_badge(0.0002, "0.0 pts", steady_below=0.001).children == "● steady"
    assert dashboard.change_badge(-0.05, "5.0 pts", steady_below=0.001).children == "▼ 5.0 pts"
    assert dashboard.change_badge(0.12, "12%", steady_below=0.005).children == "▲ 12%"


def test_the_ramp_runs_light_to_dark():
    def lightness(hex_colour):
        return sum(int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))

    stops = [colour for _, colour in charts.ramp("weekend_reader")]
    assert lightness(stops[0]) > lightness(stops[1]) > lightness(stops[2])


def test_tiles_hide_rates_resting_on_few_readers():
    days = days_for([12] * 10, [3] * 10)  # 3 readers a day: 21 in a week would just pass
    days["opened_reading"] = 2  # but only 14 opened one in the last 7 days
    weeks = pd.DataFrame(
        {"cohort_week": [], "day_7_eligible": [], "day_7_returned": [], "day_7_rate": []}
    )
    tiles = dashboard.tiles(data.headline(days, weeks), days, weeks, "app")
    finish, day_7 = tiles[2], tiles[3]
    for tile in (finish, day_7):
        figure = tile.children[1].children[0].children
        assert figure == "–"
        assert tile.children[2].children == "too few readers yet"


def test_finish_rate_with_too_few_readers_says_so():
    fig = charts.finish_rate(days_for([10] * 10, [5] * 10), "app")
    assert fig.layout.annotations[0].text == "Too few readers to show yet"


def test_streaks_with_too_few_say_so():
    streaks = pd.DataFrame(
        {"persona": ["app"] * 5, "length_days": [1, 2, 3, 1, 1], "is_current": [False] * 5}
    )
    fig = charts.streak_survival(streaks, "app")
    assert fig.layout.annotations[0].text == "Too few streaks to show yet"
