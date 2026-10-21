

"""Tests for dates in the reader's own time zone."""

from datetime import UTC, date, datetime

from app.clock import local_today

# One fixed moment: 22:30 UTC on 21 October 2026
MOMENT = datetime(2026, 10, 21, 22, 30, tzinfo=UTC)


def test_lagos_is_still_the_21st():
    # Lagos is UTC+1, so it's 23:30 on the 21st there
    assert local_today("Africa/Lagos", MOMENT) == date(2026, 10, 21)


def test_kiritimati_is_already_the_22nd():
    # Kiritimati is UTC+14, so it's 12:30 on the 22nd there
    assert local_today("Pacific/Kiritimati", MOMENT) == date(2026, 10, 22)


def test_honolulu_is_the_afternoon_of_the_21st():
    # Honolulu is UTC-10, so it's 12:30 on the 21st there
    assert local_today("Pacific/Honolulu", MOMENT) == date(2026, 10, 21)
