"""Semantic search (Card 8.2): ask in your own words, get the verses that answer.

A reader types "verses about worry". Keyword search looks for those words, and the KJV says
"take no thought for the morrow", so it misses. Semantic search turns the question into a
vector with the same model that embedded every verse (Card 8.1) and returns the verses that
point the same way.

It's graded the way the models were, against an answer key written before any search ran:
ml/data/search_questions.csv, 30 questions a reader might ask, each with the passages that
truly answer it. Five contestants, on the KJV and the ASV:

    keyword      Postgres's own full-text search: any word of the question, best match first
    bge          the 8.1 model, comparing the question with every verse exactly
    bge_hnsw     the same, but Postgres finds the nearest through its HNSW index (approximate)
    minilm       a second, smaller model, all-MiniLM-L6-v2, for comparison
    hybrid       bge and keyword together, by reciprocal rank fusion

Choices fixed before any result was seen (with 30 questions, tuning on them would be grading
on the answer key): BGE questions carry the prefix its makers recommend for searching
passages; the fusion constant is the standard 60; keyword search matches any word.

Run it from the repo root after python ml/verse_embeddings.py. It takes about 5 minutes, most
of them MiniLM embedding every verse (and the first time, downloading its 90 MB):
    python ml/search.py
It prints the leaderboard and writes ml/results/search.csv and search_by_question.csv.
"""

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

import verse_embeddings as ve

QUESTIONS = Path(__file__).with_name("data") / "search_questions.csv"
TRANSLATIONS = ("KJV", "ASV")
K = 5  # precision@5: the first screen of results
DEPTH = 10  # how far down to look for the first good answer (reciprocal rank)
RRF_K = 60  # reciprocal rank fusion's standard constant
POOL = 50  # how many of each list go into the fusion
CANDIDATES = 100  # how many the HNSW index weighs (pgvector's default, 40, can come back short)
MINILM = "sentence-transformers/all-MiniLM-L6-v2"
# BGE was trained to see short questions with this prefix when searching longer passages
BGE_QUESTION = "Represent this sentence for searching relevant passages: "
METHODS = {
    "keyword": "Keyword search (Postgres full-text)",
    "bge": "Meaning: BGE (Card 8.1)",
    "bge_hnsw": "Meaning: BGE, through Postgres's HNSW index",
    "minilm": "Meaning: MiniLM",
    "hybrid": "Hybrid: BGE and keyword together",
}


# ---- The answer key ----------------------------------------------------------------------

REFERENCE = re.compile(r"^(.+?) (\d+):(\d+)(?:-(\d+))?$")


def passages(refs: str) -> set[tuple[str, int, int]]:
    """'Psalms 23:1-6; John 3:16' as a set of (book, chapter, verse)."""
    found = set()
    for ref in (r.strip() for r in refs.split(";")):
        match = REFERENCE.match(ref)
        if not match:
            raise ValueError(f"Not a reference: {ref!r}")
        book, chapter, first, last = match.groups()
        for verse in range(int(first), int(last or first) + 1):
            found.add((book, int(chapter), verse))
    return found


def load_questions(path: Path = QUESTIONS) -> list[dict]:
    with open(path, newline="") as f:
        return [
            {"question": r["question"], "relevant": passages(r["relevant"])}
            for r in csv.DictReader(f)
        ]


# ---- The contestants ---------------------------------------------------------------------


def asking(encode, model: str = ve.MODEL):
    """Turns a model's encoder (texts to vectors, from verse_embeddings.encoder) into one for a
    single question, with BGE's search prefix."""
    prefix = BGE_QUESTION if "bge" in model.lower() else ""
    return lambda question: np.asarray(next(iter(encode([prefix + question]))), dtype=np.float32)


def by_meaning(
    vectors: np.ndarray, ids: np.ndarray, question: np.ndarray, depth: int = DEPTH
) -> list[int]:
    """The verses whose vectors point most nearly the same way as the question's (exact)."""
    scores = vectors @ (question / np.linalg.norm(question))
    order = np.argsort(-scores, kind="stable")[:depth]
    return [int(i) for i in ids[order]]


