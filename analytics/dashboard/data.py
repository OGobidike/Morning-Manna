"""The dashboard's questions, asked of the dbt marts. Every number on the page comes from here.

The functions that touch the database only fetch rows; the shaping is done by plain functions
on DataFrames (daily_totals, headline, survival, clock_grid, rhythm), so the tests can check
the arithmetic on small hand-made tables.
"""

import pandas as pd
from sqlalchemy import Engine, text

# Every persona the marts know, in the order the page shows them (their colours follow it)
PERSONAS = {
    "all": "All readers",
    "early_riser": "Early risers",
    "commuter": "Commuters",
    "weekend_reader": "Weekend readers",
    "app": "Real app users",
}

# Matches every persona when the filter says "all"
PERSONA_FILTER = "(:persona = 'all' or persona = :persona)"

# Real app users have no persona in the warehouse: the dashboard calls them "app"
WITH_PERSONA = "(select user_key, coalesce(persona, 'app') as persona from analytics.dim_users)"


def _query(engine: Engine, sql: str, **params) -> pd.DataFrame:
    with engine.connect() as connection:
        return pd.read_sql(text(sql), connection, params=params)


# ---- Fetching ---------------------------------------------------------------------------


def personas(engine: Engine) -> list[str]:
    """The filter's choices: "all", then each persona that has readers, in PERSONAS order."""
    found = set(_query(engine, f"select distinct persona from {WITH_PERSONA} as u").persona)
    return ["all"] + [p for p in PERSONAS if p in found]


def activity(engine: Engine, persona: str = "all") -> pd.DataFrame:
    """One row per day per persona: the chosen persona, or every persona for "all"."""
    rows = _query(
        engine,
        f"""
        select local_day, persona, readers_so_far, active_readers, opened_reading,
               finished_reading
        from analytics.fct_daily_activity
        where {PERSONA_FILTER}
        order by local_day, persona
        """,
        persona=persona,
    )
    rows["local_day"] = pd.to_datetime(rows.local_day)
    return rows


def reading_times(engine: Engine, persona: str = "all") -> pd.DataFrame:
    """Readings finished in each half hour of the readers' own day, per persona."""
    return _query(
        engine,
        f"select persona, half_hour, readings from analytics.fct_reading_times "
        f"where {PERSONA_FILTER}",
        persona=persona,
    )


def streaks(engine: Engine, persona: str = "all") -> pd.DataFrame:
    """Every streak's length, whether it's still going, and its reader's persona."""
    return _query(
        engine,
        f"""
        select u.persona, s.length_days, s.is_current
        from analytics.fct_streaks as s
        join {WITH_PERSONA} as u using (user_key)
        where {PERSONA_FILTER}
        """,
        persona=persona,
    )


def cohorts(engine: Engine, persona: str = "all") -> pd.DataFrame:
    """Each signup week's readers and how many came back (personas added up for "all")."""
    weeks = _query(
        engine,
        f"""
        select
            cohort_week,
            sum(readers)::bigint as readers,
            sum(day_1_eligible)::bigint as day_1_eligible,
            sum(day_1_returned)::bigint as day_1_returned,
            sum(day_7_eligible)::bigint as day_7_eligible,
            sum(day_7_returned)::bigint as day_7_returned,
            sum(day_30_eligible)::bigint as day_30_eligible,
            sum(day_30_returned)::bigint as day_30_returned
        from analytics.fct_retention_cohorts
        where {PERSONA_FILTER}
        group by cohort_week
        order by cohort_week
        """,
        persona=persona,
    )
    for day in (1, 7, 30):
        eligible = weeks[f"day_{day}_eligible"]
        weeks[f"day_{day}_rate"] = weeks[f"day_{day}_returned"] / eligible.where(eligible > 0)
    return weeks


# ---- Shaping ----------------------------------------------------------------------------


