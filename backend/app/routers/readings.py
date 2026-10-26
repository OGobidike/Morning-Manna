

"""Endpoints for opening and completing a reading."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import PlanDay, ReadingSession, User, UserPlan
from app.progress import current_enrolment, current_plan_day
from app.schemas import ReadingComplete, ReadingOpen, ReadingOut

router = APIRouter(prefix="/readings", tags=["readings"])


# POST /readings: open a reading for the day the reader has reached
@router.post("", response_model=ReadingOut, status_code=status.HTTP_201_CREATED)
def open_reading(
    body: ReadingOpen | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Start a sitting with today's passage, now or at the moment the app reports."""
    # The same plan and day that GET /today serves
    enrolment = current_enrolment(db, user)
    day = current_plan_day(db, enrolment)
    if day is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "plan already completed")

    # Event time, not processing time: when it really happened, if the app tells us
    opened_at = body.opened_at if body and body.opened_at else datetime.now(UTC)
    reading = ReadingSession(user_id=user.id, plan_day_id=day.id, opened_at=opened_at)
    db.add(reading)
    db.commit()
    db.refresh(reading)
    return reading


# POST /readings/{reading_id}/complete: finish a reading and move to the next day
@router.post("/{reading_id}/complete", response_model=ReadingOut)
def complete_reading(
    reading_id: int,
    body: ReadingComplete | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a reading finished, now or at the moment the app reports. Again changes nothing."""
    reading = db.get(ReadingSession, reading_id)
    # Someone else's reading looks exactly like a missing one
    if reading is None or reading.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "reading not found")

    # Already finished (e.g. the phone retried): answer the same, advance nothing
    if reading.completed_at is not None:
        return reading

    completed_at = body.completed_at if body and body.completed_at else datetime.now(UTC)
    # A reading can't end before it began
    if completed_at < reading.opened_at:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "completed before it was opened")
    reading.completed_at = completed_at

    day = db.get(PlanDay, reading.plan_day_id)
    enrolment = db.scalar(
        select(UserPlan).where(UserPlan.user_id == user.id, UserPlan.plan_id == day.plan_id)
    )
    # Rule B: move forward only if this reading is for the day the reader is on
    if enrolment.current_day == day.day_number:
        enrolment.current_day += 1

    db.commit()
    db.refresh(reading)
    return reading
