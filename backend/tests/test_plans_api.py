

"""Tests for the /plans endpoints."""

from app.models import ReadingPlan


def test_list_plans_returns_plans_in_creation_order(client, db):
    db.add_all(
        [
            ReadingPlan(name="Test Plan A", description="First"),
            ReadingPlan(name="Test Plan B", description="Second"),
        ]
    )
    db.flush()  # Send the rows to Postgres (inside the test's transaction)

    response = client.get("/plans")

    assert response.status_code == 200
    names = [plan["name"] for plan in response.json()]
    assert names.index("Test Plan A") < names.index("Test Plan B")


def test_list_plans_only_returns_safe_fields(client, db):
    db.add(ReadingPlan(name="Test Plan C", description="Third"))
    db.flush()

    response = client.get("/plans")

    for plan in response.json():
        assert set(plan) == {"id", "name", "description"}
