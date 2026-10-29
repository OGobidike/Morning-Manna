

"""Shared test setup: a real database session that is rolled back after every test."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.db import engine, get_db
from app.main import app
from app.models import Book, PlanDay, ReadingPlan, Translation, Verse
from app.ratelimit import signup_limiter


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Every test starts with a clean sign-up allowance."""
    signup_limiter.reset()


@pytest.fixture(autouse=True)
def no_real_lake(monkeypatch):
    """Tests never write to the real lake, even if .env sets LAKE_URL.

    Their readers vanish when each test ends, so anything they sent to the lake would be
    events from readers who never existed. The lake tests point at a test lake of their own.
    """
    monkeypatch.setattr(settings, "lake_url", "")


@pytest.fixture
def db() -> Iterator[Session]:
    """A session inside a transaction that is undone after the test, so tests leave no trace."""
    connection = engine.connect()
    transaction = connection.begin()
    # Commits inside the test become savepoints, so the outer transaction can still undo them
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    """An API client whose endpoints use the test's session instead of a real one."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()

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
            "device_id": "test-reader-device",
            "timezone": "Africa/Lagos",
            "wake_time": "06:00",
            "translation": "TST",
        },
    )
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture
def reader(client, headers, world):
    """The test reader, already started on the two-day plan."""
    client.post("/users/me/plans", json={"plan_id": world.id}, headers=headers)
    return headers
