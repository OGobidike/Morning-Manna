"""Verse embeddings (Card 8.1): every verse turned into a vector of its meaning, in Postgres.

A sentence-transformer model reads each verse and gives back 384 numbers. Verses that mean
similar things get vectors that point the same way, whatever words they use, so "be not
afraid" and "fear not" end up close together. That's what semantic search (Card 8.2), topic
tags (8.3) and recommendations (8.4) are built on.

The model is BAAI's bge-small-en-v1.5, run with FastEmbed: the same model as in the
sentence-transformers library, exported to ONNX, so it needs no PyTorch (about 30 MB of
libraries instead of 2 GB). It downloads once (67.5 MB) into FastEmbed's cache.

The vectors go into ml.verse_embeddings, a pgvector column with an HNSW index: Postgres itself
can then find the nearest verses to any vector, fast. Only verses not yet embedded with this
model are embedded, so a second run takes seconds.

Is it any good? There's no answer key for meaning yet (Card 8.2 brings labelled questions),
but the Bible has a structure the model never saw: its sections (the Law, history, poetry,
the prophets, the gospels, the letters). If the vectors capture meaning, a verse's nearest
neighbours should mostly come from the same section. check() measures that against chance.

Run it from the repo root (all 62,188 verses take a few minutes the first time):
    python ml/verse_embeddings.py
"""

import hashlib
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    select,
    text,
)

MODEL = "BAAI/bge-small-en-v1.5"
DIMS = 384
BATCH = 32  # small batches: each one is padded to its longest verse
SCHEMA, TABLE = "ml", "verse_embeddings"
NEIGHBOURS = 5
SAMPLE = 2000  # verses checked against their nearest neighbours
CHECK_TRANSLATION = "KJV"

# The Bible's sections, by each book's place in it (1 is Genesis, 66 is Revelation)
SECTIONS = {
    "The Law": range(1, 6),
    "History": range(6, 18),
    "Poetry and wisdom": range(18, 23),
    "The prophets": range(23, 40),
    "Gospels and Acts": range(40, 45),
    "Letters": range(45, 66),
    "Revelation": range(66, 67),
}


def section(book_order: int) -> str:
    return next(name for name, books in SECTIONS.items() if book_order in books)


# ---- The verses --------------------------------------------------------------------------


def load_verses(engine) -> pd.DataFrame:
    """Every verse in every translation, in Bible order."""
    with engine.connect() as connection:
        verses = pd.read_sql(
            text(
                """
                select v.id as verse_id, t.code as translation, b.canonical_order as book_order,
                       b.name as book, v.chapter, v.verse, v.text
                from verses as v
                join translations as t on t.id = v.translation_id
                join books as b on b.id = v.book_id
                order by t.code, b.canonical_order, v.chapter, v.verse
                """
            ),
            connection,
        )
    verses["section"] = verses.book_order.map(section)
    return verses


# In this Bible's text, each psalm's heading is part of verse 1 ("A Psalm of David. The Lord is
# my shepherd"). Left in, the model matches headings to headings instead of shepherds to
# shepherds, so the vectors are made without them. The text readers see is never changed.
HEADING = re.compile(
    r"Psalm|Song|Musician|Maschil|Michtam|Shiggaion|Prayer of|of David|of Asaph|Korah|"
    r"Solomon|of Moses|Ezrahite|Dedication",
    re.IGNORECASE,
)


def without_heading(text: str) -> str:
    """A psalm's first verse without its heading: leading sentences that name a psalm, a song,
    the chief musician or a psalmist go. One that runs on into the verse itself is left be."""
    sentences = re.split(r"(?<=[.?])\s+", text)
    while len(sentences) > 1 and HEADING.search(sentences[0]):
        sentences.pop(0)
    return " ".join(sentences)


def for_embedding(verses: pd.DataFrame) -> list[str]:
    """The text each verse is embedded from."""
    first = (verses.book == "Psalms") & (verses.verse == 1)
    return [without_heading(t) if f else t for t, f in zip(verses.text, first, strict=True)]


def reference(row) -> str:
    return f"{row.book} {row.chapter}:{row.verse}"


# ---- Embedding ---------------------------------------------------------------------------


def encoder(model: str = MODEL):
    """The real model: a function from texts to vectors (it downloads the model the first
    time)."""
    from fastembed import TextEmbedding

    # Kept in the home folder, not FastEmbed's default temporary one, which WSL empties on a
    # restart (and the model would download again)
    cache = os.environ.get("FASTEMBED_CACHE_PATH", str(Path.home() / ".cache" / "fastembed"))
    embedding = TextEmbedding(model, cache_dir=cache)
    return lambda texts: embedding.embed(texts, batch_size=BATCH)