def daily_totals(activity: pd.DataFrame) -> pd.DataFrame:
    """The personas added up per day, with the averages and rates the charts draw."""
    columns = ["readers_so_far", "active_readers", "opened_reading", "finished_reading"]
    days = activity.groupby("local_day", as_index=False)[columns].sum()
    days["active_7_day_average"] = days.active_readers.rolling(7, min_periods=7).mean()
    days["read_share"] = days.active_readers / days.readers_so_far.where(days.readers_so_far > 0)
    days["completion_rate"] = days.finished_reading / days.opened_reading.where(
        days.opened_reading > 0
    )
    # Over a week the rate stands on far more readers, so it swings far less
    finished_7 = days.finished_reading.rolling(7, min_periods=7).sum()
    opened_7 = days.opened_reading.rolling(7, min_periods=7).sum()
    days["completion_7_day"] = finished_7 / opened_7.where(opened_7 > 0)
    return days


def headline(days: pd.DataFrame, weeks: pd.DataFrame) -> dict:
    """The four numbers across the top, each with how it moved against a week before."""

    def last(column: str, days_back: int = 0) -> float | None:
        if len(days) <= days_back:
            return None
        value = days[column].iloc[-1 - days_back]
        return None if pd.isna(value) else float(value)

    readers, readers_before = last("readers_so_far"), last("readers_so_far", 7)
    daily, daily_before = last("active_7_day_average"), last("active_7_day_average", 7)
    finish, finish_before = last("completion_7_day"), last("completion_7_day", 7)
    eligible = weeks.day_7_eligible.sum()
    # How many readers each rate rests on, so the page can say when that's too few
    finish_readers = int(days.opened_reading.tail(7).sum()) if len(days) else 0
    return {
        "readers": readers,
        "new_readers": None if readers_before is None else readers - readers_before,
        "daily_readers": daily,
        "daily_change": daily / daily_before - 1 if daily and daily_before else None,
        "finish_rate": finish,
        "finish_change": None
        if finish is None or finish_before is None
        else finish - finish_before,
        "finish_readers": finish_readers,
        "day_7_return": weeks.day_7_returned.sum() / eligible if eligible else None,
        "day_7_readers": int(eligible),
    }


def survival(streaks: pd.DataFrame, longest: int = 30) -> pd.DataFrame:
    """Kaplan-Meier: the share of streaks that last at least n mornings, for n = 1 to longest.

    A streak still going on the last day hasn't ended, so it counts for as long as it has
    lasted and is never counted as broken. Calling it broken would make streaks look shorter
    than they are; leaving it out would lose the readers doing best.
    """
    lengths = streaks.length_days
    ongoing = streaks.is_current.astype(bool)
    share, rows = 1.0, []
    for n in range(1, longest + 1):
        rows.append((n, share))
        going = (lengths >= n).sum()  # streaks that reached morning n
        broke = ((lengths == n) & ~ongoing).sum()  # and ended there
        if going:
            share *= 1 - broke / going
    return pd.DataFrame(rows, columns=["mornings", "reach"])


def clock_grid(times: pd.DataFrame) -> pd.DataFrame:
    """Readings per half hour (rows 0 to 47) per persona (columns), with empty slots as 0."""
    grid = times.pivot_table(
        index="half_hour", columns="persona", values="readings", aggfunc="sum", fill_value=0
    )
    order = [p for p in PERSONAS if p in grid.columns]
    return grid.reindex(index=range(48), columns=order, fill_value=0)


def rhythm(days: pd.DataFrame) -> pd.DataFrame:
    """Each day's read share laid out like a wall calendar: a week column, a weekday row."""
    calendar = days[["local_day", "read_share", "active_readers", "readers_so_far"]].copy()
    calendar["weekday"] = calendar.local_day.dt.day_of_week  # 0 is Monday
    calendar["week"] = calendar.local_day - pd.to_timedelta(calendar.weekday, unit="D")
    return calendar
