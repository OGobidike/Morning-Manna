"""The reminder experiment: which wording of the morning reminder each reader gets.

The rules are in docs/analysis/reminder-experiment.md, written before the test began.
"""

import secrets

# A is the reminder readers have always had, B is the new wording being tested
VARIANTS = ("A", "B")


def assign_variant() -> str:
    """A fair coin flip, "A" or "B", made once when a reader signs up and kept for good.

    secrets draws from the operating system's randomness, so nothing about the reader
    (their id, their device, the time they signed up) can steer which group they land in.
    """
    return secrets.choice(VARIANTS)
