"""Topic tags (Card 8.3): every verse tagged with what it's about, graded by Nave's.

A reader who finishes a passage about worry might want more on worry; a reader who wants
"verses about patience" needs them found. So every verse gets topic tags, from 30 that a reader
would recognise: worry and anxiety, comfort, forgiveness, patience, money and greed, and so on
(ml/data/topic_tags.csv).

The answer key is Nave's Topical Bible (Orville J. Nave, 1896, public domain), from Brady
Stephenson's BibleData CSV (CC BY 4.0, https://github.com/BradyStephenson/bible-data). Each tag
was mapped to Nave's headings before any tagger ran, by rules fixed beforehand:
    - only teaching headings ("General scriptures concerning", "REMEDY FOR"); never the story
      lists ("EXEMPLIFIED", "INSTANCES OF"), whose verses often don't say the topic, and never
      the opposite sense ("OF THE WICKED")
    - only the references on the chosen heading's own line
    - a tag needs at least 20 verses in the key
python ml/topics.py --build-key turns them into ml/data/topic_key.csv, which is committed.

Three taggers race, graded on whole books they never saw (3 groups, by a hash of the name):
    keyword      the tag's everyday words, found in the verse (Postgres full-text)
    zero_shot    the tag's description, as a BGE question, against the verse's vector
    trained      a logistic regression per tag on the BGE vectors, trained on the other books

Run it from the repo root, after python ml/verse_embeddings.py:
    python ml/topics.py
"""

import argparse
import csv
import hashlib
import os
import re
import urllib.request
from dataclasses import dataclass
from math import comb
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import Column, Float, Integer, MetaData, Table, Text, create_engine, text

import verse_embeddings as ve

HERE = Path(__file__).parent
TAGS = HERE / "data" / "topic_tags.csv"
KEY = HERE / "data" / "topic_key.csv"
RAW = HERE.parent / "data" / "raw" / "naves.csv"
NAVES_URL = (
    "https://raw.githubusercontent.com/BradyStephenson/bible-data/main/NavesTopicalDictionary.csv"
)
NAVES_MD5 = "48abbba24a48cec982a1960c8c202e8a"  # the copy the key was built from
MIN_VERSES = 20
TRANSLATION = "KJV"  # Nave's indexed the KJV; tags reach the ASV by reference
GROUPS = 3  # held-out book groups: every book is tested once, by a tagger that never saw it
K = 20  # a topic page's first screen of verses
C = 1.0  # the trained tagger's regularisation: scikit-learn's default, fixed, never tuned
METHODS = {
    "keyword": "Keywords (Postgres full-text)",
    "zero_shot": "Meaning, no training (BGE)",
    "trained": "Meaning, trained on Nave's (BGE + logistic regression)",
}
SCHEMA, TABLE = "ml", "verse_topics"
PER_TAG, PER_VERSE = 500, 3  # what's stored: each tag's best verses, each verse's best tags

# Nave's book codes, in Bible order (Song of Solomon and Jude are written "So" and "Jude")
CODES = {
    "GEN": "Genesis",
    "EXO": "Exodus",
    "LEV": "Leviticus",
    "NUM": "Numbers",
    "DEU": "Deuteronomy",
    "JOS": "Joshua",
    "JDG": "Judges",
    "RUT": "Ruth",
    "1SA": "1 Samuel",
    "2SA": "2 Samuel",
    "1KI": "1 Kings",
    "2KI": "2 Kings",
    "1CH": "1 Chronicles",
    "2CH": "2 Chronicles",
    "EZR": "Ezra",
    "NEH": "Nehemiah",
    "EST": "Esther",
    "JOB": "Job",
    "PSA": "Psalms",
    "PRO": "Proverbs",
    "ECC": "Ecclesiastes",
    "So": "Song of Solomon",
    "ISA": "Isaiah",
    "JER": "Jeremiah",
    "LAM": "Lamentations",
    "EZK": "Ezekiel",
    "DAN": "Daniel",
    "HOS": "Hosea",
    "JOL": "Joel",
    "AMO": "Amos",
    "OBA": "Obadiah",
    "JON": "Jonah",
    "MIC": "Micah",
    "NAM": "Nahum",
    "HAB": "Habakkuk",
    "ZEP": "Zephaniah",
    "HAG": "Haggai",
    "ZEC": "Zechariah",
    "MAL": "Malachi",
    "MAT": "Matthew",
    "MRK": "Mark",
    "LUK": "Luke",
    "JHN": "John",
    "ACT": "Acts",
    "ROM": "Romans",
    "1CO": "1 Corinthians",
    "2CO": "2 Corinthians",
    "GAL": "Galatians",
    "EPH": "Ephesians",
    "PHP": "Philippians",
    "COL": "Colossians",
    "1TH": "1 Thessalonians",
    "2TH": "2 Thessalonians",
    "1TI": "1 Timothy",
    "2TI": "2 Timothy",
    "TIT": "Titus",
    "PHM": "Philemon",
    "HEB": "Hebrews",
    "JAS": "James",
    "1PE": "1 Peter",
    "2PE": "2 Peter",
    "1JN": "1 John",
    "1JHN": "1 John",
    "2JN": "2 John",
    "3JN": "3 John",
    "Jude": "Jude",
    "REV": "Revelation",
}


