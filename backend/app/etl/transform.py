

"""Transform: turn raw rows into clean rows that match our tables."""

import re

import pandas as pd

from app.etl.books import BOOKS

# Our display name -> our code, e.g. "1 Samuel" -> "1SA"
CODE_BY_NAME = {book.name: book.code for book in BOOKS}
# Our code -> position in the Bible, used for sorting
ORDER_BY_CODE = {book.code: order for order, book in enumerate(BOOKS, start=1)}

# Book names a source spells differently from us
NAME_ALIASES = {"Revelation of John": "Revelation"}

# Roman numerals at the start of a name, e.g. "II Kings" (longest first, so "III" wins over "I")
ROMAN_PREFIX = re.compile(r"^(III|II|I) ")
ROMAN_TO_DIGIT = {"I": "1", "II": "2", "III": "3"}


def normalise_book_name(name: str) -> str:
    """Turn a source's book name into ours, e.g. "II Kings" -> "2 Kings"."""
    name = name.strip()
    name = NAME_ALIASES.get(name, name)
    return ROMAN_PREFIX.sub(lambda match: ROMAN_TO_DIGIT[match.group(1)] + " ", name)


def clean_text(text: str) -> str:
    """Remove editorial brackets and tidy spaces, e.g. "[but]  he " -> "but he"."""
    text = text.replace("[", "").replace("]", "")
    # split() breaks on any run of whitespace; join puts single spaces back
    return " ".join(text.split())


def transform(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Clean the raw rows. Returns (clean rows, how many rows were rejected).

    Clean rows have the columns book_code, chapter, verse and text, sorted in Bible order.
    """
    df = pd.DataFrame(
        {
            "book_code": raw["Book"].map(normalise_book_name).map(CODE_BY_NAME),
            "chapter": pd.to_numeric(raw["Chapter"], errors="coerce"),
            "verse": pd.to_numeric(raw["Verse"], errors="coerce"),
            "text": raw["Text"].map(clean_text),
        }
    )

    # Keep only usable rows: a known book, numeric chapter and verse, and some text
    usable = (
        df["book_code"].notna()
        & df["chapter"].notna()
        & df["verse"].notna()
        & (df["text"] != "")
    )
    rejected = int((~usable).sum())
    df = df[usable].astype({"chapter": int, "verse": int})

    # Sort in Bible order: book, then chapter, then verse
    df = df.assign(order=df["book_code"].map(ORDER_BY_CODE))
    df = df.sort_values(["order", "chapter", "verse"]).drop(columns="order")
    return df.reset_index(drop=True), rejected
