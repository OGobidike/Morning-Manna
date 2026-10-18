

"""Load: upsert rows into Postgres, so running the pipeline twice changes nothing."""

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.etl.books import BOOKS
from app.etl.sources import Source
from app.models import Book, Translation, Verse

# Rows sent to Postgres per INSERT. Postgres allows at most 65,535 values per statement,
# and each verse has 5, so 5,000 verses (25,000 values) per batch is safely under the limit.
BATCH_SIZE = 5000


def upsert_books(session: Session) -> dict[str, int]:
    """Insert or update the 66 books. Returns {book code: book id}."""
    rows = [
        {
            "code": book.code,
            "name": book.name,
            "testament": book.testament,
            "canonical_order": order,
        }
        for order, book in enumerate(BOOKS, start=1)
    ]
    stmt = insert(Book).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={
            "name": stmt.excluded.name,
            "testament": stmt.excluded.testament,
            "canonical_order": stmt.excluded.canonical_order,
        },
    )
    session.execute(stmt)
    return dict(session.execute(select(Book.code, Book.id)).tuples().all())


def upsert_translation(session: Session, source: Source) -> int:
    """Insert or update one translation. Returns its id."""
    stmt = insert(Translation).values(code=source.code, name=source.name, license=source.license)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={"name": stmt.excluded.name, "license": stmt.excluded.license},
    ).returning(Translation.id)
    return session.execute(stmt).scalar_one()


def upsert_verses(
    session: Session, translation_id: int, book_ids: dict[str, int], df: pd.DataFrame
) -> int:
    """Insert or update every verse of one translation. Returns how many rows were sent."""
    rows = [
        {
            "translation_id": translation_id,
            "book_id": book_ids[code],
            # int(...) turns pandas' number type into a plain Python int that psycopg understands
            "chapter": int(chapter),
            "verse": int(verse),
            "text": text,
        }
        for code, chapter, verse, text in df.itertuples(index=False)
    ]
    for start in range(0, len(rows), BATCH_SIZE):
        stmt = insert(Verse).values(rows[start : start + BATCH_SIZE])
        stmt = stmt.on_conflict_do_update(
            index_elements=["translation_id", "book_id", "chapter", "verse"],
            set_={"text": stmt.excluded.text},
        )
        session.execute(stmt)
    return len(rows)
