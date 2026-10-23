

"""Where a reader is in their plan. Shared by GET /today and the readings endpoints."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlanDay, User, UserPlan


def current_enrolment(db: Session, user: User) -> UserPlan:
    """The plan the reader started most recently. 404 if they haven't started one."""
    enrolment = db.scalar(
        select(UserPlan).where(UserPlan.user_id == user.id).order_by(UserPlan.id.desc())
    )
    if enrolment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "start a plan first")
    return enrolment


def current_plan_day(db: Session, enrolment: UserPlan) -> PlanDay | None:
    """The day the reader has reached (Rule B). None once they are past the last day."""
    return db.scalar(
        select(PlanDay).where(
            PlanDay.plan_id == enrolment.plan_id, PlanDay.day_number == enrolment.current_day
        )
    )