# ---- The answer key ----------------------------------------------------------------------


def load_tags(path: Path = TAGS) -> pd.DataFrame:
    tags = pd.read_csv(path)
    tags["headings"] = tags.naves.str.split(r"\s*\|\s*")
    return tags


def chapter_sizes(engine, translation: str = "KJV") -> dict[tuple[str, int], int]:
    """How many verses each chapter has, for references to a whole chapter."""
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                select b.name, v.chapter, max(v.verse) as verses
                from verses as v
                join books as b on b.id = v.book_id
                join translations as t on t.id = v.translation_id
                where t.code = :translation
                group by b.name, v.chapter
                """
            ),
            {"translation": translation},
        )
        return {(r.name, r.chapter): r.verses for r in rows}


TOKEN = re.compile(r"^(?:with\s+)?(?:([1-3]?[A-Za-z]{2,4})\s+)?(\d+)(?::(.+))?$")


def references(refs: str, sizes: dict) -> tuple[set[tuple[str, int, int]], int]:
    """Nave's references as verses, and how many pieces couldn't be read. The book carries
    over to the next piece ("1CH 6:2,3; 23:13" is 1 Chronicles 6:2, 6:3 and 23:13), a bare
    number is a whole chapter ("NUM 17"), and a range can cross chapters ("1:26-2:3")."""
    found, unread, book = set(), 0, None
    for piece in (p.strip() for p in refs.split(";")):
        match = TOKEN.match(piece)
        if not match or (match.group(1) and match.group(1) not in CODES):
            unread += bool(piece)
            continue
        if match.group(1):
            book = CODES[match.group(1)]
        if book is None:
            unread += 1
            continue
        chapter, verses = int(match.group(2)), match.group(3)
        if verses is None:  # the whole chapter
            found |= {(book, chapter, v) for v in range(1, sizes.get((book, chapter), 0) + 1)}
            continue
        for item in verses.split(","):
            item = item.strip()
            new_chapter = re.fullmatch(r"(\d+):(.+)", item)  # "6:2,23:13": a new chapter
            if new_chapter:
                chapter, item = int(new_chapter.group(1)), new_chapter.group(2)
            span = re.fullmatch(r"(\d+)(?:-(?:(\d+):)?(\d+))?", item)
            if not span:
                unread += 1
                continue
            first, end_chapter, last = span.groups()
            first = int(first)
            if end_chapter:  # crosses into a later chapter
                for c in range(chapter, int(end_chapter) + 1):
                    start = first if c == chapter else 1
                    stop = int(last) if c == int(end_chapter) else sizes.get((book, c), 0)
                    found |= {(book, c, v) for v in range(start, stop + 1)}
                chapter = int(end_chapter)
            else:
                found |= {(book, chapter, v) for v in range(first, int(last or first) + 1)}
    return found, unread


def heading_refs(entry: str, heading: str) -> str:
    """The references on the line that starts with this heading, and only that line."""
    for line in entry.split("\n"):
        line = line.strip()
        if line.startswith("-" + heading):
            rest = line[len(heading) + 1 :]
            if not rest or rest[0] == " ":
                return rest.strip()
    raise KeyError(f"No heading {heading!r}")


def build_key(naves: Path, tags: pd.DataFrame, sizes: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The answer key (one row per tag and verse) and a report of what each tag drew on."""
    with open(naves, encoding="utf-8-sig", newline="") as f:
        entries = {r["subject"]: r["entry"] for r in csv.DictReader(f)}
    rows, report = [], []
    for tag in tags.itertuples():
        verses, unread = set(), 0
        for pair in tag.headings:
            subject, heading = (s.strip() for s in pair.split(">", 1))
            found, missed = references(heading_refs(entries[subject], heading), sizes)
            verses |= {v for v in found if v[2] <= sizes.get(v[:2], 0)}  # real verses only
            unread += missed
        report.append({"tag": tag.tag, "verses": len(verses), "unread_pieces": unread})
        rows += [{"tag": tag.tag, "book": b, "chapter": c, "verse": v} for b, c, v in verses]
    key = pd.DataFrame(rows)
    report = pd.DataFrame(report)
    kept = report[report.verses >= MIN_VERSES].tag
    order = {b: n for n, b in enumerate(dict.fromkeys(CODES.values()))}
    key = key[key.tag.isin(kept)].assign(order=lambda k: k.book.map(order))
    key = key.sort_values(["tag", "order", "chapter", "verse"]).drop(columns="order")
    return key.reset_index(drop=True), report