def by_index(
    engine, question: np.ndarray, translation: str, depth: int = DEPTH, schema: str = ve.SCHEMA
) -> list[int]:
    """The same, but Postgres finds them itself, through the HNSW index (approximate).

    The index gathers its nearest candidates from both translations, then drops the other
    one's, so it can come back short: with pgvector's default of 40 candidates, "the Lord's
    prayer" on the ASV found 2 verses, not 10. So it weighs more candidates, and if it's still
    short, compares every verse of the translation instead (exact, about 30 ms)."""

    def nearest(order: str):
        return text(
            f"""
            select verse_id from {schema}.{ve.TABLE}
            where translation = :translation
            order by {order}
            limit :depth
            """
        )

    params = {
        "translation": translation,
        "question": "[" + ",".join(f"{x:.7f}" for x in question) + "]",
        "depth": depth,
    }
    distance = "embedding <=> cast(:question as vector)"
    with engine.begin() as connection:
        connection.execute(text(f"set local hnsw.ef_search = {max(CANDIDATES, int(depth))}"))
        found = [row.verse_id for row in connection.execute(nearest(distance), params)]
        if len(found) < depth:  # "+ 0" is an order the index can't give, so every verse is read
            found = [
                row.verse_id for row in connection.execute(nearest(f"({distance}) + 0"), params)
            ]
        return found


def by_keyword(engine, question: str, translation: str, depth: int = DEPTH) -> list[int]:
    """Postgres's full-text search: verses holding any of the question's words (as stems, so
    'worry' finds 'worried'), the best match first."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                with q as (
                    select to_tsquery('english',
                        replace(plainto_tsquery('english', :question)::text, '&', '|')) as query
                )
                select v.id
                from verses as v
                join translations as t on t.id = v.translation_id, q
                where t.code = :translation
                  and to_tsvector('english', v.text) @@ q.query
                order by ts_rank_cd(to_tsvector('english', v.text), q.query) desc, v.id
                limit :depth
                """
            ),
            {"question": question, "translation": translation, "depth": depth},
        )
        return [row.id for row in rows]


def fuse(*rankings: list[int], depth: int = DEPTH, k: int = RRF_K) -> list[int]:
    """Reciprocal rank fusion: each list gives a verse 1 / (k + its rank). Verses near the
    top of both lists win; a verse only one list found can still make it."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, verse in enumerate(ranking, start=1):
            scores[verse] = scores.get(verse, 0.0) + 1 / (k + rank)
    return sorted(scores, key=lambda v: (-scores[v], v))[:depth]


# ---- Grading -----------------------------------------------------------------------------


def grade(found: list[int], relevant: set[int], k: int = K) -> dict[str, float]:
    """precision@k: the share of the first k results that answer the question. hit@k: did any
    of them? reciprocal rank: 1 over where the first good answer sits (0 if none in sight)."""
    top = found[:k]
    first = next((n for n, v in enumerate(found, start=1) if v in relevant), None)
    return {
        "precision_at_5": sum(v in relevant for v in top) / k,
        "hit_at_5": float(any(v in relevant for v in top)),
        "reciprocal_rank": 1 / first if first else 0.0,
    }


@dataclass
class Library:
    """One translation's verses and vectors, from each model."""

    verses: pd.DataFrame
    vectors: dict[str, np.ndarray]  # model name -> one row per verse, in verses' order

    def relevant(self, wanted: set[tuple[str, int, int]]) -> set[int]:
        keys = zip(self.verses.book, self.verses.chapter, self.verses.verse, strict=True)
        return {int(v) for v, key in zip(self.verses.verse_id, keys, strict=True) if key in wanted}


def load_library(engine, translation: str, minilm_encode=None, schema: str = ve.SCHEMA) -> Library:
    """A translation's verses, their stored BGE vectors, and (if given an encoder) MiniLM's."""
    verses = ve.load_verses(engine)
    verses = verses[verses.translation == translation].reset_index(drop=True)
    stored = ve.load_vectors(engine, schema).set_index("verse_id").embedding
    vectors = {"bge": np.vstack(stored[verses.verse_id].to_numpy())}
    if minilm_encode is not None:
        found = ve.embed(ve.for_embedding(verses), minilm_encode)
        vectors["minilm"] = found / np.linalg.norm(found, axis=1, keepdims=True)
    return Library(verses, vectors)


def answers(
    engine,
    library: Library,
    translation: str,
    question: str,
    asks: dict,
    schema: str = ve.SCHEMA,
) -> dict[str, list[int]]:
    """Every contestant's ranked verses for one question."""
    ids = library.verses.verse_id.to_numpy()
    bge_question = asks["bge"](question)
    found = {
        "keyword": by_keyword(engine, question, translation),
        "bge": by_meaning(library.vectors["bge"], ids, bge_question),
        "bge_hnsw": by_index(engine, bge_question, translation, schema=schema),
    }
    if "minilm" in library.vectors:
        found["minilm"] = by_meaning(library.vectors["minilm"], ids, asks["minilm"](question))
    found["hybrid"] = fuse(
        by_meaning(library.vectors["bge"], ids, bge_question, depth=POOL),
        by_keyword(engine, question, translation, depth=POOL),
    )
    return found


