

"""Endpoints for readers (users)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.clock import local_today
from app.db import get_db
from app.models import ReadingPlan, Translation, User, UserPlan
from app.ratelimit import limit_signups
from app.schemas import (
    StreakOut,
    UserCreate,
    UserCreated,
    UserOut,
    UserPlanCreate,
    UserPlanOut,
    UserUpdate,
)
from app.security import hash_token, new_token
from app.streaks import streaks

router = APIRouter(prefix="/users", tags=["users"])


# POST /users: register a device. Returns its token once; only the token's hash is stored.
@router.post(
    "",
    response_model=UserCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_signups)],
)

def register(body: UserCreate, db: Session = Depends(get_db)):
    """Register a new device and give it a secret token."""
    translation = db.scalar(select(Translation).where(Translation.code == body.translation))
    if translation is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown translation: {body.translation}")

    if db.scalar(select(User).where(User.device_id == body.device_id)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "this device is already registered")

    token = new_token()
    user = User(
        device_id=body.device_id,
        token_hash=hash_token(token),
        timezone=body.timezone,
        wake_time=body.wake_time,
        translation_id=translation.id,
    )
    db.add(user)
    db.commit()

    return UserCreated(id=user.id, timezone=user.timezone, wake_time=user.wake_time, token=token)


# GET /users/me: the reader making the request, worked out from their token
@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)):
    """Who am I? Returns the settings of the reader whose token was sent."""
    return user


# PATCH /users/me: change only the settings that were sent; everything else stays as it was
@router.patch("/me", response_model=UserOut)
def update_me(
    body: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the reader's time zone and/or wake time."""
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    return user


# GET /users/me/streak: mornings in a row, counted in the reader's own time zone
@router.get("/me/streak", response_model=StreakOut)
def read_streak(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The reader's current and longest reading streaks."""
    current, longest, last_read_on = streaks(db, user, local_today(user.timezone))
    return StreakOut(current=current, longest=longest, last_read_on=last_read_on)


# POST /users/me/plans: start a reading plan today (in the reader's own time zone)
@router.post("/me/plans", response_model=UserPlanOut, status_code=status.HTTP_201_CREATED)
def start_plan(
    body: UserPlanCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enrol the reader in a plan, starting at day 1."""
    if db.get(ReadingPlan, body.plan_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such plan")

    already = db.scalar(
        select(UserPlan).where(UserPlan.user_id == user.id, UserPlan.plan_id == body.plan_id)
    )
    if already is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "you have already started this plan")

    enrolment = UserPlan(
        user_id=user.id,
        plan_id=body.plan_id,
        start_date=local_today(user.timezone),
        current_day=1,
    )
    db.add(enrolment)
    db.commit()
    return enrolment
