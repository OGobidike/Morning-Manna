"""The reminder experiment's analysis, following the rules written down before it began.

The rules are in docs/analysis/reminder-experiment.md. This file applies them, in their order:

    1. Look once, when both groups have 1,508 readers who've reached their day 7.
    2. Check the split: a chi-square test against 50/50 (p below 0.001 means stop and fix).
    3. Decide on day-7 return: a two-sided two-proportion z-test with a 95% confidence
       interval, and the two guardrails (day-1 return and finish rate).
    4. A Bayesian second view, for understanding only: it never changes the decision.

Run it from this folder after dbt build, to print the result as Markdown:
    python analyze.py

Three details the written plan left open were fixed here before anyone saw the result:
    - "1,508 readers who've reached their day 7" is counted by signup day: the analysis takes
      everyone who joined up to the first day by which both groups have that many.
    - A guardrail "drops by more than 2 points" when B minus A is below -2.0 points.
    - If B wins on day 7 but a guardrail drops, wording A stays.
"""

import os
from dataclasses import dataclass
from math import erfc, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd
from sqlalchemy import Engine, create_engine, text

PER_GROUP = 1508  # from power.py, fixed in the pre-registration
SPLIT_ALARM = 0.001  # a split this unlikely means the coin is broken
SIGNIFICANCE = 0.05
GUARDRAIL_DROP = 0.02  # 2 points
BAYES_DRAWS = 200_000
BAYES_SEED = 2026  # fixed, so the Bayesian numbers come out the same every run

_normal = NormalDist()


# ---- The statistics: plain functions, checked against known answers in the tests ----------


def split_p_value(readers_a: int, readers_b: int) -> float:
    """Chi-square test of the split against 50/50 (1 degree of freedom)."""
    expected = (readers_a + readers_b) / 2
    chi2 = ((readers_a - expected) ** 2 + (readers_b - expected) ** 2) / expected
    return erfc(sqrt(chi2 / 2))  # the chi-square(1) tail, without needing scipy


@dataclass(frozen=True)
class Comparison:
    """One measure compared between the groups: B minus A, with its test and interval."""

    rate_a: float
    rate_b: float
    difference: float  # B minus A, as a proportion (0.05 is 5 points)
    z: float
    p_value: float
    low: float  # 95% confidence interval for the difference
    high: float


def compare(successes_a: int, total_a: int, successes_b: int, total_b: int) -> Comparison:
    """Two-proportion z-test (two-sided) and a 95% confidence interval for B minus A.

    The test uses the pooled rate (what the rates would share if there were no difference);
    the interval uses each group's own rate, as is standard.
    """
    rate_a, rate_b = successes_a / total_a, successes_b / total_b
    difference = rate_b - rate_a
    pooled = (successes_a + successes_b) / (total_a + total_b)
    pooled_se = sqrt(pooled * (1 - pooled) * (1 / total_a + 1 / total_b))
    # Everyone did the same thing in both groups (all or none): no spread, so no evidence
    z = difference / pooled_se if pooled_se else 0.0
    p_value = 2 * (1 - _normal.cdf(abs(z)))
    se = sqrt(rate_a * (1 - rate_a) / total_a + rate_b * (1 - rate_b) / total_b)
    margin = _normal.inv_cdf(1 - SIGNIFICANCE / 2) * se
    low, high = difference - margin, difference + margin
    return Comparison(rate_a, rate_b, difference, z, p_value, low, high)


@dataclass(frozen=True)
class Bayes:
    """The Bayesian view: how likely B beats A, and how big the lift probably is."""

    chance_b_better: float
    lift_median: float
    lift_low: float  # 95% credible interval for B minus A
    lift_high: float


def bayes(successes_a: int, total_a: int, successes_b: int, total_b: int) -> Bayes:
    """Beta-Binomial with a flat Beta(1, 1) start (no opinion), by drawing from each posterior."""
    rng = np.random.default_rng(BAYES_SEED)
    a = rng.beta(1 + successes_a, 1 + total_a - successes_a, BAYES_DRAWS)
    b = rng.beta(1 + successes_b, 1 + total_b - successes_b, BAYES_DRAWS)
    lift = b - a
    low, median, high = np.quantile(lift, [0.025, 0.5, 0.975])
    return Bayes(float((lift > 0).mean()), float(median), float(low), float(high))


