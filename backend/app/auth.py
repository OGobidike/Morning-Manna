

"""Authentication: work out which reader is making a request, from their device token."""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import hash_token


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """Return the user whose token is in the "Authorization: Bearer <token>" header, or 401."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="missing or invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Expect exactly two parts: the word "Bearer" and the token
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise unauthorized

    # Hash what arrived and look for a user with that hash
    user = db.scalar(select(User).where(User.token_hash == hash_token(token)))
    if user is None:
        raise unauthorized
    return user
