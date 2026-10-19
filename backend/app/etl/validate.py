

"""Validate: data-quality checks that stop the pipeline if the data looks wrong."""

import pandas as pd

from app.etl.books import BOOKS


class DataQualityError(Exception):
    """Raised when clean data breaks a quality rule."""


def find_problems(df: pd.DataFrame) -> list[str]:
    """Return every rule the data breaks. An empty list means all is well."""
    problems = []

    # Rule 1: all 66 books are present
    found = set(df["book_code"])
    missing = [book.code for book in BOOKS if book.code not in found]
    if missing:
        problems.append(f"missing books: {missing}")

    # Rule 2: every book has the expected number of chapters
    chapters = df.groupby("book_code")["chapter"].nunique()
    for book in BOOKS:
        if book.code in found and chapters[book.code] != book.chapters:
            problems.append(
                f"{book.code} has {chapters[book.code]} chapters, expected {book.chapters}"
            )

    # Rule 3: no empty verses
    empty = int((df["text"].str.strip() == "").sum())
    if empty:
        problems.append(f"{empty} empty verses")

    # Rule 4: no verse appears twice
    duplicates = int(df.duplicated(["book_code", "chapter", "verse"]).sum())
    if duplicates:
        problems.append(f"{duplicates} duplicate verses")

    # Rule 5: chapter and verse numbers start at 1
    if (df["chapter"] < 1).any() or (df["verse"] < 1).any():
        problems.append("chapter or verse numbers below 1")

    return problems


def validate(df: pd.DataFrame, label: str) -> None:
    """Fail loudly if the data breaks any rule."""
    problems = find_problems(df)
    if problems:
        raise DataQualityError(f"{label} failed data-quality checks: " + "; ".join(problems))
