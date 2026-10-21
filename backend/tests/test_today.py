

"""Tests for GET /today (this morning's passage, Rule B: progress-based)."""

import pytest
from sqlalchemy import select

from app.models import Book, PlanDay, ReadingPlan, Translation, User, UserPlan, Verse


@pytest.fixture
def world(db):
    """A tiny Bible and a two-day plan: day 1 is Testbook 1:1-2, day 2 is Testbook 1:3-2:1."""
    translation = Translation(code="TST", name="Test Translation", license="Public domain")
    book = Book(code="TBK", name="Testbook", testament="NT", canonical_order=999)
    plan = ReadingPlan(name="Two Mornings", description="For tests")
    db.add_all([translation, book, plan])
    db.flush()

    verses = [(1, 1, "First."), (1, 2, "Second."), (1, 3, "Third."), (2, 1, "Fourth.")]
    for chapter, verse, text in verses:
        db.add(
            Verse(
                translation_id=translation.id,
                book_id=book.id,
                chapter=chapter,
                verse=verse,
                text=text,
            )
        )

    # (day, start chapter, start verse, end chapter, end verse)
    days = [(1, 1, 1, 1, 2), (2, 1, 3, 2, 1)]
    for day, start_chapter, start_verse, end_chapter, end_verse in days:
        db.add(
            PlanDay(
                plan_id=plan.id,
                day_number=day,
                book_id=book.id,
                start_chapter=start_chapter,
                start_verse=start_verse,
                end_chapter=end_chapter,
                end_verse=end_verse,
            )
        )
    db.flush()
    return plan


@pytest.fixture
def headers(client, world):
    """Register a reader who reads the test translation."""
    response = client.post(
        "/users",
        json={
            "device_id": "today-test-device",
            "timezone": "Africa/Lagos",
            "wake_time": "06:00",
            "translation": "TST",
        },
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


def start_plan(client, headers, plan):
    client.post("/users/me/plans", json={"plan_id": plan.id}, headers=headers)


def set_current_day(db, day):
    """Move the TEST reader to a given day (a stand-in until readings can be completed)."""
    enrolment = db.scalar(
        select(UserPlan)
        .join(User, User.id == UserPlan.user_id)
        .where(User.device_id == "today-test-device")
    )
    enrolment.current_day = day
    db.flush()


def test_day_one_passage(client, headers, world):
    start_plan(client, headers, world)

    data = client.get("/today", headers=headers).json()

    assert data["day_number"] == 1
    assert data["total_days"] == 2
    assert data["completed"] is False
    assert data["reference"] == "Testbook 1:1-2"
    assert [v["text"] for v in data["verses"]] == ["First.", "Second."]


def test_passage_across_two_chapters(client, db, headers, world):
    start_plan(client, headers, world)
    set_current_day(db, 2)

    data = client.get("/today", headers=headers).json()

    assert data["reference"] == "Testbook 1:3-2:1"
    assert [v["text"] for v in data["verses"]] == ["Third.", "Fourth."]


def test_after_the_last_day_the_plan_is_completed(client, db, headers, world):
    start_plan(client, headers, world)
    set_current_day(db, 3)

    data = client.get("/today", headers=headers).json()

    assert data["completed"] is True
    assert data["verses"] == []


def test_no_plan_yet_is_404(client, headers):
    response = client.get("/today", headers=headers)

    assert response.status_code == 404


def test_today_needs_a_token(client):
    assert client.get("/today").status_code == 401
