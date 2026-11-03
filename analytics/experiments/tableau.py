"""The reminder experiment as three tidy tables, for Tableau Public.

Tableau Public is open to everyone, so these files hold only the pretend readers' practice
run, and only counts and results: no reader keys, nothing from a real app user.

    experiment_look.csv    one row per signup day per group: the climb to 1,508 readers
    experiment_result.csv  one row per measure: B minus A, its interval, the guardrail floor
    experiment_drill.csv   one row per practice run: its estimate, interval and decision

Every number comes from analyze.py and drill.py, so Tableau, the charts and the results page
always agree. Differences are in points (percentage points), the unit people read.

Run it from this folder after `dbt build` (CI checks the committed files are up to date):
    python tableau.py
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

import analyze
import drill

OUT = Path(__file__).resolve().parents[1] / "tableau"
GROUPS = {"A": "A: Good morning", "B": "B: New every morning"}
SETS = {False: "No effect (A/A)", True: "Wording B's effect (A/B)"}


def pretend_readers(engine) -> pd.DataFrame:
    """The practice run's readers: the same columns as analyze.readers_in_test, no real users."""
    with engine.connect() as connection:
        return pd.read_sql(
            text(
                """
                select user_key, reminder_variant, signed_up_on, can_have_day_7,
                       read_day_1, read_day_7, first_week_opened, first_week_finished
                from analytics.fct_experiment
                where source = 'synthetic'
                """
            ),
            connection,
        )


def points(x: float) -> float:
    return round(x * 100, 2)


def look_table(readers: pd.DataFrame, per_group: int = analyze.PER_GROUP) -> pd.DataFrame:
    """Readers who had reached day 7, by signup day and group, with every day filled in."""
    reached = readers[readers.can_have_day_7]
    daily = (
        reached.groupby(["signed_up_on", "reminder_variant"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["A", "B"], fill_value=0)
    )
    days = pd.date_range(daily.index.min(), daily.index.max(), freq="D").date
    daily = daily.reindex(days, fill_value=0)
    _, look = analyze.at_the_look(readers, per_group)
    rows = []
    for group in ("A", "B"):
        for day, new, so_far in zip(days, daily[group], daily[group].cumsum()):
            rows.append(
                {
                    "signup_day": day,
                    "group": GROUPS[group],
                    "new_readers": int(new),
                    "readers_so_far": int(so_far),
                    "planned_size": per_group,
                    "is_the_look": day == look,
                }
            )
    return pd.DataFrame(rows)


def result_table(
    readers: pd.DataFrame, truth: float, per_group: int = analyze.PER_GROUP
) -> pd.DataFrame:
    """B minus A for each measure at the look, with the counts it rests on."""
    counted, look = analyze.at_the_look(readers, per_group)
    if look is None:
        raise ValueError(f"No look yet: a group has fewer than {per_group:,} readers at day 7")
    a, b = analyze.tally(counted, "A"), analyze.tally(counted, "B")
    measures = [
        ("Day-7 return", "Decides", "day_7", "readers"),
        ("Day-1 return", "Guardrail", "day_1", "readers"),
        ("Finish rate", "Guardrail", "finished", "opened"),
    ]
    rows = []
    for order, (name, role, hits, out_of) in enumerate(measures, start=1):
        c = analyze.compare(a[hits], a[out_of], b[hits], b[out_of])
        rows.append(
            {
                "order": order,
                "measure": name,
                "role": role,
                "a_successes": a[hits],
                "a_total": a[out_of],
                "b_successes": b[hits],
                "b_total": b[out_of],
                "a_rate_pct": points(c.rate_a),
                "b_rate_pct": points(c.rate_b),
                "difference_points": points(c.difference),
                "low_points": points(c.low),
                "high_points": points(c.high),
                "p_value": round(c.p_value, 4),
                "guardrail_floor_points": (
                    -points(analyze.GUARDRAIL_DROP) if role == "Guardrail" else None
                ),
                "truth_points": points(truth) if role == "Decides" else None,
            }
        )
    return pd.DataFrame(rows)


def drill_table(runs: pd.DataFrame, truth: float) -> pd.DataFrame:
    """Every practice run, with what the analysis decided and whether that was right."""
    planted = runs.lift > 0
    holds = (runs.low <= truth) & (truth <= runs.high)
    alarm = runs.decision.str.startswith("Switch") | runs.decision.str.contains("did worse")
    return pd.DataFrame(
        {
            "seed": runs.seed,
            "run_set": planted.map(SETS),
            "estimate_points": (runs.estimate * 100).round(2),
            "low_points": (runs.low * 100).round(2),
            "high_points": (runs.high * 100).round(2),
            "p_value": runs.p_value.round(4),
            "decision": runs.decision,
            # True or False only where the question applies to that set of runs
            "false_alarm": alarm.where(~planted),
            "found_b": runs.decision.str.startswith("Switch").where(planted),
            "interval_holds_truth": holds.where(planted),
            "truth_points": (planted * truth * 100).round(2),
        }
    )


def everything(engine) -> dict[str, pd.DataFrame]:
    readers = pretend_readers(engine)
    runs = pd.read_csv(Path(__file__).with_name("drill_runs.csv"))
    truth = drill.true_effect(runs[runs.lift == 0], runs[runs.lift > 0])
    return {
        "experiment_look.csv": look_table(readers),
        "experiment_result.csv": result_table(readers, truth),
        "experiment_drill.csv": drill_table(runs, truth),
    }


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    OUT.mkdir(exist_ok=True)
    for name, table in everything(create_engine(url)).items():
        table.to_csv(OUT / name, index=False, lineterminator="\n")
        print(f"{OUT.name}/{name}: {len(table):,} rows")
