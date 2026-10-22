

"""Tests for opening and completing a reading."""


def open_reading(client, headers):
    return client.post("/readings", headers=headers)


def complete(client, headers, reading_id):
    return client.post(f"/readings/{reading_id}/complete", headers=headers)


def test_open_a_reading_for_today(client, reader, world):
    response = open_reading(client, reader)

    assert response.status_code == 201
    data = response.json()
    assert data["completed_at"] is None
    assert data["opened_at"] is not None


def test_completing_moves_to_the_next_day(client, reader):
    reading = open_reading(client, reader).json()

    response = complete(client, reader, reading["id"])

    assert response.status_code == 200
    assert response.json()["completed_at"] is not None
    assert client.get("/today", headers=reader).json()["day_number"] == 2


def test_completing_twice_counts_once(client, reader):
    reading = open_reading(client, reader).json()
    first = complete(client, reader, reading["id"]).json()

    second = complete(client, reader, reading["id"])

    assert second.status_code == 200
    assert second.json()["completed_at"] == first["completed_at"]
    assert client.get("/today", headers=reader).json()["day_number"] == 2


def test_an_old_reading_does_not_skip_a_day(client, reader):
    # Two readings opened on day 1; finishing both must still only reach day 2
    first = open_reading(client, reader).json()
    second = open_reading(client, reader).json()
    complete(client, reader, first["id"])

    complete(client, reader, second["id"])

    assert client.get("/today", headers=reader).json()["day_number"] == 2


def test_someone_elses_reading_is_404(client, reader, world):
    reading = open_reading(client, reader).json()
    other = client.post(
        "/users",
        json={
            "device_id": "other-reader-device",
            "timezone": "Africa/Lagos",
            "wake_time": "06:00",
            "translation": "TST",
        },
    ).json()
    other_headers = {"Authorization": f"Bearer {other['token']}"}

    response = complete(client, other_headers, reading["id"])

    assert response.status_code == 404
    assert client.get("/today", headers=reader).json()["day_number"] == 1


def test_missing_reading_is_404(client, reader):
    assert complete(client, reader, 999_999_999).status_code == 404


def test_open_without_a_plan_is_404(client, headers):
    assert open_reading(client, headers).status_code == 404


def test_open_after_the_last_day_is_409(client, reader):
    for _ in range(2):
        reading = open_reading(client, reader).json()
        complete(client, reader, reading["id"])

    assert open_reading(client, reader).status_code == 409


def test_readings_need_a_token(client):
    assert client.post("/readings").status_code == 401
    assert client.post("/readings/1/complete").status_code == 401