def embed(texts: list[str], encode) -> np.ndarray:
    """One vector per text, in the same order. Texts are embedded shortest first, so each
    batch holds verses of about the same length (about 1.7 times faster), then put back."""
    order = np.argsort([len(t) for t in texts], kind="stable")
    vectors = np.asarray(list(encode([texts[i] for i in order])), dtype=np.float32)
    out = np.empty_like(vectors)
    out[order] = vectors
    return out


# ---- Storing -----------------------------------------------------------------------------


def embeddings_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    return Table(
        TABLE,
        metadata,
        Column("verse_id", Integer, primary_key=True),
        Column("translation", Text, nullable=False),
        Column("model", Text, nullable=False),
        Column("embedding", Vector(DIMS), nullable=False),
        Column("embedded_at", DateTime(timezone=True), nullable=False),
        schema=schema,
    )


def prepare(engine, schema: str = SCHEMA) -> None:
    """The pgvector extension, the schema and the table, if they're missing."""
    with engine.begin() as connection:
        connection.execute(text("create extension if not exists vector"))
        connection.execute(text(f"create schema if not exists {schema}"))
        embeddings_table(MetaData(), schema).create(connection, checkfirst=True)


def already_done(engine, model: str = MODEL, schema: str = SCHEMA) -> set[int]:
    """The verses embedded with this model already."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(f"select verse_id from {schema}.{TABLE} where model = :model"), {"model": model}
        )
        return {row.verse_id for row in rows}


def save(
    engine, verses: pd.DataFrame, vectors: np.ndarray, model: str = MODEL, schema: str = SCHEMA
) -> None:
    """Add the new verses' vectors in one transaction. Vectors from any other model are removed
    first, since vectors from two models can't be compared. Then the HNSW index, which lets
    Postgres find the nearest vectors without comparing against every one."""
    table = embeddings_table(MetaData(), schema)
    now = datetime.now(UTC)
    rows = [
        {
            "verse_id": int(v),
            "translation": t,
            "model": model,
            "embedding": vector,
            "embedded_at": now,
        }
        for v, t, vector in zip(verses.verse_id, verses.translation, vectors, strict=True)
    ]
    with engine.begin() as connection:
        connection.execute(table.delete().where(table.c.model != model))
        if rows:
            connection.execute(table.insert(), rows)
        connection.execute(
            text(
                f"create index if not exists {TABLE}_hnsw on {schema}.{TABLE} "
                "using hnsw (embedding vector_cosine_ops)"
            )
        )


def load_vectors(engine, schema: str = SCHEMA) -> pd.DataFrame:
    """Every stored vector, by verse. Read through the table, whose pgvector column turns
    Postgres's vectors back into numpy arrays (plain SQL would hand back text)."""
    table = embeddings_table(MetaData(), schema)
    with engine.connect() as connection:
        rows = connection.execute(
            select(table.c.verse_id, table.c.embedding).order_by(table.c.verse_id)
        ).all()
    return pd.DataFrame(
        {"verse_id": [r.verse_id for r in rows],
         "embedding": [np.asarray(r.embedding, dtype=np.float32) for r in rows]}
    )


