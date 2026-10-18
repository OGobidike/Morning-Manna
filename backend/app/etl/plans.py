

"""The "30 Mornings" reading plan, built by hand: one short passage per day."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import PlanDay, ReadingPlan

PLAN_NAME = "30 Mornings"
PLAN_DESCRIPTION = "Thirty short passages for the start of the day: psalms, promises, and hope."

# One passage per day: (book code, start chapter, start verse, end chapter, end verse)
DAYS = [
    ("PSA", 1, 1, 1, 6),
    ("PSA", 23, 1, 23, 6),
    ("MAT", 5, 1, 5, 12),
    ("MAT", 6, 25, 6, 34),
    ("JHN", 1, 1, 1, 14),
    ("JHN", 3, 16, 3, 21),
    ("ROM", 8, 28, 8, 39),
    ("PHP", 4, 4, 4, 9),
    ("ISA", 40, 28, 40, 31),
    ("LAM", 3, 22, 3, 26),
    ("PRO", 3, 1, 3, 8),
    ("PSA", 121, 1, 121, 8),
    ("1CO", 13, 1, 13, 13),
    ("GAL", 5, 16, 5, 26),
    ("EPH", 2, 1, 2, 10),
    ("HEB", 11, 1, 11, 6),
    ("JAS", 1, 2, 1, 8),
    ("1PE", 5, 6, 5, 11),
    ("MAT", 11, 25, 11, 30),
    ("JHN", 15, 1, 15, 11),
    ("PSA", 46, 1, 46, 11),
    ("ISA", 43, 1, 43, 7),
    ("ROM", 12, 1, 12, 8),
    ("COL", 3, 12, 3, 17),
    ("1JN", 4, 7, 4, 12),
    ("PSA", 139, 1, 139, 12),
    ("JOS", 1, 6, 1, 9),
    ("MIC", 6, 6, 6, 8),
    ("LUK", 15, 11, 15, 24),
    ("REV", 21, 1, 21, 7),
]


def upsert_plan(session: Session, book_ids: dict[str, int]) -> int:
    """Insert or update the plan and its days. Returns how many days were loaded."""
    stmt = insert(ReadingPlan).values(name=PLAN_NAME, description=PLAN_DESCRIPTION)
    stmt = stmt.on_conflict_do_update(
        index_elements=["name"],
        set_={"description": stmt.excluded.description},
    ).returning(ReadingPlan.id)
    plan_id = session.execute(stmt).scalar_one()

    rows = [
        {
            "plan_id": plan_id,
            "day_number": day_number,
            "book_id": book_ids[code],
            "start_chapter": start_chapter,
            "start_verse": start_verse,
            "end_chapter": end_chapter,
            "end_verse": end_verse,
        }
        for day_number, (code, start_chapter, start_verse, end_chapter, end_verse) in enumerate(
            DAYS, start=1
        )
    ]
    stmt = insert(PlanDay).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["plan_id", "day_number"],
        set_={
            "book_id": stmt.excluded.book_id,
            "start_chapter": stmt.excluded.start_chapter,
            "start_verse": stmt.excluded.start_verse,
            "end_chapter": stmt.excluded.end_chapter,
            "end_verse": stmt.excluded.end_verse,
        },
    )
    session.execute(stmt)
    return len(rows)
