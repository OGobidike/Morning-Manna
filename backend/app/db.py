

"""Database connection: one engine for the whole backend, and a session factory."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# The engine manages a pool of connections to Postgres (address from app/config.py)
engine = create_engine(settings.database_url)

# Call SessionLocal() to get a session: one conversation with the database
SessionLocal = sessionmaker(engine)


### a generator function: it yields a session to the endpoint, then cleans up after the request.

def get_db() -> Iterator[Session]:
    """Give each request its own session, and always close it afterwards."""
    with SessionLocal() as session:
        yield session
