

"""Tests for POST /users (registering a device)."""

import pytest
from sqlalchemy import select

from app.models import Translation, User
from app.security import hash_token


@pytest.fixture
def translation(db):
    """A translation for test users to read in (CI's database starts empty)."""
    translation = Translation(code="TST", name="Test Translation", license="Public domain")
    db.add(translation)
    db.flush()
    return translation


def register(client, **changes):
    """Send a valid registration, with any fields changed for the test."""
    body = {
        "device_id": "test-device-0001",
        "timezone": "Africa/Lagos",
        "wake_time": "05:30",
        "translation": "TST",
    }
    body.update(changes)
    return client.post("/users", json=body)


def test_register_returns_201_and_a_token(client, translation):
    response = register(client)

    assert response.status_code == 201
    data = response.json()
    assert data["timezone"] == "Africa/Lagos"
    assert data["wake_time"] == "05:30:00"
    assert len(data["token"]) >= 40


def test_database_stores_the_hash_not_the_token(client, db, translation):
    token = register(client).json()["token"]

    user = db.scalar(select(User).where(User.device_id == "test-device-0001"))
    assert user.token_hash == hash_token(token)
    assert user.token_hash != token


def test_unknown_time_zone_is_rejected(client, translation):
    response = register(client, timezone="Mars/Olympus")

    assert response.status_code == 422


def test_unknown_translation_is_rejected(client, translation):
    response = register(client, translation="XYZ")

    assert response.status_code == 400


def test_same_device_cannot_register_twice(client, translation):
    register(client)
    response = register(client)

    assert response.status_code == 409
