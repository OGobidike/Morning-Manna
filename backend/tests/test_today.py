

"""Tests for GET /today (this morning's passage, Rule B: progress-based)."""


def finish_today(client, reader):
    """Open today's reading and complete it, the way the app will."""
    reading = client.post("/readings", headers=reader).json()
    client.post(f"/readings/{reading['id']}/complete", headers=reader)


def test_day_one_passage(client, reader):
    data = client.get("/today", headers=reader).json()

    assert data["day_number"] == 1
    assert data["total_days"] == 2
    assert data["completed"] is False
    assert data["reference"] == "Testbook 1:1-2"
    assert [v["text"] for v in data["verses"]] == ["First.", "Second."]


def test_passage_across_two_chapters(client, reader):
    finish_today(client, reader)

    data = client.get("/today", headers=reader).json()

    assert data["reference"] == "Testbook 1:3-2:1"
    assert [v["text"] for v in data["verses"]] == ["Third.", "Fourth."]


def test_after_the_last_day_the_plan_is_completed(client, reader):
    finish_today(client, reader)
    finish_today(client, reader)

    data = client.get("/today", headers=reader).json()

    assert data["completed"] is True
    assert data["verses"] == []


def test_no_plan_yet_is_404(client, headers):
    response = client.get("/today", headers=headers)

    assert response.status_code == 404


def test_today_needs_a_token(client):
    assert client.get("/today").status_code == 401
