

"""Reading streaks: how many mornings in a row a reader has finished their passage."""

from datetime import date, timedelta

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.models import ReadingSession, User


def local_reading_day(user: User):
    """SQL for the calendar day a reading was finished, in the reader's own time zone."""
    return func.date(func.timezone(user.timezone, ReadingSession.completed_at))


def reading_days(db: Session, user: User, start: date, end: date) -> list[date]:
    """Every day from start to end (both included) on which the reader finished a reading."""
    day = local_reading_day(user)
    query = (
        select(day)
        .where(
            ReadingSession.user_id == user.id,
            ReadingSession.completed_at.is_not(None),
            day.between(start, end),
        )
        .distinct()
        .order_by(day)
    )
    return list(db.scalars(query))




def reading_runs(db: Session, user: User) -> list[tuple[date, date, int]]:
    """Every unbroken run of reading days: (first day, last day, length), oldest first.

    "Gaps and islands": number the reading days 1, 2, 3... in order. Within a run of
    back-to-back days, day minus its number stays the same, so that value names the run.
    """
    # The calendar day each reading was finished, in the reader's own time zone
    local_day = local_reading_day(user)
    # Each reading day once, however many readings were finished that day
    days = (
        select(local_day.label("day"))
        .where(ReadingSession.user_id == user.id, ReadingSession.completed_at.is_not(None))
        .distinct()
        .subquery()
    )

    # day minus its position: the same value for every day in one run
    position = cast(func.row_number().over(order_by=days.c.day), Integer)
    numbered = select(days.c.day, (days.c.day - position).label("run")).subquery()

    runs = (
        select(
            func.min(numbered.c.day),
            func.max(numbered.c.day),
            func.count(),
        )
        .group_by(numbered.c.run)
        .order_by(func.min(numbered.c.day))
    )
    return [tuple(row) for row in db.execute(runs)]


def streaks(db: Session, user: User, today: date) -> tuple[int, int, date | None]:
    """(current streak, longest streak, last day read).

    The current streak stays alive through today: reading yesterday still counts,
    because the reader may simply not have read yet this morning.
    """
    runs = reading_runs(db, user)
    if not runs:
        return 0, 0, None

    longest = max(length for _, _, length in runs)
    _, last_day, last_length = runs[-1]
    current = last_length if last_day >= today - timedelta(days=1) else 0
    return current, longest, last_day
