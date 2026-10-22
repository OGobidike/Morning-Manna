

"""Tests for reading streaks (mornings in a row, in the reader's own time zone)."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models import PlanDay, ReadingSession, User
from app.streaks import streaks

TODAY = date(2026, 10, 22)


@pytest.fixture
def me(db, reader):
    """The test reader's own row (found by the device this test registered)."""
    return db.scalar(select(User).where(User.device_id == "test-reader-device"))


def finished_at(db, me, world, *moments):
    """Record readings by the test reader, finished at the given moments (UTC)."""
    day = db.scalar(select(PlanDay).where(PlanDay.plan_id == world.id))
    for moment in moments:
        db.add(
            ReadingSession(
                user_id=me.id, plan_day_id=day.id, opened_at=moment, completed_at=moment
            )
        )
    db.flush()


def morning(year, month, day):
    """7am in Lagos (6am UTC) on a given day."""
    return datetime(year, month, day, 6, 0, tzinfo=UTC)


def test_no_readings_is_no_streak(db, me):
    assert streaks(db, me, TODAY) == (0, 0, None)


def test_three_mornings_in_a_row(db, me, world):
    finished_at(db, me, world, morning(2026, 10, 20), morning(2026, 10, 21), morning(2026, 10, 22))

    assert streaks(db, me, TODAY) == (3, 3, date(2026, 10, 22))


def test_streak_survives_until_today_ends(db, me, world):
    # Read yesterday and the day before, not yet today: still a 2-day streak
    finished_at(db, me, world, morning(2026, 10, 20), morning(2026, 10, 21))

    assert streaks(db, me, TODAY) == (2, 2, date(2026, 10, 21))


def test_a_missed_day_breaks_the_streak(db, me, world):
    finished_at(db, me, world, morning(2026, 10, 18), morning(2026, 10, 19), morning(2026, 10, 20))

    current, longest, _ = streaks(db, me, TODAY)

    assert current == 0
    assert longest == 3


def test_longest_and_current_can_differ(db, me, world):
    # 15, 16, 17 then a gap, then 21, 22
    finished_at(
        db,
        me,
        world,
        morning(2026, 10, 15),
        morning(2026, 10, 16),
        morning(2026, 10, 17),
        morning(2026, 10, 21),
        morning(2026, 10, 22),
    )

    assert streaks(db, me, TODAY) == (2, 3, date(2026, 10, 22))


def test_two_readings_in_one_day_count_once(db, me, world):
    finished_at(db, me, world, morning(2026, 10, 22), datetime(2026, 10, 22, 18, 0, tzinfo=UTC))

    assert streaks(db, me, TODAY) == (1, 1, date(2026, 10, 22))


def test_days_follow_the_readers_time_zone(db, me, world):
    # 23:30 UTC on the 21st is already 00:30 on the 22nd in Lagos
    finished_at(db, me, world, datetime(2026, 10, 21, 23, 30, tzinfo=UTC))

    assert streaks(db, me, TODAY) == (1, 1, date(2026, 10, 22))


def test_unfinished_readings_do_not_count(db, me, world):
    day = db.scalar(select(PlanDay).where(PlanDay.plan_id == world.id))
    db.add(ReadingSession(user_id=me.id, plan_day_id=day.id, opened_at=morning(2026, 10, 22)))
    db.flush()

    assert streaks(db, me, TODAY) == (0, 0, None)


def test_streak_endpoint_after_finishing_today(client, reader):
    reading = client.post("/readings", headers=reader).json()
    client.post(f"/readings/{reading['id']}/complete", headers=reader)

    data = client.get("/users/me/streak", headers=reader).json()

    assert data["current"] == 1
    assert data["longest"] == 1


def test_streak_needs_a_token(client):
    assert client.get("/users/me/streak").status_code == 401
