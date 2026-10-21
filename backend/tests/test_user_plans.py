

"""Tests for POST /users/me/plans (starting a reading plan)."""

import pytest

from app.clock import local_today
from app.models import ReadingPlan, Translation


@pytest.fixture
def headers(client, db):
    """Register a test device and return the headers that prove who it is."""
    db.add(Translation(code="TST", name="Test Translation", license="Public domain"))
    db.flush()
    response = client.post(
        "/users",
        json={
            "device_id": "plans-test-device",
            "timezone": "Africa/Lagos",
            "wake_time": "06:00",
            "translation": "TST",
        },
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def plan(db):
    """A reading plan to start."""
    plan = ReadingPlan(name="Test Plan", description="For tests")
    db.add(plan)
    db.flush()
    return plan


def test_start_a_plan(client, headers, plan):
    response = client.post("/users/me/plans", json={"plan_id": plan.id}, headers=headers)

    assert response.status_code == 201
    data = response.json()
    assert data["plan_id"] == plan.id
    assert data["current_day"] == 1
    assert data["start_date"] == local_today("Africa/Lagos").isoformat()


def test_cannot_start_the_same_plan_twice(client, headers, plan):
    client.post("/users/me/plans", json={"plan_id": plan.id}, headers=headers)
    response = client.post("/users/me/plans", json={"plan_id": plan.id}, headers=headers)

    assert response.status_code == 409


def test_unknown_plan_is_404(client, headers):
    response = client.post("/users/me/plans", json={"plan_id": 999999}, headers=headers)

    assert response.status_code == 404


def test_starting_a_plan_needs_a_token(client, plan):
    response = client.post("/users/me/plans", json={"plan_id": plan.id})

    assert response.status_code == 401
