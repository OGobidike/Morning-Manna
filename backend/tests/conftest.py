

"""Shared test setup: a real database session that is rolled back after every test."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.main import app


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
