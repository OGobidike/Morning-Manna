

### Oh boi was this complicated the first timee
"""Database tables for Morning Manna, written as SQLAlchemy models."""

# Python's built-in date and time types
from datetime import date, datetime, time

# Tools from SQLAlchemy for describing columns and rules
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func

# A Postgresql specific column type for JSON data
from sqlalchemy.dialects.postgresql import JSONB

# Tools for writing tables as Python classes (the SQLAlchemy 2.0 style :)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """The parent of every table. Keeps a record of them."""


class Translation(Base):
    """One Bible translation, such as the World English Bible."""

    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short code, e.g. "WEB" or "KJV". No two translations may share one.
    code: Mapped[str] = mapped_column(String(10), unique=True)
    # Full name, e.g. "World English Bible"
    name: Mapped[str] = mapped_column(String(100))
    # Licence, e.g. "Public domain"
    license: Mapped[str] = mapped_column(String(100))


class Book(Base):
    """One book of the Bible, such as Genesis Exodus or John."""

    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short code, e.g. "GEN" for Genesis
    code: Mapped[str] = mapped_column(String(10), unique=True)
    # Full name, e.g. "Genesis"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # "OT" (Old Testament) or "NT" (New Testament)
    testament: Mapped[str] = mapped_column(String(10))
    # Position in the Bible: 1 = Genesis ... 66 = Revelation. Each position is used once.
    canonical_order: Mapped[int] = mapped_column(unique=True)


class Verse(Base):
    """One verse in one translation, such as John 3:16 in the KJV."""
    # Rule: each verse appears once per translation.
    # Its unique index also serves verse lookups (translation + book + chapter.
    # *Think out it like a surname),
    # so no separate index is needed.

    __tablename__ = "verses"
    # Unique constraint: no two verses may have the same translation, book, chapter, and verse.
    # Its index also serves verse lookups (translation + book + chapter, the leftmost
    # columns), so no separate index is needed.
    __table_args__ = (UniqueConstraint("translation_id", "book_id", "chapter", "verse"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Which translation this wording comes from (points to translations.id)
    translation_id: Mapped[int] = mapped_column(ForeignKey("translations.id"))
    # Which book this verse is in (points to books.id)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    # Position within the book, e.g. chapter 3, verse 16
    chapter: Mapped[int]
    verse: Mapped[int]
    # The words of the verse. Text has no length limit.
    text: Mapped[str] = mapped_column(Text)


class ReadingPlan(Base):
    """A 30 day reading plan ( such as; 30 Mornings)"""

    __tablename__ = "reading_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The plans name: e.g. "30 Mornings"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    # A sentence or two describing the plan
    description: Mapped[str] = mapped_column(String(500))


class PlanDay(Base):
    """One day in a reading plan, e.g. Day 1 of 30 Mornings."""

    __tablename__ = "plan_days"
    # Rule: each plan has only one row per day number
    __table_args__ = (UniqueConstraint("plan_id", "day_number"),)


    # the unique id of this row
    id: Mapped[int] = mapped_column(primary_key=True)
    # The plan this day belongs to
    plan_id: Mapped[int] = mapped_column(ForeignKey("reading_plans.id"))
    # the number of day ( e.g. day 1, day 2, day 3, etc)
    day_number: Mapped[int]

    #where to start and end reading Remember, the translations are stored by the reader not here
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    start_chapter: Mapped[int]
    start_verse: Mapped[int]
    end_chapter: Mapped[int]
    end_verse: Mapped[int]


class User(Base):
    """One reader, identified only by an anonymous device ID."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Random ID created by the app on first launch. No name or email, by design.
    device_id: Mapped[str] = mapped_column(String(64), unique=True)
    # Time zone name, e.g. "Africa/Lagos" (a name, not an offset like +1)
    timezone: Mapped[str] = mapped_column(String(64))
    # Reminder clock time, e.g. 05:30 (no date, no zone)
    wake_time: Mapped[time]
    # The reader's chosen translation (points to translations.id)
    translation_id: Mapped[int] = mapped_column(ForeignKey("translations.id"))
    # When the reader joined. The database fills this in automatically.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserPlan(Base):
    """One reader's progress through one reading plan."""

    __tablename__ = "user_plans"
    # Rule: a reader can be enrolled in each plan only once
    __table_args__ = (UniqueConstraint("user_id", "plan_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Which reader (points to users.id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Which plan (points to reading_plans.id)
    plan_id: Mapped[int] = mapped_column(ForeignKey("reading_plans.id"))
    # The day the reader started, e.g. 2026-10-06 (date only)
    start_date: Mapped[date]
    # Which day of the plan they're on. New enrolments start at day 1.
    current_day: Mapped[int] = mapped_column(default=1)

class ReadingSession(Base):
    """One sitting with one day's passage: opened, and perhaps completed."""

    __tablename__ = "reading_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Who read (points to users.id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # Which day's passage (points to plan_days.id)
    plan_day_id: Mapped[int] = mapped_column(ForeignKey("plan_days.id"))
    # When the passage was opened. Always known.
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When it was finished. Empty (NULL) if the reader never finished.
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Real reading time measured by the app. Empty (NULL) if never finished.
    seconds_spent: Mapped[int | None]


class Event(Base):
    """One thing that happened in the app, e.g. a notification was opened."""

    __tablename__ = "events"
    # Index: find one user's events in a time range quickly
    # (user first for the exact match(surname rule), then time for the range)
    __table_args__ = (Index("ix_events_user_id_occurred_at", "user_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Who it happened to (points to users.id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    # What happened, e.g. "notification_opened" or "reading_completed"
    event_type: Mapped[str] = mapped_column(String(50))
    # When it happened. Always known.
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Extra details that differ for each event type, e.g. {"minutes": 10}
    properties: Mapped[dict] = mapped_column(JSONB, server_default="{}")
