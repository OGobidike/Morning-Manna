"""The dashboard's numbers: the arithmetic on small hand-made tables, then the real warehouse
checked against itself and against the simulator's answer key. Run after dbt build."""

import os

import pandas as pd
import pytest
from sqlalchemy import create_engine

import data

URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
SIMULATED = ["early_riser", "commuter", "weekend_reader"]


@pytest.fixture(scope="module")
def engine():
    return create_engine(URL)


def scalar(engine, sql: str):
    with engine.connect() as connection:
        return pd.read_sql(sql, connection).iloc[0, 0]


# ---- The arithmetic, on tables small enough to check by hand ---------------------------


def test_survival_counts_ended_streaks_only():
    # Four streaks that all ended: 1, 2, 2 and 3 mornings long
    streaks = pd.DataFrame({"length_days": [1, 2, 2, 3], "is_current": [False] * 4})
    reach = data.survival(streaks, longest=4).set_index("mornings").reach
    assert reach[1] == 1  # every streak lasts a first morning
    assert reach[2] == pytest.approx(3 / 4)  # the 1-morning one ended
    assert reach[3] == pytest.approx(3 / 4 * 1 / 3)  # of the 3 left, two ended at 2
    assert reach[4] == 0


def test_a_streak_still_going_is_never_counted_as_broken():
    # One streak ended after 1 morning; one is 2 mornings long and still going
    streaks = pd.DataFrame({"length_days": [1, 2], "is_current": [False, True]})
    reach = data.survival(streaks, longest=3).set_index("mornings").reach
    assert reach[2] == pytest.approx(1 / 2)
    assert reach[3] == pytest.approx(1 / 2)  # the ongoing streak didn't break


def test_daily_totals_add_the_personas_up():
    day = pd.Timestamp("2026-10-01")
    rows = pd.DataFrame(
        {
            "local_day": [day, day],
            "persona": ["early_riser", "commuter"],
            "readers_so_far": [10, 30],
            "active_readers": [4, 6],
            "opened_reading": [5, 5],
            "finished_reading": [4, 5],
        }
    )
    days = data.daily_totals(rows)
    assert days.active_readers[0] == 10
    assert days.read_share[0] == pytest.approx(10 / 40)
    assert days.completion_rate[0] == pytest.approx(9 / 10)


def test_headline_compares_with_a_week_before():
    days = pd.DataFrame(
        {
            "readers_so_far": range(100, 114),  # one new reader a day
            "active_7_day_average": [None] * 6 + [50.0] * 7 + [60.0],
            "completion_7_day": [0.80] * 13 + [0.90],
            "opened_reading": [10] * 14,
        }
    )
    weeks = pd.DataFrame({"day_7_eligible": [10, 30], "day_7_returned": [5, 10]})
    numbers = data.headline(days, weeks)
    assert numbers["readers"] == 113
    assert numbers["new_readers"] == 7
    assert numbers["daily_change"] == pytest.approx(0.2)  # 60 against 50
    assert numbers["finish_change"] == pytest.approx(0.1)
    assert numbers["day_7_return"] == pytest.approx(15 / 40)
    assert numbers["finish_readers"] == 70  # the last 7 days' readers who opened one
    assert numbers["day_7_readers"] == 40


def test_headline_copes_with_too_little_history():
    days = pd.DataFrame(
        {
            "readers_so_far": [5],
            "active_7_day_average": [None],
            "completion_7_day": [None],
            "opened_reading": [0],
        }
    )
    weeks = pd.DataFrame({"day_7_eligible": [0], "day_7_returned": [0]})
    numbers = data.headline(days, weeks)
    assert numbers["new_readers"] is None
    assert numbers["daily_readers"] is None
    assert numbers["day_7_return"] is None


def test_the_clock_has_all_48_half_hours():
    times = pd.DataFrame(
        {"persona": ["commuter", "early_riser"], "half_hour": [14, 11], "readings": [3, 2]}
    )
    grid = data.clock_grid(times)
    assert list(grid.index) == list(range(48))
    assert list(grid.columns) == ["early_riser", "commuter"]  # the page's order, not the table's
    assert grid.to_numpy().sum() == 5


def test_the_rhythm_lays_days_out_like_a_calendar():
    days = pd.DataFrame(
        {
            "local_day": pd.to_datetime(["2026-10-26", "2026-11-01"]),  # a Monday and a Sunday
            "read_share": [0.5, 0.25],
            "active_readers": [5, 2],
            "readers_so_far": [10, 8],
        }
    )
    calendar = data.rhythm(days)
    assert list(calendar.weekday) == [0, 6]
    assert calendar.week.nunique() == 1  # the same week


# ---- The warehouse, checked against itself ----------------------------------------------


def test_every_simulated_persona_is_offered(engine):
    choices = data.personas(engine)
    assert choices[0] == "all"
    assert set(SIMULATED) <= set(choices)


def test_every_day_is_there_once(engine):
    days = data.daily_totals(data.activity(engine))
    assert days.local_day.is_unique
    # No gaps: a missing day would show as a false dip
    assert (days.local_day.diff().dropna() == pd.Timedelta(days=1)).all()


def test_the_personas_add_up_to_everyone(engine):
    everyone = data.daily_totals(data.activity(engine)).set_index("local_day").active_readers
    parts = sum(
        data.daily_totals(data.activity(engine, p))
        .set_index("local_day")
        .active_readers.reindex(everyone.index, fill_value=0)
        for p in data.personas(engine)[1:]
    )
    assert (parts == everyone).all()


def test_active_readers_match_the_warehouse(engine):
    reader_days = scalar(engine, "select count(*) from analytics.int_daily_reading where did_read")
    assert data.daily_totals(data.activity(engine)).active_readers.sum() == reader_days


def test_the_clock_holds_every_finished_reading(engine):
    finished = scalar(
        engine, "select count(*) from analytics.stg_events where event_type = 'reading_completed'"
    )
    assert data.clock_grid(data.reading_times(engine)).to_numpy().sum() == finished


def test_cohorts_add_up_across_personas(engine):
    everyone = data.cohorts(engine).set_index("cohort_week")
    parts = sum(
        data.cohorts(engine, p)
        .set_index("cohort_week")[["readers", "day_7_returned"]]
        .reindex(everyone.index, fill_value=0)
        for p in data.personas(engine)[1:]
    )
    assert (parts.readers == everyone.readers).all()
    assert (parts.day_7_returned == everyone.day_7_returned).all()


def test_survival_starts_whole_and_only_falls(engine):
    reach = data.survival(data.streaks(engine)).reach
    assert reach.iloc[0] == 1
    assert (reach.diff().dropna() <= 0).all()


# ---- The warehouse, checked against the simulator's answer key (ml/simulate.py) ---------


def test_finish_rate_matches_the_answer_key(engine):
    # The simulator has readers finish 9 in 10 of the readings they open
    days = data.daily_totals(data.activity(engine))
    assert days.finished_reading.sum() / days.opened_reading.sum() == pytest.approx(0.9, abs=0.01)


def test_early_risers_read_before_commuters(engine):
    # Early risers wake around 05:15, commuters around 06:30
    grid = data.clock_grid(data.reading_times(engine))
    assert grid.early_riser.idxmax() < grid.commuter.idxmax()


def test_commuters_skip_sundays(engine):
    # Commuters are half as likely to read on a Sunday as midweek
    calendar = data.rhythm(data.daily_totals(data.activity(engine, "commuter")))
    by_weekday = calendar.groupby("weekday").read_share.mean()
    assert by_weekday[6] < 0.7 * by_weekday[2]
