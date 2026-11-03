"""The analysis, checked on made-up numbers with known answers, before it ever saw the real data."""

from datetime import date

import pandas as pd
import pytest

from analyze import Comparison, at_the_look, bayes, compare, decide, report, split_p_value


def test_an_even_split_is_perfectly_fine():
    assert split_p_value(500, 500) == pytest.approx(1.0)


def test_split_matches_the_textbook():
    # 60 vs 40: chi-square = 4 with 1 degree of freedom, p = 0.0455
    assert split_p_value(60, 40) == pytest.approx(0.0455, abs=1e-4)


def test_z_test_matches_working_it_out_by_hand():
    # 20% vs 25% of 1,000 each: pooled 22.5%, z = 0.05 / 0.018675 = 2.677, p = 0.0074
    c = compare(200, 1000, 250, 1000)
    assert c.difference == pytest.approx(0.05)
    assert c.z == pytest.approx(2.677, abs=1e-3)
    assert c.p_value == pytest.approx(0.0074, abs=1e-4)
    # Interval: 0.05 ± 1.96 × 0.018641
    assert c.low == pytest.approx(0.0135, abs=1e-4)
    assert c.high == pytest.approx(0.0865, abs=1e-4)


def test_swapping_the_groups_flips_the_sign_only():
    ab, ba = compare(200, 1000, 250, 1000), compare(250, 1000, 200, 1000)
    assert ba.difference == pytest.approx(-ab.difference)
    assert ba.p_value == pytest.approx(ab.p_value)
    assert (ba.low, ba.high) == pytest.approx((-ab.high, -ab.low))


def test_identical_perfect_rates_are_no_evidence():
    # 100% vs 100%: nothing varies, so there's nothing to test (and no dividing by zero)
    c = compare(50, 50, 80, 80)
    assert (c.difference, c.z, c.p_value) == (0.0, 0.0, 1.0)


def test_bayes_with_identical_groups_is_a_coin_toss():
    view = bayes(300, 1000, 300, 1000)
    assert view.chance_b_better == pytest.approx(0.5, abs=0.01)
    assert view.lift_median == pytest.approx(0.0, abs=0.002)


def test_bayes_sees_a_clear_lift_and_is_repeatable():
    view = bayes(200, 1000, 300, 1000)
    assert view.chance_b_better > 0.999
    assert view.lift_low < 0.1 < view.lift_high
    assert bayes(200, 1000, 300, 1000) == view  # the fixed seed gives the same numbers


def comparison(difference, low, high, p):
    return Comparison(0.4, 0.4 + difference, difference, 0.0, p, low, high)


FINE = {
    "day-1 return": comparison(0.0, -0.03, 0.03, 0.9),
    "finish rate": comparison(0.0, -0.01, 0.01, 0.9),
}


@pytest.mark.parametrize(
    ("split_p", "day_7", "guardrails", "starts"),
    [
        (0.5, comparison(0.06, 0.03, 0.09, 0.0001), FINE, "Switch every reader to wording B"),
        (0.5, comparison(0.01, -0.02, 0.04, 0.4), FINE, "Keep wording A: no clear difference"),
        (0.5, comparison(-0.06, -0.09, -0.03, 0.0001), FINE, "Keep wording A: B did worse"),
        (0.0001, comparison(0.06, 0.03, 0.09, 0.0001), FINE, "Stop"),
        (
            0.5,
            comparison(0.06, 0.03, 0.09, 0.0001),
            {**FINE, "finish rate": comparison(-0.03, -0.05, -0.01, 0.001)},
            "Keep wording A: B won on day 7, but finish rate dropped",
        ),
    ],
)
def test_the_decision_table(split_p, day_7, guardrails, starts):
    assert decide(split_p, day_7, guardrails).startswith(starts)


def test_a_guardrail_dip_within_2_points_is_allowed():
    dip = {**FINE, "day-1 return": comparison(-0.019, -0.05, 0.01, 0.2)}
    decision = decide(0.5, comparison(0.06, 0.03, 0.09, 0.0001), dip)
    assert decision == "Switch every reader to wording B"


def readers(rows):
    """Made-up readers: (group, signup day of October, has reached day 7, read on day 7)."""
    return pd.DataFrame(
        [
            {
                "user_key": f"r{n}",
                "reminder_variant": group,
                "signed_up_on": date(2026, 10, day),
                "can_have_day_7": reached,
                "read_day_1": read,
                "read_day_7": read,
                "first_week_opened": 2,
                "first_week_finished": 2,
            }
            for n, (group, day, reached, read) in enumerate(rows)
        ]
    )


def test_the_look_waits_for_both_groups():
    toy = readers(
        [
            ("A", 1, True, True),
            ("A", 2, True, False),
            ("B", 2, True, True),
            ("B", 3, True, False),
            ("A", 4, True, True),
            ("B", 5, False, False),
        ]
    )
    counted, last_day = at_the_look(toy, per_group=2)
    # A reaches 2 on the 2nd, B only on the 3rd: everyone who joined up to the 3rd is counted
    assert last_day == date(2026, 10, 3)
    assert sorted(counted.user_key) == ["r0", "r1", "r2", "r3"]


def test_no_look_before_the_planned_size():
    toy = readers([("A", 1, True, True), ("B", 1, True, True)])
    counted, last_day = at_the_look(toy, per_group=2)
    assert last_day is None and counted.empty
    assert report(toy).startswith("Not yet")


def test_the_report_follows_the_plan_s_order():
    toy = readers(
        [("A", 1, True, n % 2 == 0) for n in range(1600)]
        + [("B", 1, True, n % 2 == 0) for n in range(1600)]
    )
    text = report(toy)
    assert text.index("The look") < text.index("The split") < text.index("Day-7 return")
    assert text.index("Day-7 return") < text.index("Bayesian") < text.index("The decision")
    assert "Keep wording A: no clear difference" in text
