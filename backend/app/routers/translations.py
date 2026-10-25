

"""Endpoint for the Bible translations a reader can choose from."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Translation
from app.schemas import TranslationOut

router = APIRouter(prefix="/translations", tags=["translations"])


# GET /translations: every translation, by code
@router.get("", response_model=list[TranslationOut])
def list_translations(db: Session = Depends(get_db)):
    """Every translation a reader can choose, e.g. KJV and ASV."""
    return db.scalars(select(Translation).order_by(Translation.code)).all()
