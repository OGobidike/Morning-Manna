

"""Tests for the load step: upserts, so loading the same data twice changes nothing."""

import pandas as pd
from sqlalchemy import func, select

from app.etl import load
from app.etl.books import BOOKS
from app.etl.load import upsert_books, upsert_translation, upsert_verses
from app.etl.plans import DAYS, PLAN_NAME, upsert_plan
from app.etl.sources import Source
from app.models import Book, PlanDay, ReadingPlan, Translation, Verse

# A made-up translation, so the tests only ever touch their own verses
TEST_SOURCE = Source("ZZT", "Load Test Translation", "Public domain", "https://example.com")


def verses(*rows):
    """A clean DataFrame shaped like transform's output."""
    return pd.DataFrame(rows, columns=["book_code", "chapter", "verse", "text"])


def my_verses(db, translation_id):
    """The verses of the test translation only, in order."""
    return db.execute(
        select(Verse.chapter, Verse.verse, Verse.text)
        .where(Verse.translation_id == translation_id)
        .order_by(Verse.chapter, Verse.verse)
    ).all()


def test_books_load_once_however_often_they_run(db):
    first = upsert_books(db)
    second = upsert_books(db)

    codes = [book.code for book in BOOKS]
    count = db.scalar(select(func.count()).select_from(Book).where(Book.code.in_(codes)))
    assert count == 66
    # Same ids both times: the second run updated rows, it didn't add new ones
    assert {code: first[code] for code in codes} == {code: second[code] for code in codes}


def test_translation_upsert_keeps_one_row_and_updates_it(db):
    first_id = upsert_translation(db, TEST_SOURCE)
    renamed = TEST_SOURCE._replace(name="Load Test Translation, revised")

    second_id = upsert_translation(db, renamed)

    assert first_id == second_id
    assert db.get(Translation, first_id).name == "Load Test Translation, revised"


def test_verses_load_twice_without_duplicates(db):
    book_ids = upsert_books(db)
    translation_id = upsert_translation(db, TEST_SOURCE)
    df = verses(("GEN", 1, 1, "In the beginning."), ("GEN", 1, 2, "And the earth."))

    upsert_verses(db, translation_id, book_ids, df)
    sent = upsert_verses(db, translation_id, book_ids, df)

    assert sent == 2
    assert len(my_verses(db, translation_id)) == 2


def test_a_corrected_verse_replaces_the_old_text(db):
    book_ids = upsert_books(db)
    translation_id = upsert_translation(db, TEST_SOURCE)
    upsert_verses(db, translation_id, book_ids, verses(("GEN", 1, 1, "In the begining.")))

    upsert_verses(db, translation_id, book_ids, verses(("GEN", 1, 1, "In the beginning.")))

    assert my_verses(db, translation_id) == [(1, 1, "In the beginning.")]


def test_verses_are_sent_in_batches(db, monkeypatch):
    # Batches of 2, so 5 verses take 3 INSERTs; every verse must still arrive
    monkeypatch.setattr(load, "BATCH_SIZE", 2)
    book_ids = upsert_books(db)
    translation_id = upsert_translation(db, TEST_SOURCE)
    df = verses(*[("GEN", 1, number, f"Verse {number}.") for number in range(1, 6)])

    upsert_verses(db, translation_id, book_ids, df)

    assert [verse for _, verse, _ in my_verses(db, translation_id)] == [1, 2, 3, 4, 5]


def test_plan_loads_30_days_however_often_it_runs(db):
    book_ids = upsert_books(db)

    upsert_plan(db, book_ids)
    loaded = upsert_plan(db, book_ids)

    plan = db.scalar(select(ReadingPlan).where(ReadingPlan.name == PLAN_NAME))
    days = db.scalar(select(func.count()).select_from(PlanDay).where(PlanDay.plan_id == plan.id))
    assert loaded == len(DAYS) == 30
    assert days == 30