def fetch_naves(path: Path = RAW) -> Path:
    """Nave's, downloaded once (1.4 MB) into data/raw/, and checked against the copy the key
    was built from."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(NAVES_URL, path)
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    if digest != NAVES_MD5:
        raise ValueError(f"{path} has md5 {digest}, not {NAVES_MD5}: Nave's copy has changed")
    return path


# ---- The taggers ------------------------------------------------------------------------


def group_of(book: str) -> int:
    """A book's held-out group, from a hash of its name: the same on every machine."""
    return int(hashlib.md5(book.encode()).hexdigest(), 16) % GROUPS


def labels(verses: pd.DataFrame, key: pd.DataFrame, tags: list[str]) -> np.ndarray:
    """One row per verse, one column per tag: True where Nave's puts the verse under the tag."""
    y = np.zeros((len(verses), len(tags)), dtype=bool)
    where = {k: n for n, k in enumerate(zip(verses.book, verses.chapter, verses.verse))}
    column = {t: n for n, t in enumerate(tags)}
    for row in key.itertuples():
        n = where.get((row.book, row.chapter, row.verse))
        if n is not None:
            y[n, column[row.tag]] = True
    return y


def keyword_scores(engine, verses: pd.DataFrame, tags: pd.DataFrame) -> np.ndarray:
    """Postgres's full-text rank of each verse for each tag's everyday words (any of them,
    as stems); 0 where none appears."""
    scores = np.zeros((len(verses), len(tags)))
    where = {int(v): n for n, v in enumerate(verses.verse_id)}
    with engine.connect() as connection:
        for j, words in enumerate(tags.keywords):
            rows = connection.execute(
                text(
                    """
                    with q as (
                        select to_tsquery('english',
                            replace(plainto_tsquery('english', :words)::text, '&', '|')) as query
                    )
                    select v.id, ts_rank_cd(to_tsvector('english', v.text), q.query) as rank
                    from verses as v join translations as t on t.id = v.translation_id, q
                    where t.code = :translation and to_tsvector('english', v.text) @@ q.query
                    """
                ),
                {"words": words, "translation": TRANSLATION},
            )
            for row in rows:
                if row.id in where:
                    scores[where[row.id], j] = row.rank
    return scores


def zero_shot_scores(vectors: np.ndarray, tags: pd.DataFrame, ask) -> np.ndarray:
    """How closely each verse points the same way as each tag's description, asked as a BGE
    question (the 8.2 search, with the tag as the question)."""
    questions = np.vstack([ask(d) for d in tags.description])
    questions /= np.linalg.norm(questions, axis=1, keepdims=True)
    return vectors @ questions.T


def trained_tagger(vectors: np.ndarray, y: np.ndarray) -> list:
    """One logistic regression per tag on the BGE vectors. Tagged verses are rare, so each
    tag's few are weighted up (class_weight="balanced"). A tag with no examples to learn from
    gets no model, and scores 0."""
    from sklearn.linear_model import LogisticRegression

    return [
        LogisticRegression(C=C, class_weight="balanced", max_iter=2000).fit(vectors, y[:, j])
        if y[:, j].any() and not y[:, j].all()
        else None
        for j in range(y.shape[1])
    ]


def tag_chances(models: list, vectors: np.ndarray) -> np.ndarray:
    return np.column_stack(
        [np.zeros(len(vectors)) if m is None else m.predict_proba(vectors)[:, 1] for m in models]
    )


def trained_scores(vectors: np.ndarray, y: np.ndarray, groups: np.ndarray) -> np.ndarray:
    """Each verse scored by taggers trained on the other two groups of books only."""
    scores = np.zeros(y.shape)
    for g in range(GROUPS):
        test = groups == g
        if not test.any():
            continue
        scores[test] = tag_chances(trained_tagger(vectors[~test], y[~test]), vectors[test])
    return scores


# ---- Grading -----------------------------------------------------------------------------


