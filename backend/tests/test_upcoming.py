

"""Tests for GET /today/upcoming (the next few passages, for reading offline)."""

import pytest


def finish_today(client, reader):
    """Open today's reading and complete it, the way the app does."""
    reading = client.post("/readings", headers=reader).json()
    client.post(f"/readings/{reading['id']}/complete", headers=reader)


def test_upcoming_starts_at_the_current_day(client, reader):
    data = client.get("/today/upcoming", headers=reader).json()

    assert data["plan_name"] == "Two Mornings"
    assert data["total_days"] == 2
    assert [p["day_number"] for p in data["passages"]] == [1, 2]
    assert data["passages"][0]["reference"] == "Testbook 1:1-2"
    assert [v["text"] for v in data["passages"][1]["verses"]] == ["Third.", "Fourth."]


def test_upcoming_moves_on_after_a_reading(client, reader):
    finish_today(client, reader)

    data = client.get("/today/upcoming", headers=reader).json()

    assert [p["day_number"] for p in data["passages"]] == [2]


def test_upcoming_length_can_be_chosen(client, reader):
    data = client.get("/today/upcoming?days=1", headers=reader).json()

    assert [p["day_number"] for p in data["passages"]] == [1]


def test_upcoming_is_empty_once_the_plan_is_finished(client, reader):
    finish_today(client, reader)
    finish_today(client, reader)

    assert client.get("/today/upcoming", headers=reader).json()["passages"] == []


def test_upcoming_matches_today(client, reader):
    today = client.get("/today", headers=reader).json()

    first = client.get("/today/upcoming", headers=reader).json()["passages"][0]

    assert first["reference"] == today["reference"]
    assert first["verses"] == today["verses"]


def test_upcoming_without_a_plan_is_404(client, headers):
    assert client.get("/today/upcoming", headers=headers).status_code == 404


@pytest.mark.parametrize("days", [0, 15])
def test_upcoming_length_is_checked(client, reader, days):
    assert client.get(f"/today/upcoming?days={days}", headers=reader).status_code == 422


def test_upcoming_needs_a_token(client):
    assert client.get("/today/upcoming").status_code == 401
