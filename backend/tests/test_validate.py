

"""Tests for the data-quality checks of the scripture pipeline."""

import pandas as pd
import pytest

from app.etl.books import BOOKS
from app.etl.validate import DataQualityError, find_problems, validate


def make_bible() -> pd.DataFrame:
    """A tiny but complete Bible: one verse in every chapter of all 66 books."""
    rows = [
        {"book_code": book.code, "chapter": chapter, "verse": 1, "text": "Some words."}
        for book in BOOKS
        for chapter in range(1, book.chapters + 1)
    ]
    return pd.DataFrame(rows)


def test_a_complete_bible_passes():
    assert find_problems(make_bible()) == []
    validate(make_bible(), "test")  # Does not raise


def test_bible_has_1189_chapters():
    assert len(make_bible()) == 1189


def test_missing_book_is_caught():
    bible = make_bible()
    bible = bible[bible["book_code"] != "JUD"]
    assert "missing books: ['JUD']" in find_problems(bible)


def test_missing_chapter_is_caught():
    bible = make_bible()
    bible = bible[~((bible["book_code"] == "GEN") & (bible["chapter"] == 50))]
    assert "GEN has 49 chapters, expected 50" in find_problems(bible)


def test_empty_verse_is_caught():
    bible = make_bible()
    bible.loc[0, "text"] = "  "
    assert "1 empty verses" in find_problems(bible)


def test_duplicate_verse_is_caught():
    bible = make_bible()
    bible = pd.concat([bible, bible.head(1)])
    assert "1 duplicate verses" in find_problems(bible)


def test_validate_fails_loudly():
    with pytest.raises(DataQualityError, match="missing books"):
        validate(make_bible().head(10), "test")
