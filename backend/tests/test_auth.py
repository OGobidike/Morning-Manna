

"""Tests for authentication with a device token (GET /users/me)."""

import pytest

from app.models import Translation


@pytest.fixture
def token(client, db):
    """Register a test device and return its token."""
    db.add(Translation(code="TST", name="Test Translation", license="Public domain"))
    db.flush()
    response = client.post(
        "/users",
        json={
            "device_id": "auth-test-device",
            "timezone": "Europe/London",
            "wake_time": "06:30",
            "translation": "TST",
        },
    )
    return response.json()["token"]


def test_me_with_a_valid_token(client, token):
    response = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/London"
    assert "token" not in response.json()


def test_me_without_a_token_is_401(client):
    response = client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_with_a_wrong_token_is_401(client, token):
    response = client.get("/users/me", headers={"Authorization": "Bearer not-the-real-token"})

    assert response.status_code == 401


def test_me_with_the_wrong_scheme_is_401(client, token):
    response = client.get("/users/me", headers={"Authorization": f"Basic {token}"})

    assert response.status_code == 401
