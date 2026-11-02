"""How many readers an A/B test needs, worked out before it starts.

Run it from this folder to print the table in the pre-registration:
    python power.py

The maths is the standard one for comparing two proportions (a two-sided z-test): enough
readers that a real lift of the chosen size would be spotted 80% of the time, while a lift
that isn't there would be "found" only 5% of the time.
"""

from math import ceil, sqrt
from statistics import NormalDist

_z = NormalDist().inv_cdf


def readers_per_group(baseline: float, lift: float, alpha: float = 0.05, power: float = 0.8) -> int:
    """New readers needed in each group to detect `lift` (in proportion points) over `baseline`.

    baseline: the share who come back today, e.g. 0.376
    lift:     the smallest improvement worth finding, e.g. 0.05 for +5 points
    alpha:    how often we'd "find" a lift that isn't there (5%)
    power:    how often we'd find a lift that is there (80%)
    """
    if not 0 < baseline < 1 or not 0 < baseline + lift < 1 or lift == 0:
        raise ValueError("baseline and baseline + lift must both be between 0 and 1, lift not 0")
    treated = baseline + lift
    pooled = (baseline + treated) / 2
    spread_if_no_lift = _z(1 - alpha / 2) * sqrt(2 * pooled * (1 - pooled))
    spread_if_lift = _z(power) * sqrt(baseline * (1 - baseline) + treated * (1 - treated))
    return ceil(((spread_if_no_lift + spread_if_lift) / lift) ** 2)


def table(baseline: float, lifts: list[float]) -> str:
    """The sample sizes for several lifts, as a Markdown table."""
    rows = ["| Smallest lift | Day-7 return | Per group | Both groups |", "|---|---|---|---|"]
    for lift in lifts:
        n = readers_per_group(baseline, lift)
        rows.append(
            f"| +{lift * 100:.0f} points | {baseline:.1%} → {baseline + lift:.1%} "
            f"| {n:,} | {2 * n:,} |"
        )
    return "\n".join(rows)


if __name__ == "__main__":
    # Day-7 return today, from the 6.1 notebook and fct_retention_cohorts
    print(table(0.376, [0.03, 0.05, 0.08]))
