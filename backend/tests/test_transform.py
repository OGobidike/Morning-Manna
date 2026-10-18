

"""Tests for the transform step of the scripture pipeline."""

import pandas as pd

from app.etl.transform import clean_text, normalise_book_name, transform


def test_normalise_book_name_turns_roman_numerals_into_digits():
    assert normalise_book_name("I Samuel") == "1 Samuel"
    assert normalise_book_name("II Kings") == "2 Kings"
    assert normalise_book_name("III John") == "3 John"


def test_normalise_book_name_uses_aliases():
    assert normalise_book_name("Revelation of John") == "Revelation"


def test_normalise_book_name_leaves_normal_names_alone():
    assert normalise_book_name("Isaiah") == "Isaiah"


def test_clean_text_removes_brackets_and_extra_spaces():
    assert clean_text("  the Father: [but]  he that ") == "the Father: but he that"
    assert clean_text("upon thy people. [Selah") == "upon thy people. Selah"


def test_transform_maps_books_types_and_order():
    raw = pd.DataFrame(
        {
            "Book": ["John", "Genesis", "I John"],
            "Chapter": ["3", "1", "1"],
            "Verse": ["16", "1", "1"],
            "Text": ["For God so loved", "In the beginning", "That which was"],
        }
    )
    clean, rejected = transform(raw)

    assert rejected == 0
    # Sorted in Bible order: Genesis, John, 1 John
    assert list(clean["book_code"]) == ["GEN", "JHN", "1JN"]
    # Chapter and verse became numbers
    assert clean.loc[1, "chapter"] == 3
    assert clean.loc[1, "verse"] == 16


def test_transform_rejects_unusable_rows():
    raw = pd.DataFrame(
        {
            "Book": ["Genesis", "Genesis", "Narnia", "Genesis"],
            "Chapter": ["1", "1", "1", "x"],
            "Verse": ["1", "2", "1", "3"],
            "Text": ["In the beginning", "   ", "Aslan", "And God said"],
        }
    )
    clean, rejected = transform(raw)

    # Rejected: the empty verse, the unknown book, and the non-numeric chapter
    assert rejected == 3
    assert list(clean["text"]) == ["In the beginning"]
