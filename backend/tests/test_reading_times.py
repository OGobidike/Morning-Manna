

"""Tests for reported reading times: when a reading really happened (e.g. while offline)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

LAGOS = ZoneInfo("Africa/Lagos")


def iso(moment: datetime) -> str:
    return moment.isoformat()


def open_reading(client, reader, opened_at=None):
    body = None if opened_at is None else {"opened_at": iso(opened_at)}
    return client.post("/readings", json=body, headers=reader)


def complete(client, reader, reading_id, completed_at=None):
    body = None if completed_at is None else {"completed_at": iso(completed_at)}
    return client.post(f"/readings/{reading_id}/complete", json=body, headers=reader)


def yesterday_morning() -> datetime:
    """07:10 yesterday, in Lagos (the test reader's time zone)."""
    yesterday = datetime.now(LAGOS) - timedelta(days=1)
    return yesterday.replace(hour=7, minute=10, second=0, microsecond=0)


def test_reported_times_are_kept(client, reader):
    opened = yesterday_morning()
    finished = opened + timedelta(minutes=6)

    reading = open_reading(client, reader, opened).json()
    done = complete(client, reader, reading["id"], finished).json()

    assert datetime.fromisoformat(done["opened_at"]) == opened
    assert datetime.fromisoformat(done["completed_at"]) == finished


def test_a_reading_synced_late_counts_on_the_day_it_happened(client, reader):
    # Read offline yesterday at 07:10, synced only now
    opened = yesterday_morning()
    reading = open_reading(client, reader, opened).json()
    complete(client, reader, reading["id"], opened + timedelta(minutes=6))

    history = client.get("/users/me/history?days=7", headers=reader).json()

    assert history["days"] == [opened.date().isoformat()]


def test_without_a_body_the_time_is_now(client, reader):
    before = datetime.now(UTC)

    reading = open_reading(client, reader).json()
    done = complete(client, reader, reading["id"]).json()

    assert datetime.fromisoformat(done["opened_at"]) >= before
    assert datetime.fromisoformat(done["completed_at"]) >= before


@pytest.mark.parametrize(
    "moment",
    [
        datetime.now(UTC) + timedelta(hours=1),  # in the future
        datetime.now(UTC) - timedelta(days=15),  # too long ago to be an offline reading
    ],
)
def test_unbelievable_times_are_refused(client, reader, moment):
    assert open_reading(client, reader, moment).status_code == 422


def test_a_time_without_a_time_zone_is_refused(client, reader):
    response = client.post("/readings", json={"opened_at": "2026-10-25T07:10:00"}, headers=reader)

    assert response.status_code == 422


def test_a_reading_cannot_end_before_it_began(client, reader):
    opened = yesterday_morning()
    reading = open_reading(client, reader, opened).json()

    response = complete(client, reader, reading["id"], opened - timedelta(minutes=1))

    assert response.status_code == 422
    # Nothing changed: still on day 1, still unfinished
    assert client.get("/today", headers=reader).json()["day_number"] == 1
