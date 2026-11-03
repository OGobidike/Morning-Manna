"""The reminder experiment's answer key: what wording B's planted effect is really worth.

simulate.py gives wording B a planted effect (WORDING_B_LIFT). The analysis never reads it
(analytics/experiments/analyze.py). This script measures the effect's true size on day-7
return, so the analysis's estimate can be checked against the truth.

How: it simulates the same readers twice, with the effect and without it. Each reader keeps
their own random stream, so the only difference between the two runs is the effect itself.
A reader who comes back on day 7 with it, but not without it, was brought back by wording B.

Run it from the repo root (it takes a few minutes):
    python ml/true_effect.py
"""

from datetime import date, datetime, timedelta
from math import sqrt
from zoneinfo import ZoneInfo

import simulate as sim

END = date(2026, 10, 27)  # the same 90 days CI and the warehouse use
THE_LOOK = date(2026, 10, 9)  # the analysis looked at everyone who joined up to here


def read_on_day_7(readers: list[sim.Reader], events: list[dict]) -> dict[str, bool]:
    """Whether each reader finished a reading on the 7th day after joining, in their own time."""
    zone = {r.user_key: ZoneInfo(r.timezone) for r in readers}
    day_7 = {r.user_key: date.fromisoformat(r.signed_up_on) + timedelta(days=7) for r in readers}
    returned = dict.fromkeys(day_7, False)
    for e in events:
        if e["event_type"] == "reading_completed":
            key = e["user_key"]
            when = datetime.fromisoformat(e["occurred_at"]).astimezone(zone[key]).date()
            if when == day_7[key]:
                returned[key] = True
    return returned


def with_and_without(readers: int, days: int, end: date, seed: int):
    """The same readers' day-7 returns with wording B's effect, and as if it had none."""
    planted = sim.WORDING_B_LIFT
    people, events = sim.simulate(readers, days, end, seed)
    with_effect = read_on_day_7(people, events)
    sim.WORDING_B_LIFT = 0.0
    try:
        _, events = sim.simulate(readers, days, end, seed)
    finally:
        sim.WORDING_B_LIFT = planted  # put the answer key back the way it was
    return people, with_effect, read_on_day_7(people, events)


def reached_day_7(reader: sim.Reader, end: date, joined_by: date | None = None) -> bool:
    joined = date.fromisoformat(reader.signed_up_on)
    return joined + timedelta(days=7) <= end and (joined_by is None or joined <= joined_by)


def true_effect(people, with_effect, without, end: date, joined_by: date | None = None):
    """Among group B readers who reached day 7: the share brought back by the effect.

    Returns the effect, its 95% margin, and how many readers it rests on. Every reader's
    difference is +1 (brought back), -1 (put off) or 0 (no change), and the effect is their
    average: what wording B did to day-7 return.
    """
    b = [r.user_key for r in people
         if r.reminder_variant == "B" and reached_day_7(r, end, joined_by)]
    differences = [int(with_effect[k]) - int(without[k]) for k in b]
    mean = sum(differences) / len(differences)
    spread = sqrt(sum((d - mean) ** 2 for d in differences) / (len(differences) - 1))
    return mean, 1.96 * spread / sqrt(len(differences)), len(differences)


def group_rates(people, returned, end: date, joined_by: date):
    """Day-7 return per group at the analysis's look, to check this script counts as dbt does."""
    rates = {}
    for group in ("A", "B"):
        keys = [r.user_key for r in people
                if r.reminder_variant == group and reached_day_7(r, end, joined_by)]
        rates[group] = (sum(returned[k] for k in keys), len(keys))
    return rates


def points(x: float) -> str:
    return f"{x * 100:+.1f} points"


if __name__ == "__main__":
    print(f"The planted effect: WORDING_B_LIFT = {sim.WORDING_B_LIFT} (a daily reading chance, "
          "for group B readers with reminders on)\n")

    # 1. This practice run: the 5,000 readers the analysis saw
    people, with_effect, without = with_and_without(5000, 90, END, 7)
    for group, (came_back, total) in group_rates(people, with_effect, END, THE_LOOK).items():
        print(f"Check, group {group} at the look: {came_back} of {total} came back on day 7")
    effect, margin, n = true_effect(people, with_effect, without, END, THE_LOOK)
    print(f"In this practice run: wording B brought back {points(effect)} "
          f"(± {margin * 100:.1f}, from {n:,} group B readers)")

    # 2. The long run: 20,000 readers, so the effect is pinned down tightly
    people, with_effect, without = with_and_without(20_000, 90, END, 7)
    effect, margin, n = true_effect(people, with_effect, without, END)
    print(f"In the long run: wording B is worth {points(effect)} on day-7 return "
          f"(± {margin * 100:.1f}, from {n:,} group B readers)")
