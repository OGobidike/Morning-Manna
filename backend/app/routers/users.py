

"""Endpoints for readers (users)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Translation, User
from app.schemas import UserCreate, UserCreated, UserOut
from app.security import hash_token, new_token

router = APIRouter(prefix="/users", tags=["users"])


# POST /users: register a device. Returns its token once; only the token's hash is stored.
@router.post("", response_model=UserCreated, status_code=status.HTTP_201_CREATED)
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
