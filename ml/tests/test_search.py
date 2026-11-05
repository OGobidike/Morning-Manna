"""Semantic search (Card 8.2): graded fairly, and it finds what it's asked for.

Like 8.1's tests, these never download a model: the stand-in encoder lights up one slot per
word. The database tests build a pretend Bible (shepherds in the Psalms, fishermen in Matthew)
in a throwaway schema of a Postgres with pgvector; they're skipped without one locally, but
fail in CI.
"""

import hashlib
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, ProgrammingError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_verse_embeddings import pretend_verses, stand_in  # noqa: E402

import search  # noqa: E402
import search_charts as charts  # noqa: E402
import serve  # noqa: E402
import verse_embeddings as ve  # noqa: E402

# The answer key's fingerprint. It was written before any search ran and must never be edited
# after seeing results: with 30 questions, tuning them to the search would grade it on itself
FROZEN = "e4dc49875767958b8d567034a6db9c44"
ASK = search.asking(stand_in, "stand-in")
SHEPHERDS = {("Psalms", 1 + n // 10, 1 + n % 10) for n in range(0, 40, 2)}


def pretend_bible() -> pd.DataFrame:
    """8.1's 40 pretend verses and 20 more fishermen: more than the 40 candidates pgvector's
    index weighs by default, so a long list of results can be tested."""
    verses = pretend_verses()
    more = verses[verses.book == "Matthew"].assign(
        verse_id=lambda v: v.verse_id + 40, chapter=lambda v: v.chapter + 4
    )
    return pd.concat([verses, more], ignore_index=True)


def test_references_become_verses():
    assert search.passages("Psalms 23:1-3; John 3:16; 1 John 4:8") == {
        ("Psalms", 23, 1),
        ("Psalms", 23, 2),
        ("Psalms", 23, 3),
        ("John", 3, 16),
        ("1 John", 4, 8),
    }
    with pytest.raises(ValueError, match="Not a reference"):
        search.passages("Psalm twenty-three")


def test_the_answer_key_is_frozen():
    key = search.QUESTIONS.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.md5(key).hexdigest() == FROZEN, "the answer key changed after it was frozen"
    questions = search.load_questions()
    assert len(questions) == 30 and all(q["relevant"] for q in questions)
    assert len({q["question"] for q in questions}) == 30


def test_grading():
    relevant = {2, 4}
    assert search.grade([1, 2, 3, 4, 5, 6], relevant) == {
        "precision_at_5": 0.4,
        "hit_at_5": 1.0,
        "reciprocal_rank": 0.5,
    }
    missed = search.grade([1, 3, 5, 7, 9, 4], relevant)  # found, but only at 6th
    assert missed == {
        "precision_at_5": 0.0,
        "hit_at_5": 0.0,
        "reciprocal_rank": pytest.approx(1 / 6),
    }
    assert search.grade([], relevant)["reciprocal_rank"] == 0.0


def test_fusion_rewards_agreement():
    meaning, keyword = [1, 2, 3], [3, 4, 1]
    fused = search.fuse(meaning, keyword)
    assert fused[:2] == [1, 3]  # high in both lists beats first in one
    assert set(fused) == {1, 2, 3, 4}  # a verse only one list found still makes it
    assert search.fuse([5, 6], [6, 5]) == [5, 6]  # a tie goes the same way every time


def test_the_bge_prefix_goes_on_questions_only():
    seen = []
    ask = search.asking(lambda texts: seen.extend(texts) or iter([np.ones(3)]), ve.MODEL)
    ask("why do the righteous suffer")
    assert seen == [search.BGE_QUESTION + "why do the righteous suffer"]
    seen.clear()
    search.asking(lambda texts: seen.extend(texts) or iter([np.ones(3)]), search.MINILM)("hi")
    assert seen == ["hi"]


def test_meaning_finds_the_shepherds():
    verses = pretend_bible()
    vectors = ve.embed(verses.text.tolist(), stand_in)
    found = search.by_meaning(vectors, verses.verse_id.to_numpy(), ASK("my shepherd"), depth=5)
    assert all(v % 2 == 1 for v in found)  # the psalms' verses have odd ids


@pytest.fixture
def bible():
    """A pretend Bible in a throwaway schema, its vectors stored the way 8.1 stores them."""
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    url = url.replace("postgresql://", "postgresql+psycopg://")
    schema = f"search_test_{os.getpid()}"
    admin = create_engine(url)
    try:
        with admin.begin() as connection:
            connection.execute(text("create extension if not exists vector"))
            connection.execute(text(f"create schema if not exists {schema}"))
    except OperationalError:
        if os.environ.get("CI"):
            raise
        pytest.skip("no Postgres with pgvector here (docker compose up -d db)")
    # The app's tables (verses, books, translations) are found in the schema first
    engine = create_engine(url, connect_args={"options": f"-c search_path={schema},public"})
    verses = pretend_bible()
    with engine.begin() as connection:
        connection.execute(
            text("create table books (id int primary key, name text, canonical_order int)")
        )
        connection.execute(text("create table translations (id int primary key, code text)"))
        connection.execute(
            text(
                "create table verses (id int primary key, translation_id int, book_id int, "
                "chapter int, verse int, text text)"
            )
        )
        connection.execute(text("insert into books values (19, 'Psalms', 19), (40, 'Matthew', 40)"))
        connection.execute(text("insert into translations values (1, 'KJV'), (2, 'ASV')"))
        connection.execute(
            text("insert into verses values (:id, 1, :book, :chapter, :verse, :text)"),
            [
                {
                    "id": int(v.verse_id),
                    "book": int(v.book_order),
                    "chapter": int(v.chapter),
                    "verse": int(v.verse),
                    "text": v.text,
                }
                for v in verses.itertuples()
            ],
        )
    ve.prepare(engine, schema)
    ve.save(engine, verses, ve.embed(verses.text.tolist(), stand_in), schema=schema)
    yield engine, schema
    engine.dispose()
    with admin.begin() as connection:
        connection.execute(text(f"drop schema if exists {schema} cascade"))
    admin.dispose()


def test_keyword_search_matches_any_word_by_its_stem(bible):
    engine, _ = bible
    shepherds = search.by_keyword(engine, "shepherds", "KJV")  # stem: finds "shepherd"
    assert shepherds and all(v % 2 == 1 for v in shepherds)
    either = set(search.by_keyword(engine, "shepherd or fish", "KJV", depth=60))
    assert len(either) == 60  # any word, not every word: no verse has both
    assert search.by_keyword(engine, "shepherd", "ASV") == []  # only the translation asked for


def test_the_index_weighs_more_than_its_default_40(bible):
    engine, schema = bible
    found = search.by_index(engine, ASK("fish"), "KJV", depth=search.POOL, schema=schema)
    assert len(found) == search.POOL


def test_the_index_never_comes_back_short(bible, monkeypatch):
    engine, schema = bible
    with engine.begin() as connection:  # only two KJV verses left, both about shepherds
        connection.execute(
            text(
                f"update {schema}.verse_embeddings set translation = 'ASV' "
                "where verse_id not in (1, 3)"
            )
        )
    # A table this small is read whole, which is exact; this connection makes Postgres use the
    # index, as it does for the real 62,188 verses
    indexed = create_engine(
        engine.url,
        connect_args={"options": f"-c search_path={schema},public -c enable_seqscan=off"},
    )
    question = ASK("fish")
    with indexed.begin() as connection:  # the index alone: its 2 nearest are ASV fishermen
        connection.execute(text("set local hnsw.ef_search = 2"))
        alone = connection.execute(
            text(
                f"select verse_id from {schema}.verse_embeddings where translation = 'KJV' "
                "order by embedding <=> cast(:q as vector) limit 2"
            ),
            {"q": "[" + ",".join(f"{x:.7f}" for x in question) + "]"},
        ).all()
    assert len(alone) < 2
    monkeypatch.setattr(search, "CANDIDATES", 2)
    assert set(search.by_index(indexed, question, "KJV", 2, schema)) == {1, 3}
    indexed.dispose()


def test_the_index_agrees_with_the_exact_search(bible):
    engine, schema = bible
    verses = pretend_bible()
    vectors = ve.embed(verses.text.tolist(), stand_in)
    question = ASK("the lord is my shepherd")
    exact = search.by_meaning(vectors, verses.verse_id.to_numpy(), question, depth=5)
    indexed = search.by_index(engine, question, "KJV", depth=5, schema=schema)
    assert set(indexed) == set(exact)


def test_every_contestant_is_graded(bible):
    engine, schema = bible
    questions = [{"question": "the lord is my shepherd", "relevant": SHEPHERDS}]
    result = search.run(
        engine, questions, {"bge": stand_in, "minilm": stand_in}, ("KJV",), schema=schema
    )
    assert list(result.board.method) == list(search.METHODS)
    assert (result.board.set_index("method").precision_at_5 == 1.0).all()
    record = search.summary(result)
    assert record.precision_at_5.tolist() == [100] * 5 and (record.questions == 1).all()


def test_search_gives_references_best_first(bible):
    engine, schema = bible
    for method in ("hybrid", "meaning", "keyword"):
        found = search.search(engine, "my shepherd", ASK, "KJV", 3, method, schema=schema)
        assert len(found) == 3
        assert (found.book == "Psalms").all()
        assert list(found.reference) == [
            f"Psalms {c}:{v}" for c, v in zip(found.chapter, found.verse)
        ]
        assert found.text.str.contains("shepherd").all()
    assert search.search(engine, "zzzz", ASK, "KJV", 3, "keyword", schema=schema).empty


def test_the_api_searches(bible, store):
    engine, schema = bible

    def find(question, translation, k, method):
        return search.search(engine, question, ASK, translation, k, method, schema=schema)

    with TestClient(serve.create_app(store, search_with=find)) as client:
        answer = client.get("/search", params={"q": "my shepherd", "k": 3})
        assert answer.status_code == 200
        body = answer.json()
        assert body["method"] == "meaning" and body["translation"] == "KJV"
        assert len(body["verses"]) == 3
        assert all("shepherd" in v["text"] and v["book"] == "Psalms" for v in body["verses"])
        assert body["verses"][0]["reference"].startswith("Psalms ")
        for bad in ({"q": "x"}, {"q": "shepherd", "k": 0}, {"q": "shepherd", "translation": "NIV"}):
            assert client.get("/search", params=bad).status_code == 422


def test_the_api_says_plainly_when_there_are_no_vectors(store):
    def no_table(*_):
        raise ProgrammingError(
            "select", {}, Exception('relation "ml.verse_embeddings" does not exist')
        )

    with TestClient(serve.create_app(store, search_with=no_table)) as client:
        answer = client.get("/search", params={"q": "my shepherd"})
        assert answer.status_code == 503 and "verse_embeddings.py" in answer.json()["detail"]


def test_the_charts():
    rows = [
        {
            "translation": t,
            "question": f"question {n}",
            "method": m,
            "relevant_verses": 5,
            "precision_at_5": (n + len(m)) % 6 / 5,
            "hit_at_5": 1.0,
            "reciprocal_rank": 1.0,
        }
        for t in search.TRANSLATIONS
        for n in range(6)
        for m in search.METHODS
    ]
    graded = pd.DataFrame(rows)
    figures = [charts.leaderboard(graded), charts.questions(graded)]
    assert all(figure.data and figure.layout.title.text for figure in figures)
    low, high = charts.interval(np.array([0.0, 20, 40, 60]))
    assert 0 <= low < 30 < high <= 60