def decide(split_p: float, day_7: Comparison, guardrails: dict[str, Comparison]) -> str:
    """The pre-registered decision table, as one sentence."""
    if split_p < SPLIT_ALARM:
        return "Stop: the split is too far from 50/50, so fix the assignment before trusting this"
    dropped = [name for name, c in guardrails.items() if c.difference < -GUARDRAIL_DROP]
    if day_7.p_value < SIGNIFICANCE and day_7.low > 0:
        if dropped:
            return f"Keep wording A: B won on day 7, but {' and '.join(dropped)} dropped"
        return "Switch every reader to wording B"
    if day_7.p_value < SIGNIFICANCE and day_7.high < 0:
        return "Keep wording A: B did worse"
    return "Keep wording A: no clear difference"


# ---- The data ------------------------------------------------------------------------------


def readers_in_test(engine: Engine) -> pd.DataFrame:
    """Every reader in the experiment (one row each), from the dbt table."""
    with engine.connect() as connection:
        return pd.read_sql(
            text(
                """
                select user_key, reminder_variant, signed_up_on, can_have_day_7,
                       read_day_1, read_day_7, first_week_opened, first_week_finished
                from analytics.fct_experiment
                """
            ),
            connection,
        )


def at_the_look(readers: pd.DataFrame, per_group: int = PER_GROUP) -> tuple[pd.DataFrame, object]:
    """The readers counted at the planned look, and the last signup day among them.

    The look happens on the first signup day by which both groups have `per_group` readers
    who have reached day 7. Returns no readers if that day hasn't come yet.
    """
    reached = readers[readers.can_have_day_7]
    counts = (
        reached.groupby(["signed_up_on", "reminder_variant"])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=["A", "B"], fill_value=0)
        .sort_index()
        .cumsum()
    )
    ready = counts[(counts.A >= per_group) & (counts.B >= per_group)]
    if ready.empty:
        return reached.iloc[0:0], None
    last_day = ready.index[0]
    return reached[reached.signed_up_on <= last_day], last_day


def tally(readers: pd.DataFrame, group: str) -> dict[str, int]:
    """The counts each measure needs, for one group."""
    g = readers[readers.reminder_variant == group]
    return {
        "readers": len(g),
        "day_1": int(g.read_day_1.sum()),
        "day_7": int(g.read_day_7.sum()),
        "opened": int(g.first_week_opened.sum()),
        "finished": int(g.first_week_finished.sum()),
    }


# ---- The report ----------------------------------------------------------------------------


def points(x: float) -> str:
    return f"{x * 100:+.1f} points"


def report(readers: pd.DataFrame) -> str:
    """The whole analysis, as Markdown, in the pre-registered order."""
    counted, last_day = at_the_look(readers)
    if last_day is None:
        return f"Not yet: the look waits until both groups have {PER_GROUP:,} readers at day 7."

    a, b = tally(counted, "A"), tally(counted, "B")
    split_p = split_p_value(a["readers"], b["readers"])
    day_7 = compare(a["day_7"], a["readers"], b["day_7"], b["readers"])
    guardrails = {
        "day-1 return": compare(a["day_1"], a["readers"], b["day_1"], b["readers"]),
        "finish rate": compare(a["finished"], a["opened"], b["finished"], b["opened"]),
    }
    view = bayes(a["day_7"], a["readers"], b["day_7"], b["readers"])
    decision = decide(split_p, day_7, guardrails)

    def row(name: str, c: Comparison) -> str:
        return (
            f"| {name} | {c.rate_a:.1%} | {c.rate_b:.1%} | **{points(c.difference)}** "
            f"| {points(c.low)} to {points(c.high)} | {c.p_value:.4f} |"
        )

    lines = [
        f"**The look:** readers who joined up to {last_day}, "
        f"**{a['readers']:,}** in A and **{b['readers']:,}** in B.",
        "",
        f"**The split:** chi-square p = {split_p:.3f} "
        + ("(fine: above 0.001)" if split_p >= SPLIT_ALARM else "(**broken**: below 0.001)"),
        "",
        "| Measure | A | B | B minus A | 95% interval | p |",
        "|---|---|---|---|---|---|",
        row("🎯 Day-7 return", day_7),
        row("🛡️ Day-1 return", guardrails["day-1 return"]),
        row("🛡️ Finish rate", guardrails["finish rate"]),
        "",
        f"**The Bayesian view (for understanding only):** a {view.chance_b_better:.1%} chance "
        f"that B beats A on day 7, with the lift most likely {points(view.lift_median)} "
        f"(95% credible interval {points(view.lift_low)} to {points(view.lift_high)}).",
        "",
        f"**The decision:** {decision}.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    # The local docker database unless DATABASE_URL says otherwise
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    print(report(readers_in_test(create_engine(url))))
