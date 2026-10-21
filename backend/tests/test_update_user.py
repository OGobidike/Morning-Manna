

"""Tests for PATCH /users/me (changing a reader's settings)."""

import pytest

from app.models import Translation


@pytest.fixture
def headers(client, db):
    """Register a test device and return the headers that prove who it is."""
    db.add(Translation(code="TST", name="Test Translation", license="Public domain"))
    db.flush()
    response = client.post(
        "/users",
        json={
            "device_id": "patch-test-device",
            "timezone": "Europe/London",
            "wake_time": "06:30",
            "translation": "TST",
        },
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_change_only_the_wake_time(client, headers):
    response = client.patch("/users/me", json={"wake_time": "05:45"}, headers=headers)

    assert response.status_code == 200
    assert response.json()["wake_time"] == "05:45:00"
    # The time zone wasn't sent, so it stays as it was
    assert response.json()["timezone"] == "Europe/London"


def test_change_the_time_zone(client, headers):
    response = client.patch("/users/me", json={"timezone": "Africa/Lagos"}, headers=headers)

    assert response.json()["timezone"] == "Africa/Lagos"
    assert response.json()["wake_time"] == "06:30:00"


def test_change_is_saved(client, headers):
    client.patch("/users/me", json={"wake_time": "05:45"}, headers=headers)

    assert client.get("/users/me", headers=headers).json()["wake_time"] == "05:45:00"


def test_unknown_time_zone_is_rejected(client, headers):
    response = client.patch("/users/me", json={"timezone": "Mars/Olympus"}, headers=headers)

    assert response.status_code == 422


def test_update_needs_a_token(client):
    response = client.patch("/users/me", json={"wake_time": "05:45"})

    assert response.status_code == 401
