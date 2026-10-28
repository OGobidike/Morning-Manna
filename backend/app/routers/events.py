

"""Endpoint for app events (what readers do in the app), sent in batches."""

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from app import lake
from app.auth import get_current_user
from app.db import get_db
from app.models import Event, User
from app.schemas import EventBatch, EventBatchOut

router = APIRouter(prefix="/events", tags=["events"])


# POST /events: store a batch of events. Pydantic has already checked every one.
@router.post("", response_model=EventBatchOut, status_code=status.HTTP_201_CREATED)
def record_events(
    batch: EventBatch,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Store a batch of events for the signed-in reader, all or nothing."""
    received_at = datetime.now(UTC)
    events = [
        Event(
            user_id=user.id,
            event_type=event.event_type,
            occurred_at=event.occurred_at,
            properties=event.properties,
        )
        for event in batch.events
    ]
    db.add_all(events)
    db.flush()  # gives each event its id now, without reloading them after the commit
    records = lake.lake_records(events, received_at)
    db.commit()
    # A copy for the data lake, written after the reply has gone, so the phone never waits
    background.add_task(lake.save_events, records, received_at)
    return EventBatchOut(accepted=len(batch.events))
