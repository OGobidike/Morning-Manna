

"""Endpoints for reading plans."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ReadingPlan
from app.schemas import PlanOut

router = APIRouter(prefix="/plans", tags=["plans"])


# GET /plans: every plan, filtered through PlanOut (so only safe fields leave the server)
@router.get("", response_model=list[PlanOut])
def list_plans(db: Session = Depends(get_db)):
    """Every reading plan, in the order they were created."""
    return db.scalars(select(ReadingPlan).order_by(ReadingPlan.id)).all()