def precision_at(scores: np.ndarray, truth: np.ndarray, k: int = K) -> float:
    top = np.argsort(-scores, kind="stable")[:k]
    return float(truth[top].mean())


def top_hits(scores: np.ndarray, y: np.ndarray, k: int) -> float:
    """For verses Nave's tags: is one of their tags among the k best? Only tags scoring above
    0 count (a verse with none of a tag's keywords hasn't been tagged with it)."""
    tagged = y.any(axis=1)
    s, truth = scores[tagged], y[tagged]
    top = np.argsort(-s, axis=1, kind="stable")[:, :k]
    rows = np.arange(len(s))[:, None]
    return float((truth[rows, top] & (s[rows, top] > 0)).any(axis=1).mean())


def grade(scores: np.ndarray, y: np.ndarray, tags: list[str]) -> pd.DataFrame:
    from sklearn.metrics import average_precision_score

    per_tag = pd.DataFrame(
        {
            "tag": tags,
            "verses": y.sum(axis=0),
            "precision_at_20": [precision_at(scores[:, j], y[:, j]) for j in range(len(tags))],
            "average_precision": [
                average_precision_score(y[:, j], scores[:, j]) for j in range(len(tags))
            ],
        }
    )
    per_tag.attrs["top1"] = top_hits(scores, y, 1)
    per_tag.attrs["top3"] = top_hits(scores, y, 3)
    return per_tag


def chance(y: np.ndarray) -> dict[str, float]:
    """What picking verses, or tags, at random would score."""
    tagged = y[y.any(axis=1)]
    m, n = tagged.sum(axis=1), y.shape[1]
    return {
        "precision_at_20": float(y.mean(axis=0).mean()),
        "average_precision": float(y.mean(axis=0).mean()),
        "top1": float((m / n).mean()),
        "top3": float(np.mean([1 - comb(n - k, min(3, n)) / comb(n, min(3, n)) for k in m])),
    }


@dataclass
class Result:
    verses: pd.DataFrame  # the translation's verses, in vector order
    vectors: np.ndarray
    y: np.ndarray
    tags: pd.DataFrame
    scores: dict[str, np.ndarray]  # method -> held-out scores, one column per tag
    per_tag: pd.DataFrame  # one row per method and tag
    board: pd.DataFrame  # one row per method, and chance

    @property
    def winner(self) -> str:
        """The tagger the app uses: the best average precision, the measure fixed beforehand."""
        return self.board.drop(index="chance").average_precision.idxmax()


def run(
    engine,
    ask,
    key: pd.DataFrame | None = None,
    tags: pd.DataFrame | None = None,
    schema: str = ve.SCHEMA,
) -> Result:
    tags = load_tags() if tags is None else tags
    key = pd.read_csv(KEY) if key is None else key
    tags = tags[tags.tag.isin(key.tag)].reset_index(drop=True)
    verses = ve.load_verses(engine)
    verses = verses[verses.translation == TRANSLATION].reset_index(drop=True)
    stored = ve.load_vectors(engine, schema).set_index("verse_id").embedding
    vectors = np.vstack(stored[verses.verse_id].to_numpy())
    names = tags.tag.tolist()
    y = labels(verses, key, names)
    groups = verses.book.map(group_of).to_numpy()
    scores = {
        "keyword": keyword_scores(engine, verses, tags),
        "zero_shot": zero_shot_scores(vectors, tags, ask),
        "trained": trained_scores(vectors, y, groups),
    }
    per_tag, board = [], {}
    for method, s in scores.items():
        graded = grade(s, y, names)
        per_tag.append(graded.assign(method=method))
        board[method] = {
            "precision_at_20": graded.precision_at_20.mean(),
            "average_precision": graded.average_precision.mean(),
            "top1": graded.attrs["top1"],
            "top3": graded.attrs["top3"],
        }
    board["chance"] = chance(y)
    board = pd.DataFrame(board).T
    return Result(verses, vectors, y, tags, scores, pd.concat(per_tag, ignore_index=True), board)


def by_tag(result: Result) -> pd.DataFrame:
    """Each tag's grades, in whole percents. Average precision is a continuous measure over
    31,000 verses, and another computer's floating point moves its 4th decimal (Kai's did, on
    4 of 90 rows), so the record keeps only what survives that."""
    record = result.per_tag.copy()
    for column in ("precision_at_20", "average_precision"):
        record[column] = (record[column] * 100).round().astype(int)
    return record


