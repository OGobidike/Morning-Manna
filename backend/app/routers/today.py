

"""Endpoint for this morning's reading."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Book, PlanDay, ReadingPlan, User, UserPlan, Verse
from app.schemas import TodayOut, VerseOut

router = APIRouter(prefix="/today", tags=["today"])


def reference(book: str, day: PlanDay) -> str:
    """A human-readable passage, e.g. "John 3:16-21" or "Ruth 1:1-2:3"."""
    if day.start_chapter == day.end_chapter:
        return f"{book} {day.start_chapter}:{day.start_verse}-{day.end_verse}"
    return f"{book} {day.start_chapter}:{day.start_verse}-{day.end_chapter}:{day.end_verse}"


# GET /today: the passage for the reader's current day (Rule B: progress, not the calendar)
@router.get("", response_model=TodayOut)
def read_today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """This morning's passage, in the reader's own translation."""
    # The plan the reader started most recently
    enrolment = db.scalar(
        select(UserPlan).where(UserPlan.user_id == user.id).order_by(UserPlan.id.desc())
    )
    if enrolment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "start a plan first")

    plan = db.get(ReadingPlan, enrolment.plan_id)
    total_days = db.scalar(
        select(func.count()).select_from(PlanDay).where(PlanDay.plan_id == plan.id)
    )

    # Rule B: serve the day the reader has reached, however many calendar days have passed
    day = db.scalar(
        select(PlanDay).where(
            PlanDay.plan_id == plan.id, PlanDay.day_number == enrolment.current_day
        )
    )
    if day is None:
        # Past the last day: the plan is finished
        return TodayOut(
            plan_name=plan.name,
            day_number=enrolment.current_day,
            total_days=total_days,
            completed=True,
        )

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
    return TodayOut(
        plan_name=plan.name,
        day_number=day.day_number,
        total_days=total_days,
        completed=False,
        reference=reference(book.name, day),
        verses=[VerseOut.model_validate(verse) for verse in verses],
    )