@dataclass
class Result:
    graded: pd.DataFrame  # one row per translation, question and contestant
    board: pd.DataFrame
    found: dict  # (translation, question, method) -> ranked verse ids
    libraries: dict[str, Library]


def run(
    engine,
    questions: list[dict] | None = None,
    encoders: dict | None = None,
    translations=TRANSLATIONS,
    schema: str = ve.SCHEMA,
) -> Result:
    questions = questions or load_questions()
    if encoders is None:  # each model loads once, for the verses and the questions alike
        encoders = {"bge": ve.encoder(ve.MODEL), "minilm": ve.encoder(MINILM)}
    models = {"bge": ve.MODEL, "minilm": MINILM}
    asks = {name: asking(encode, models[name]) for name, encode in encoders.items()}
    rows, found, libraries = [], {}, {}
    for translation in translations:
        library = load_library(engine, translation, encoders.get("minilm"), schema)
        libraries[translation] = library
        for q in questions:
            relevant = library.relevant(q["relevant"])
            for method, ranking in answers(
                engine, library, translation, q["question"], asks, schema
            ).items():
                found[(translation, q["question"], method)] = ranking
                rows.append(
                    {
                        "translation": translation,
                        "question": q["question"],
                        "method": method,
                        "relevant_verses": len(relevant),
                        **grade(ranking, relevant),
                    }
                )
    graded = pd.DataFrame(rows)
    return Result(graded, leaderboard(graded), found, libraries)


def leaderboard(graded: pd.DataFrame) -> pd.DataFrame:
    board = (
        graded.groupby(["method", "translation"], sort=False)[
            ["precision_at_5", "hit_at_5", "reciprocal_rank"]
        ]
        .mean()
        .reset_index()
        .rename(columns={"reciprocal_rank": "mrr"})
    )
    board["method"] = pd.Categorical(board.method, list(METHODS), ordered=True)
    board["translation"] = pd.Categorical(board.translation, list(TRANSLATIONS), ordered=True)
    return board.sort_values(["translation", "method"]).reset_index(drop=True)


def summary(result: Result) -> pd.DataFrame:
    """The record, in whole percents: computers can round a near-tie differently, and one
    swapped result moves precision@5 by under a point."""
    board = result.board.copy()
    for column in ("precision_at_5", "hit_at_5", "mrr"):
        board[column] = (board[column] * 100).round().astype(int)
    board["questions"] = result.graded.question.nunique()
    return board


# ---- Searching, for the API --------------------------------------------------------------


def search(
    engine,
    question: str,
    encode,
    translation: str = "KJV",
    k: int = K,
    method: str = "meaning",
    schema: str = ve.SCHEMA,
) -> pd.DataFrame:
    """The verses that answer a question, best first, with their references and text. Meaning
    (BGE, the winner on the labelled questions) comes through the HNSW index, so it stays fast
    whatever the size of the Bible."""
    if method == "keyword":
        ids = by_keyword(engine, question, translation, depth=k)
    elif method == "meaning":
        ids = by_index(engine, encode(question), translation, depth=k, schema=schema)
    else:
        ids = fuse(
            by_index(engine, encode(question), translation, depth=POOL, schema=schema),
            by_keyword(engine, question, translation, depth=POOL),
            depth=k,
        )
    if not ids:
        return pd.DataFrame(columns=["verse_id", "reference", "book", "chapter", "verse", "text"])
    with engine.connect() as connection:
        rows = pd.read_sql(
            text(
                """
                select v.id as verse_id, b.name as book, v.chapter, v.verse, v.text
                from verses as v join books as b on b.id = v.book_id
                where v.id = any(:ids)
                """
            ),
            connection,
            params={"ids": ids},
        )
    rows = rows.set_index("verse_id").loc[ids].reset_index()
    rows.insert(1, "reference", [f"{r.book} {r.chapter}:{r.verse}" for r in rows.itertuples()])
    return rows


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    result = run(engine)
    print(
        f"Graded on {result.graded.question.nunique()} questions, written before any search "
        "ran, on the KJV and the ASV\n"
    )
    shown = result.board.assign(
        method=result.board.method.map(METHODS),
        **{
            c: (result.board[c] * 100).map("{:.0f}%".format) for c in ("precision_at_5", "hit_at_5")
        },
        mrr=result.board.mrr.map("{:.2f}".format),
    )
    print(shown.to_string(index=False))
    results = Path(__file__).with_name("results")
    summary(result).to_csv(results / "search.csv", index=False, lineterminator="\n")
    result.graded.round(4).to_csv(
        results / "search_by_question.csv", index=False, lineterminator="\n"
    )
    print("\nThe record: ml/results/search.csv, and each question's in search_by_question.csv")