def summary(result: Result) -> pd.DataFrame:
    """The record, in whole percents: one swapped verse moves precision@20 by 5 points on one
    tag, under 0.2 averaged over 30."""
    board = (result.board * 100).round().astype(int).reset_index(names="method")
    board["tags"] = len(result.tags)
    board["tagged_verses"] = int(result.y.any(axis=1).sum())
    board["winner"] = board.method == result.winner
    return board


# ---- Storing the tags --------------------------------------------------------------------


def topics_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    return Table(
        TABLE,
        metadata,
        Column("verse_id", Integer, primary_key=True),
        Column("tag", Text, primary_key=True),
        Column("translation", Text, nullable=False),
        Column("score", Float, nullable=False),
        schema=schema,
    )


def final_scores(result: Result) -> np.ndarray:
    """The winner's scores for every verse: the trained tagger is refit on every book first."""
    if result.winner == "trained":
        return tag_chances(trained_tagger(result.vectors, result.y), result.vectors)
    return result.scores[result.winner]


def keep(scores: np.ndarray) -> np.ndarray:
    """Which (verse, tag) scores to store: each tag's best verses, and each verse's best tags."""
    kept = np.zeros(scores.shape, dtype=bool)
    best_verses = np.argsort(-scores, axis=0, kind="stable")[:PER_TAG]
    kept[best_verses, np.arange(scores.shape[1])] = True
    best_tags = np.argsort(-scores, axis=1, kind="stable")[:, :PER_VERSE]
    kept[np.arange(scores.shape[0])[:, None], best_tags] = True
    return kept


def save(engine, result: Result, scores: np.ndarray, schema: str = SCHEMA) -> int:
    """Both translations' tags, replaced in one transaction. The ASV gets the KJV verse's tags
    by reference (book, chapter, verse)."""
    every = ve.load_verses(engine)
    ref = list(zip(result.verses.book, result.verses.chapter, result.verses.verse))
    kept = keep(scores)
    rows = []
    for translation, mine in every.groupby("translation"):
        ids = dict(zip(zip(mine.book, mine.chapter, mine.verse), mine.verse_id))
        for n, j in zip(*np.nonzero(kept)):
            verse_id = ids.get(ref[n])
            if verse_id is not None:
                rows.append(
                    {
                        "verse_id": int(verse_id),
                        "tag": result.tags.tag[j],
                        "translation": translation,
                        "score": float(scores[n, j]),
                    }
                )
    table = topics_table(MetaData(), schema)
    with engine.begin() as connection:
        connection.execute(text(f"create schema if not exists {schema}"))
        table.create(connection, checkfirst=True)
        connection.execute(table.delete())
        connection.execute(table.insert(), rows)
    return len(rows)


def topic_verses(
    engine, tag: str, translation: str = "KJV", k: int = 10, schema: str = SCHEMA
) -> pd.DataFrame:
    """A tag's best verses, with their references and text: a topic page."""
    with engine.connect() as connection:
        rows = pd.read_sql(
            text(
                f"""
                select v.id as verse_id, b.name as book, v.chapter, v.verse, v.text, s.score
                from {schema}.{TABLE} as s
                join verses as v on v.id = s.verse_id
                join books as b on b.id = v.book_id
                where s.tag = :tag and s.translation = :translation
                order by s.score desc, v.id
                limit :k
                """
            ),
            connection,
            params={"tag": tag, "translation": translation, "k": k},
        )
    rows.insert(1, "reference", [f"{r.book} {r.chapter}:{r.verse}" for r in rows.itertuples()])
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--build-key", action="store_true", help="rebuild topic_key.csv")
    args = parser.parse_args()
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    if args.build_key:
        key, report = build_key(fetch_naves(), load_tags(), chapter_sizes(engine))
        print(report.to_string(index=False))
        key.to_csv(KEY, index=False, lineterminator="\n")
        print(f"\n{len(key):,} tag-verse pairs, {key.tag.nunique()} tags: {KEY.name}")
    else:
        from search import asking

        result = run(engine, asking(ve.encoder(ve.MODEL), ve.MODEL))
        print(f"{len(result.tags)} tags, graded on books each tagger never saw ({TRANSLATION})\n")
        print((result.board * 100).round(1).to_string())
        print(f"\nThe app uses: {METHODS[result.winner]}")
        stored = save(engine, result, final_scores(result))
        print(f"Stored {stored:,} verse tags in {SCHEMA}.{TABLE}")
        results = HERE / "results"
        summary(result).to_csv(results / "topics.csv", index=False, lineterminator="\n")
        by_tag(result).to_csv(results / "topics_by_tag.csv", index=False, lineterminator="\n")
        print("The record: ml/results/topics.csv, and each tag's in topics_by_tag.csv")
