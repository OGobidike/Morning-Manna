

"""Endpoint for app events (what readers do in the app), sent in batches."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.models import Event, User
from app.schemas import EventBatch, EventBatchOut

router = APIRouter(prefix="/events", tags=["events"])


# POST /events: store a batch of events. Pydantic has already checked every one.
@router.post("", response_model=EventBatchOut, status_code=status.HTTP_201_CREATED)
def record_events(
    batch: EventBatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Store a batch of events for the signed-in reader, all or nothing."""
    db.add_all(
        Event(
            user_id=user.id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            properties=event.properties,
        )
        for event in batch.events
    )
    db.commit()
    return EventBatchOut(accepted=len(batch.events))
