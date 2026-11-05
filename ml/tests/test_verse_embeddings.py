"""Verse embeddings (Card 8.1): vectors stay with their verses, and Postgres finds the nearest.

These never download the model: a stand-in encoder turns words into vectors, enough to test
everything around the model. The storage tests need Postgres with pgvector (docker compose's
db, or CI's): they're skipped without one locally, but fail in CI.
"""

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verse_embeddings as ve  # noqa: E402
import verse_embeddings_charts as charts  # noqa: E402


def stand_in(texts):
    """A pretend model: each word lights up one of 384 slots, then the vector gets length 1.
    Verses sharing words point the same way, which is all these tests need."""
    for t in texts:
        vector = np.zeros(ve.DIMS, dtype=np.float32)
        for word in t.lower().split():
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % ve.DIMS] += 1
        yield vector / max(np.linalg.norm(vector), 1e-9)


def pretend_verses() -> pd.DataFrame:
    """Two topics in two sections: shepherds in the poetry, fishermen in the gospels."""
    rows = []
    for n in range(40):
        poetry = n % 2 == 0
        rows.append(
            {
                "verse_id": n + 1,
                "translation": "KJV",
                "book_order": 19 if poetry else 40,
                "book": "Psalms" if poetry else "Matthew",
                "chapter": 1 + n // 10,
                "verse": 1 + n % 10,
                "text": (
                    "the lord is my shepherd green pastures still waters sheep"
                    if poetry
                    else "fishers of men nets boat sea galilee fish"
                )
                + f" word{n}",
            }
        )
    verses = pd.DataFrame(rows)
    verses["section"] = verses.book_order.map(ve.section)
    return verses


def test_every_book_has_a_section():
    assert [ve.section(b) for b in (1, 5, 6, 19, 23, 40, 44, 45, 65, 66)] == [
        "The Law",
        "The Law",
        "History",
        "Poetry and wisdom",
        "The prophets",
        "Gospels and Acts",
        "Gospels and Acts",
        "Letters",
        "Letters",
        "Revelation",
    ]
    assert sum(len(books) for books in ve.SECTIONS.values()) == 66


def test_vectors_come_back_in_the_verses_order():
    texts = ["a much longer verse than the others here", "short", "middling verse"]
    vectors = ve.embed(texts, stand_in)
    expected = np.array(list(stand_in(texts)))
    assert np.allclose(vectors, expected)  # embedded shortest first, but put back in order


def test_psalm_headings_are_left_out_of_the_vectors():
    cases = {
        "A Psalm of David. The Lord is my shepherd; I shall not want.":
            "The Lord is my shepherd; I shall not want.",
        "For the Chief Musician; on stringed instruments. A Psalm of David. Answer me when I call":
            "Answer me when I call",
        "To the chief Musician on Neginoth, Maschil, A Psalm of David, when the Ziphims came and "
        "said to Saul, Doth not David hide himself with us? Save me, O God, by thy name":
            "Save me, O God, by thy name",
        "Why do the heathen rage, and the people imagine a vain thing?":
            "Why do the heathen rage, and the people imagine a vain thing?",
        "Praise ye the Lord. Praise God in his sanctuary.":  # no heading: nothing goes
            "Praise ye the Lord. Praise God in his sanctuary.",
    }
    for verse, expected in cases.items():
        assert ve.without_heading(verse) == expected
    verses = pd.DataFrame({"book": ["Psalms", "Psalms", "Matthew"], "verse": [1, 2, 1],
                           "text": ["A Psalm of David. Hear me.", "A Psalm of David. Hear me.",
                                    "A Psalm of David. Hear me."]})
    assert ve.for_embedding(verses) == ["Hear me.", "A Psalm of David. Hear me.",
                                        "A Psalm of David. Hear me."]  # psalms' first verses only


def test_neighbours_from_the_same_section_beat_chance():
    verses = pretend_verses()
    vectors = ve.embed(verses.text.tolist(), stand_in)
    table = ve.check(verses, vectors, size=20, k=3).set_index("section")
    assert table.loc["All", "same_section"] == 1.0
    assert table.loc["All", "chance_section"] == pytest.approx(0.5)
    assert set(table.index) == {"Poetry and wisdom", "Gospels and Acts", "All"}


def test_the_sample_is_the_same_whatever_the_ids():
    verses = pretend_verses()
    renumbered = verses.assign(verse_id=verses.verse_id + 1000)
    first = ve.sample(verses, 10)
    assert list(first.text) == list(ve.sample(renumbered, 10).text)


@pytest.fixture
def warehouse():
    """A throwaway schema in a Postgres that has pgvector."""
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://"))
    try:
        with engine.begin() as connection:
            connection.execute(text("create extension if not exists vector"))
    except OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip("no Postgres with pgvector here (docker compose up -d db)")
    schema = f"ml_test_{os.getpid()}"
    yield engine, schema
    with engine.begin() as connection:
        connection.execute(text(f"drop schema if exists {schema} cascade"))


def test_saving_and_finding_the_nearest_in_postgres(warehouse):
    engine, schema = warehouse
    verses = pretend_verses()
    vectors = ve.embed(verses.text.tolist(), stand_in)
    ve.prepare(engine, schema)
    ve.save(engine, verses.head(30), vectors[:30], schema=schema)
    assert ve.already_done(engine, schema=schema) == set(range(1, 31))
    ve.save(engine, verses.tail(10), vectors[30:], schema=schema)  # only the new ones
    assert len(ve.already_done(engine, schema=schema)) == 40
    found = ve.nearest(engine, 1, k=5, schema=schema)  # a shepherd verse
    assert len(found) == 5 and all(v % 2 == 1 for v in found)  # every neighbour a shepherd
    stored = ve.load_vectors(engine, schema)
    assert np.allclose(np.vstack(stored.embedding), vectors, atol=1e-6)


def test_a_new_model_replaces_the_old_ones_vectors(warehouse):
    engine, schema = warehouse
    verses = pretend_verses().head(5)
    vectors = ve.embed(verses.text.tolist(), stand_in)
    ve.prepare(engine, schema)
    ve.save(engine, verses, vectors, model="an-old-model", schema=schema)
    ve.save(engine, verses.head(2), vectors[:2], schema=schema)
    assert ve.already_done(engine, schema=schema) == {1, 2}
    assert ve.already_done(engine, model="an-old-model", schema=schema) == set()


def test_the_charts():
    verses = pretend_verses()
    vectors = ve.embed(verses.text.tolist(), stand_in)
    result = ve.Result(verses, 0, 0.0, ve.check(verses, vectors, size=20, k=3))
    figures = [charts.chapter_map(verses, vectors), charts.agreement(result.checked)]
    assert all(figure.data and figure.layout.title.text for figure in figures)