def nearest(engine, verse_id: int, k: int = NEIGHBOURS, schema: str = SCHEMA) -> list[int]:
    """The k verses closest in meaning to this one, in the same translation, found by
    Postgres itself (<=> is pgvector's cosine distance)."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                f"""
                select e.verse_id
                from {schema}.{TABLE} as e,
                     (select embedding, translation from {schema}.{TABLE}
                      where verse_id = :verse_id) as me
                where e.translation = me.translation and e.verse_id <> :verse_id
                order by e.embedding <=> me.embedding
                limit :k
                """
            ),
            {"verse_id": verse_id, "k": k},
        )
        return [row.verse_id for row in rows]


# ---- Checking ----------------------------------------------------------------------------


def sample(verses: pd.DataFrame, size: int = SAMPLE) -> pd.DataFrame:
    """A fixed sample, picked by a hash of each verse's place in the Bible, so it's the same
    on every machine whatever the database ids are."""
    key = [
        hashlib.md5(f"{r.book_order}:{r.chapter}:{r.verse}".encode()).hexdigest()
        for r in verses.itertuples()
    ]
    return verses.assign(key=key).sort_values("key").head(size).drop(columns="key")


def check(
    verses: pd.DataFrame, vectors: np.ndarray, size: int = SAMPLE, k: int = NEIGHBOURS
) -> pd.DataFrame:
    """For a sample of verses, how often their nearest neighbours come from the same section
    and the same book, against what picking verses at random would give."""
    verses = verses.reset_index(drop=True)
    picked = sample(verses, size)
    top = np.empty((len(picked), k), dtype=int)
    for start in range(0, len(picked), 250):  # in chunks, to keep memory small
        rows = picked.index[start:start + 250]
        similarity = vectors[rows] @ vectors.T  # the vectors have length 1: this is cosine
        similarity[np.arange(len(rows)), rows] = -np.inf  # not itself
        top[start:start + 250] = np.argsort(-similarity, axis=1, kind="stable")[:, :k]
    rows = []
    for name in [*SECTIONS, "All"]:
        mine = (picked.section == name).to_numpy() if name != "All" else np.ones(len(picked), bool)
        if not mine.any():
            continue
        neighbours = verses.iloc[top[mine].ravel()]
        own = picked[mine].loc[picked[mine].index.repeat(k)]
        share = verses.section.value_counts(normalize=True)
        books = verses.book.value_counts(normalize=True)
        rows.append(
            {
                "section": name,
                "verses": int(mine.sum()),
                "same_section": float(
                    (neighbours.section.to_numpy() == own.section.to_numpy()).mean()
                ),
                "chance_section": float(share[own.section].mean()),
                "same_book": float((neighbours.book.to_numpy() == own.book.to_numpy()).mean()),
                "chance_book": float(books[own.book].mean()),
            }
        )
    return pd.DataFrame(rows)


# ---- The whole run -----------------------------------------------------------------------


@dataclass
class Result:
    verses: pd.DataFrame  # every verse
    embedded_now: int
    seconds: float
    checked: pd.DataFrame


def run(engine, encode=None, schema: str = SCHEMA) -> Result:
    verses = load_verses(engine)
    prepare(engine, schema)
    todo = verses[~verses.verse_id.isin(already_done(engine, MODEL, schema))]
    started = time.perf_counter()
    if len(todo):
        vectors = embed(for_embedding(todo), encode or encoder())
        save(engine, todo, vectors, MODEL, schema)
    seconds = time.perf_counter() - started
    stored = load_vectors(engine, schema).set_index("verse_id").embedding
    graded = verses[verses.translation == CHECK_TRANSLATION]
    vectors = np.vstack(stored[graded.verse_id].to_numpy())
    return Result(verses, len(todo), seconds, check(graded, vectors))


def summary(result: Result) -> pd.DataFrame:
    """The record, in whole percents: tiny differences between computers' arithmetic can swap
    a far neighbour or two, and shouldn't change it."""
    table = result.checked.copy()
    for column in ("same_section", "chance_section", "same_book", "chance_book"):
        table[column] = (table[column] * 100).round().astype(int)
    table.insert(0, "model", MODEL)
    table["verses_embedded"] = len(result.verses)
    return table


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    result = run(engine)
    counts = result.verses.translation.value_counts().sort_index()
    print(
        f"{len(result.verses):,} verses ("
        + ", ".join(f"{t} {n:,}" for t, n in counts.items())
        + f"), model {MODEL}"
    )
    if result.embedded_now:
        print(
            f"Embedded {result.embedded_now:,} new verses in {result.seconds:.0f} s "
            f"({result.embedded_now / result.seconds:.0f} a second)"
        )
    else:
        print("Every verse was already embedded with this model")
    verses = result.verses.set_index("verse_id")
    print("\nThe nearest verses in meaning, found by Postgres (pgvector):")
    for book, chapter, verse in (("Psalms", 23, 1), ("Matthew", 6, 34), ("John", 3, 16)):
        me = verses[
            (verses.translation == CHECK_TRANSLATION)
            & (verses.book == book)
            & (verses.chapter == chapter)
            & (verses.verse == verse)
        ]
        if me.empty:
            continue
        found = nearest(engine, int(me.index[0]), k=3)
        print(f"  {book} {chapter}:{verse} → " + "; ".join(reference(verses.loc[v]) for v in found))
    table = summary(result)
    every = table[table.section == "All"].iloc[0]
    print(
        f"\nChecked on {SAMPLE:,} {CHECK_TRANSLATION} verses: their {NEIGHBOURS} nearest "
        f"neighbours come from the same section {every.same_section}% of the time "
        f"(chance: {every.chance_section}%), and the same book {every.same_book}% "
        f"(chance: {every.chance_book}%)"
    )
    out = Path(__file__).with_name("results") / "verse_embeddings.csv"
    table.to_csv(out, index=False, lineterminator="\n")
    print(
        f"\nThe record: {out.relative_to(Path(__file__).resolve().parents[1])}; "
        f"every verse's vector: {SCHEMA}.{TABLE}"
    )
