"""The fire drill: the whole reminder experiment, re-run hundreds of times on fresh readers.

One practice run can be lucky. This file asks how the analysis behaves on average:

    A/A runs: no effect planted (wording B is no better than A). The analysis should say
              "switch to B" or "B did worse" only about 5% of the time: its false alarms.
    A/B runs: the real planted effect. The analysis should find B about 80% of the time or
              more (its power), and its 95% interval should hold the true effect about 95%
              of the time (its coverage).

The true effect comes from the runs themselves: each A/B run has an A/A twin with the same
seed, so the same readers, and the only difference between the twins is the planted effect.

Each run simulates 5,000 new readers with a new seed, builds the same per-reader table the
warehouse builds (fct_experiment), and hands it to analyze.py unchanged: the same look, the
same split check, the same z-test, guardrails and decision.

Run it from this folder (about 25 minutes on 4 cores):
    python drill.py              # 1,000 A/A runs and 200 A/B runs
    python drill.py 20 20        # a quicker look: 20 of each
"""

import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import analyze

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml"))
import simulate as sim  # noqa: E402

READERS, DAYS, END = 5000, 90, date(2026, 10, 27)  # the same shape as the real practice run


def experiment_table(readers: list[sim.Reader], events: list[dict]) -> pd.DataFrame:
    """One row per reader, with the same columns and counting as dbt's fct_experiment."""
    zone = {r.user_key: ZoneInfo(r.timezone) for r in readers}
    joined = {r.user_key: date.fromisoformat(r.signed_up_on) for r in readers}
    # Per reader per day of their own: did they open a reading, did they finish one?
    opened, finished = set(), set()
    last_day = None
    for e in events:
        key = e["user_key"]
        day = datetime.fromisoformat(e["occurred_at"]).astimezone(zone[key]).date()
        last_day = day if last_day is None or day > last_day else last_day
        if e["event_type"] == "reading_opened":
            opened.add((key, day))
        elif e["event_type"] == "reading_completed":
            finished.add((key, day))
    rows = []
    for r in readers:
        start = joined[r.user_key]
        week = [start + timedelta(days=n) for n in range(8)]  # day 0 to day 7
        rows.append(
            {
                "user_key": r.user_key,
                "reminder_variant": r.reminder_variant,
                "signed_up_on": start,
                "can_have_day_7": start + timedelta(days=7) <= last_day,
                "read_day_1": (r.user_key, start + timedelta(days=1)) in finished,
                "read_day_7": (r.user_key, start + timedelta(days=7)) in finished,
                "first_week_opened": sum((r.user_key, d) in opened for d in week),
                "first_week_finished": sum(
                    (r.user_key, d) in opened and (r.user_key, d) in finished for d in week
                ),
            }
        )
    return pd.DataFrame(rows)


def one_run(seed: int, lift: float) -> dict:
    """Simulate one practice run with this seed and planted lift, and analyse it."""
    planted = sim.WORDING_B_LIFT
    sim.WORDING_B_LIFT = lift
    try:
        readers, events = sim.simulate(READERS, DAYS, END, seed)
    finally:
        sim.WORDING_B_LIFT = planted  # put the answer key back the way it was
    table = experiment_table(readers, events)
    counted, last_day = analyze.at_the_look(table)
    if last_day is None:  # too few readers to reach the planned look
        nothing = float("nan")
        return {
            "seed": seed,
            "lift": lift,
            "estimate": nothing,
            "low": nothing,
            "high": nothing,
            "p_value": nothing,
            "split_p": nothing,
            "decision": "Not yet",
        }
    a, b = analyze.tally(counted, "A"), analyze.tally(counted, "B")
    day_7 = analyze.compare(a["day_7"], a["readers"], b["day_7"], b["readers"])
    guardrails = {
        "day-1 return": analyze.compare(a["day_1"], a["readers"], b["day_1"], b["readers"]),
        "finish rate": analyze.compare(a["finished"], a["opened"], b["finished"], b["opened"]),
    }
    split_p = analyze.split_p_value(a["readers"], b["readers"])
    return {
        "seed": seed,
        "lift": lift,
        "estimate": day_7.difference,
        "low": day_7.low,
        "high": day_7.high,
        "p_value": day_7.p_value,
        "split_p": split_p,
        "decision": analyze.decide(split_p, day_7, guardrails),
    }


def run_all(runs: int, lift: float, first_seed: int = 1) -> pd.DataFrame:
    seeds = range(first_seed, first_seed + runs)
    with ProcessPoolExecutor() as pool:
        return pd.DataFrame(pool.map(one_run, seeds, [lift] * runs))


def true_effect(aa: pd.DataFrame, ab: pd.DataFrame) -> float:
    """The planted effect's true size: each A/B run minus its A/A twin (same seed), averaged."""
    twins = ab.set_index("seed").estimate - aa.set_index("seed").estimate
    return float(twins.dropna().mean())


def summary(aa: pd.DataFrame, ab: pd.DataFrame, truth: float | None = None) -> str:
    """The drill's scorecard, as Markdown."""
    if truth is None:
        truth = true_effect(aa, ab)

    def share(mask) -> str:
        return f"**{mask.mean():.1%}** ({int(mask.sum())} of {len(mask)})"

    switched_aa = aa.decision.str.startswith("Switch")
    worse_aa = aa.decision.str.contains("did worse")
    found_ab = ab.decision.str.startswith("Switch")
    covered = (ab.low <= truth) & (truth <= ab.high)
    split_alarm = pd.concat([aa, ab]).split_p < 0.001
    truth_points = f"+{truth * 100:.1f} points"
    rows = [
        ('A/A: wrongly says "switch to B"', "about 2.5% or less", switched_aa),
        ('A/A: wrongly says "B did worse"', "about 2.5% or less", worse_aa),
        ("A/A: any false alarm", "about 5% or less", switched_aa | worse_aa),
        ("A/B: finds that B is better (power)", "80% or more", found_ab),
        (f"A/B: interval holds the truth ({truth_points})", "about 95%", covered),
        ("Both: split alarm (p below 0.001)", "about 0.1%", split_alarm),
    ]
    lines = ["| Drill | What we want | What happened |", "|---|---|---|"]
    lines += [f"| {name} | {want} | {share(mask)} |" for name, want, mask in rows]
    lines += [
        "",
        f"A/B estimates averaged **{ab.estimate.mean() * 100:+.1f} points** "
        f"(the truth, from the twins, is {truth_points}); A/A estimates averaged "
        f"**{aa.estimate.mean() * 100:+.1f} points** (the truth is 0).",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    aa_runs = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    ab_runs = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    aa = run_all(aa_runs, lift=0.0)
    ab = run_all(ab_runs, lift=sim.WORDING_B_LIFT)
    print(summary(aa, ab))
    if (aa_runs, ab_runs) == (1000, 200):
        # Only the full drill replaces the committed record of every run
        out = Path("drill_runs.csv")
        pd.concat([aa, ab]).to_csv(out, index=False)
        print(f"\nEvery run's numbers: {out}")
    else:
        print("\nA quick drill: drill_runs.csv keeps the full drill's numbers.")
