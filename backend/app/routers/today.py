

"""Endpoint for this morning's reading."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Book, PlanDay, ReadingPlan, User, Verse
from app.progress import current_enrolment, current_plan_day
from app.schemas import PassageOut, TodayOut, UpcomingOut, VerseOut

router = APIRouter(prefix="/today", tags=["today"])


def reference(book: str, day: PlanDay) -> str:
    """A human-readable passage, e.g. "John 3:16-21" or "Ruth 1:1-2:3"."""
    if day.start_chapter == day.end_chapter:
        return f"{book} {day.start_chapter}:{day.start_verse}-{day.end_verse}"
    return f"{book} {day.start_chapter}:{day.start_verse}-{day.end_chapter}:{day.end_verse}"


def plan_length(db: Session, plan_id: int) -> int:
    """How many days a plan has."""
    return db.scalar(select(func.count()).select_from(PlanDay).where(PlanDay.plan_id == plan_id))


def passage(db: Session, user: User, day: PlanDay) -> PassageOut:
    """One day's passage, in the reader's own translation."""
    # Every verse from (start chapter, start verse) to (end chapter, end verse), in order
    position = tuple_(Verse.chapter, Verse.verse)
    verses = db.scalars(
        select(Verse)
        .where(
            Verse.translation_id == user.translation_id,
            Verse.book_id == day.book_id,
            position >= (day.start_chapter, day.start_verse),
            position <= (day.end_chapter, day.end_verse),
        )
        .order_by(Verse.chapter, Verse.verse)
    ).all()

    book = db.get(Book, day.book_id)
    return PassageOut(
        day_number=day.day_number,
        reference=reference(book.name, day),
        verses=[VerseOut.model_validate(verse) for verse in verses],
    )


# GET /today: the passage for the reader's current day (Rule B: progress, not the calendar)
@router.get("", response_model=TodayOut)
def read_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """This morning's passage, in the reader's own translation."""
    enrolment = current_enrolment(db, user)

    plan = db.get(ReadingPlan, enrolment.plan_id)
    total_days = plan_length(db, plan.id)

    day = current_plan_day(db, enrolment)
    if day is None:
        # Past the last day: the plan is finished
        return TodayOut(
            plan_name=plan.name,
            day_number=enrolment.current_day,
            total_days=total_days,
            completed=True,
        )

    today = passage(db, user, day)
    return TodayOut(
        plan_name=plan.name,
        day_number=today.day_number,
        total_days=total_days,
        completed=False,
        reference=today.reference,
        verses=today.verses,
    )


# GET /today/upcoming: this morning's passage and the next few, so the app can read offline
@router.get("/upcoming", response_model=UpcomingOut)
def read_upcoming(
    days: int = Query(7, ge=1, le=14),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The passages from the reader's current day onwards: `days` of them, or fewer near the end."""
    enrolment = current_enrolment(db, user)
    plan = db.get(ReadingPlan, enrolment.plan_id)

    coming_days = db.scalars(
        select(PlanDay)
        .where(PlanDay.plan_id == plan.id, PlanDay.day_number >= enrolment.current_day)
        .order_by(PlanDay.day_number)
        .limit(days)
    ).all()

    return UpcomingOut(
        plan_name=plan.name,
        total_days=plan_length(db, plan.id),
        passages=[passage(db, user, day) for day in coming_days],
    )
