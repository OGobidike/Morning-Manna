"""The sample-size maths, checked against known answers and common sense."""

import pytest

from power import readers_per_group, table


def test_matches_the_textbook():
    # 50% vs 60%, 5% two-sided, 80% power: 388 per group (Fleiss, no continuity correction)
    assert readers_per_group(0.5, 0.1) == 388


def test_our_pre_registered_number():
    # Day-7 return of 37.6%, smallest lift worth finding +5 points
    assert readers_per_group(0.376, 0.05) == 1508


def test_smaller_lifts_need_more_readers():
    assert readers_per_group(0.376, 0.03) > readers_per_group(0.376, 0.05)
    assert readers_per_group(0.376, 0.05) > readers_per_group(0.376, 0.08)


def test_more_certainty_costs_more_readers():
    assert readers_per_group(0.376, 0.05, power=0.9) > readers_per_group(0.376, 0.05)
    assert readers_per_group(0.376, 0.05, alpha=0.01) > readers_per_group(0.376, 0.05)


def test_a_drop_is_as_hard_to_find_as_a_rise():
    # The test is two-sided: it would catch wording B doing worse, too
    assert readers_per_group(0.5, -0.1) == readers_per_group(0.5, 0.1)


@pytest.mark.parametrize("baseline, lift", [(0, 0.05), (0.98, 0.05), (0.4, 0)])
def test_impossible_inputs_are_refused(baseline, lift):
    with pytest.raises(ValueError):
        readers_per_group(baseline, lift)


def test_the_table_for_the_pre_registration():
    lines = table(0.376, [0.05]).splitlines()
    assert lines[2] == "| +5 points | 37.6% → 42.6% | 1,508 | 3,016 |"
