

"""Tests for reading history (the days a reader finished a reading)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.clock import local_today
from app.models import PlanDay, ReadingSession, User
from app.streaks import reading_days

START, END = date(2026, 10, 1), date(2026, 10, 31)


@pytest.fixture
def me(db, reader):
    """The test reader's own row (found by the device this test registered)."""
    return db.scalar(select(User).where(User.device_id == "test-reader-device"))


def finish(db, me, world, *moments, completed=True):
    """Record readings by the test reader at the given moments (UTC)."""
    day = db.scalar(select(PlanDay).where(PlanDay.plan_id == world.id))
    for moment in moments:
        db.add(
            ReadingSession(
                user_id=me.id,
                plan_day_id=day.id,
                opened_at=moment,
                completed_at=moment if completed else None,
            )
        )
    db.flush()


def at(month, day, hour=6):
    return datetime(2026, month, day, hour, 0, tzinfo=UTC)


def test_each_reading_day_once_oldest_first(db, me, world):
    finish(db, me, world, at(10, 22), at(10, 20), at(10, 22, hour=18))

    assert reading_days(db, me, START, END) == [date(2026, 10, 20), date(2026, 10, 22)]


def test_days_outside_the_range_are_left_out(db, me, world):
    finish(db, me, world, at(9, 30), at(10, 1), at(10, 31), at(11, 1))

    assert reading_days(db, me, START, END) == [date(2026, 10, 1), date(2026, 10, 31)]


def test_days_follow_the_readers_time_zone(db, me, world):
    # 23:30 UTC on the 21st is already the 22nd in Lagos
    finish(db, me, world, datetime(2026, 10, 21, 23, 30, tzinfo=UTC))

    assert reading_days(db, me, START, END) == [date(2026, 10, 22)]


def test_unfinished_readings_are_left_out(db, me, world):
    finish(db, me, world, at(10, 22), completed=False)

    assert reading_days(db, me, START, END) == []


def test_history_endpoint_after_reading_today(client, reader):
    reading = client.post("/readings", headers=reader).json()
    client.post(f"/readings/{reading['id']}/complete", headers=reader)

    data = client.get("/users/me/history", headers=reader).json()

    today = local_today("Africa/Lagos")
    assert data["end"] == today.isoformat()
    assert data["start"] == (today - timedelta(days=90)).isoformat()
    assert data["days"] == [today.isoformat()]


def test_history_length_can_be_chosen(client, reader):
    data = client.get("/users/me/history?days=7", headers=reader).json()

    today = local_today("Africa/Lagos")
    assert data["start"] == (today - timedelta(days=6)).isoformat()
    assert data["days"] == []


@pytest.mark.parametrize("days", [0, 367])
def test_history_length_is_checked(client, reader, days):
    assert client.get(f"/users/me/history?days={days}", headers=reader).status_code == 422


def test_history_needs_a_token(client):
    assert client.get("/users/me/history").status_code == 401
