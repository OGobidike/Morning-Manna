

"""Database connection: one engine for the whole backend, and a session factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

# The engine manages a pool of connections to Postgres (address from app/config.py)
engine = create_engine(settings.database_url)

# Call SessionLocal() to get a session: one conversation with the database
SessionLocal = sessionmaker(engine)
