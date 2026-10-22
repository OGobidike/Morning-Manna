

"""Tests for POST /events (batches of app events)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.models import Event, User


def my_event_count(db):
    """How many events belong to the test reader (never anyone else's)."""
    return db.scalar(
        select(func.count())
        .select_from(Event)
        .join(User, User.id == Event.user_id)
        .where(User.device_id == "test-reader-device")
    )


def event(event_type="app_opened", occurred_at="2026-10-22T06:00:00Z", **properties):
    return {"event_type": event_type, "occurred_at": occurred_at, "properties": properties}


def send(client, headers, *events):
    return client.post("/events", json={"events": list(events)}, headers=headers)


def test_a_batch_is_stored(client, db, headers):
    response = send(client, headers, event(), event("reminder_snoozed", minutes=10))

    assert response.status_code == 201
    assert response.json() == {"accepted": 2}
    assert my_event_count(db) == 2


def test_properties_are_kept(client, db, headers):
    send(client, headers, event("reminder_snoozed", minutes=10))

    stored = db.scalar(
        select(Event)
        .join(User, User.id == Event.user_id)
        .where(User.device_id == "test-reader-device")
    )
    assert stored.event_type == "reminder_snoozed"
    assert stored.properties == {"minutes": 10}


def test_unknown_event_type_is_422(client, db, headers):
    response = send(client, headers, event("app_exploded"))

    assert response.status_code == 422
    assert my_event_count(db) == 0


def test_one_bad_event_rejects_the_whole_batch(client, db, headers):
    response = send(client, headers, event(), event("app_exploded"), event())

    assert response.status_code == 422
    assert my_event_count(db) == 0


def test_time_without_a_time_zone_is_422(client, headers):
    response = send(client, headers, event(occurred_at="2026-10-22T06:00:00"))

    assert response.status_code == 422


def test_time_in_the_future_is_422(client, headers):
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).isoformat()

    response = send(client, headers, event(occurred_at=tomorrow))

    assert response.status_code == 422


def test_empty_batch_is_422(client, headers):
    assert send(client, headers).status_code == 422


def test_batch_of_more_than_100_is_422(client, headers):
    assert send(client, headers, *[event()] * 101).status_code == 422


def test_events_need_a_token(client):
    assert client.post("/events", json={"events": [event()]}).status_code == 401
