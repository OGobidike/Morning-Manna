

"""Tests for the hand-built "30 Mornings" reading plan."""

from app.etl.books import BOOKS
from app.etl.plans import DAYS

CHAPTERS_BY_CODE = {book.code: book.chapters for book in BOOKS}


def test_plan_has_30_days():
    assert len(DAYS) == 30


def test_every_passage_points_somewhere_real():
    for code, start_chapter, start_verse, end_chapter, end_verse in DAYS:
        # A real book, and chapters that exist in it
        assert code in CHAPTERS_BY_CODE
        assert 1 <= start_chapter <= end_chapter <= CHAPTERS_BY_CODE[code]
        # The passage doesn't end before it starts
        assert (start_chapter, start_verse) <= (end_chapter, end_verse)
