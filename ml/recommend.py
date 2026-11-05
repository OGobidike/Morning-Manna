"""Because you read (Card 8.4): after a passage, the verses a reader might want next.

A reader who finishes Psalm 23 might want John 10, "I am the good shepherd". The shelf is 10
verses from 10 different chapters, never from the chapter just read.

The answer key is OpenBible.info's cross-references (CC BY, 2024-11-04): 344,799 links between
verses, each voted on by readers for how helpful it is. The rules were fixed before any
recommender ran:
    - a link counts when it has at least 10 votes: the best tenth, 36,425 links
    - links keep their direction: reading the "from" verse, the "to" verses are the answer
    - a "to" range counts as found when any of its verses is on the shelf
    - the reader just read the chapter, so its own verses are never the answer, nor shelved
python ml/recommend.py downloads the file once (8.3 MB, into data/raw/) and checks its md5.

Five recommenders race, graded on whole books they never saw (8.3's 3 groups):
    popular   the most linked-to verses, counted from the other books' links
    words     the verses sharing the rarest words (TF-IDF on the KJV text)
    meaning   the nearest verses by meaning (8.1's BGE vectors)
    topics    the verses with the most similar topic tags (8.3's tagger)
    blend     words, meaning and topics together, weighted by what worked on the other books
              (each signal standardised per query; weights in tenths)

A passage pools its verses' shelves, adding up their scores. That was checked too, on every run
of 6 verses, against fusing ranks and against the whole passage as one query (grade_passages).

"Readers like you" (readers_like_you) is built and tested, but switched off: everyone reads the
same plan, so readers' choices say nothing yet. It switches on when at least 200 readers have
each chosen at least 5 chapters themselves (collab_status).

Run it from the repo root, after python ml/verse_embeddings.py:
    python ml/recommend.py
"""

import argparse
import hashlib
import os
import urllib.request
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import Column, Float, Integer, MetaData, Table, create_engine, text

import topics
import verse_embeddings as ve

HERE = Path(__file__).parent
RAW = HERE.parent / "data" / "raw" / "cross_references.txt"
XREF_URL = (
    "https://raw.githubusercontent.com/scrollmapper/bible_databases/master/"
    "sources/extras/cross_references.txt"
)
XREF_MD5 = "70a9195d7c9ad72ed8ac2e9291881e49"  # the copy the rules were fixed on
VOTES = 10  # a link counts from 10 votes: the best tenth
SHELF = 10  # the shelf a reader sees, and the one that's graded
STORED = 20  # each verse's shelf as stored: the API serves up to 20
TRANSLATION = "KJV"  # the cross-references follow the KJV's verse numbers
SEED = 7
CHANCE_ROUNDS = 10  # random shelves per verse, for chance
STEP = 10  # the blend's weights, in tenths
SCHEMA, TABLE = "ml", "verse_shelves"
METHODS = {  # in order of simplicity: a tie goes to the simpler
    "popular": "The most linked-to verses",
    "words": "Shared rare words",
    "meaning": "Nearest by meaning",
    "topics": "Similar topic tags",
    "blend": "Words, meaning and topics together",
}
SIGNALS = ["words", "meaning", "topics"]  # what the blend weighs
PASSAGE, SHORTEST = 6, 3  # graded passages: runs of 6 verses; a last run needs at least 3
POOLERS = {  # how a passage pools its verses' shelves; full is a ceiling, not servable
    "sum": "The stored scores added up",
    "rrf": "Each verse's ranks fused (1/(60 + rank))",
    "full": "The whole passage as one query",
}
SERVABLE = ["sum", "rrf"]  # a tie goes to sum
RRF_K = 60  # as 8.2 fused its lists
MIN_READERS = 200  # readers like you: readers needed, each having chosen...
MIN_CHOSEN = 5  # ...at least this many chapters themselves
MIN_TOGETHER = 3  # two chapters are paired only when this many readers chose both

# OpenBible's book codes, in Bible order (canonical_order 1 to 66)
OSIS = (
    "Gen Exod Lev Num Deut Josh Judg Ruth 1Sam 2Sam 1Kgs 2Kgs 1Chr 2Chr Ezra Neh Esth Job Ps "
    "Prov Eccl Song Isa Jer Lam Ezek Dan Hos Joel Amos Obad Jonah Mic Nah Hab Zeph Hag Zech Mal "
    "Matt Mark Luke John Acts Rom 1Cor 2Cor Gal Eph Phil Col 1Thess 2Thess 1Tim 2Tim Titus Phlm "
    "Heb Jas 1Pet 2Pet 1John 2John 3John Jude Rev"
).split()
ORDER = {code: n for n, code in enumerate(OSIS, start=1)}


# ---- The answer key ---------------------------------------------------------------------


def fetch_xrefs(path: Path = RAW) -> Path:
    """The cross-references, downloaded once (8.3 MB) into data/raw/, and checked against the
    copy the rules were fixed on."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(XREF_URL, path)
    digest = hashlib.md5(path.read_bytes()).hexdigest()
    if digest != XREF_MD5:
        raise ValueError(f"{path} has md5 {digest}, not {XREF_MD5}: the file has changed")
    return path


def osis(ref: str) -> tuple[int, int, int]:
    """'1Cor.13.4' -> (46, 13, 4): the book's place in the Bible, the chapter and the verse."""
    code, chapter, verse = ref.split(".")
    return ORDER[code], int(chapter), int(verse)


def load_links(path: Path, votes: int = VOTES) -> pd.DataFrame:
    """The links with enough votes, one row each: where from, and the first and last verse of
    where to (the same verse when it isn't a range)."""
    raw = pd.read_csv(path, sep="\t", skiprows=1, names=["source", "target", "votes"])
    raw = raw[raw.votes >= votes].reset_index(drop=True)
    first, _, last = raw.target.str.partition("-").iloc[:, [0, 1, 2]].T.to_numpy()
    last = np.where(last == "", first, last)
    rows = [
        (*osis(s), *osis(a), *osis(b), v)
        for s, a, b, v in zip(raw.source, first, last, raw.votes, strict=True)
    ]
    columns = ["book", "chapter", "verse", "to_book", "to_chapter", "to_verse"]
    columns += ["end_book", "end_chapter", "end_verse", "votes"]
    return pd.DataFrame(rows, columns=columns)


@dataclass
class Bible:
    """The verses in Bible order, numbered 0 to n-1, and their chapters (contiguous runs)."""

    verses: pd.DataFrame  # book_order, book, chapter, verse, text: one translation

    def __post_init__(self):
        v = self.verses
        self.where = {k: n for n, k in enumerate(zip(v.book_order, v.chapter, v.verse))}
        new = np.r_[True, (v.book_order.diff().ne(0) | v.chapter.diff().ne(0)).to_numpy()[1:]]
        self.chapter_of = np.cumsum(new) - 1  # each verse's chapter, numbered 0 up
        self.starts = np.flatnonzero(new)  # each chapter's first verse
        sizes = np.diff(np.r_[self.starts, len(v)])
        # Each chapter's verses in a row, so the best verse of any chapter is one argmax away.
        # Short chapters are padded with their own first verse, which changes no argmax
        self.padded = np.repeat(self.starts[:, None], sizes.max(), axis=1)
        for c, (start, size) in enumerate(zip(self.starts, sizes, strict=True)):
            self.padded[c, :size] = np.arange(start, start + size)

    def __len__(self) -> int:
        return len(self.verses)


@dataclass
class Key:
    """For each query verse, its links: each a set of verse numbers, own chapter removed."""

    queries: np.ndarray  # the verses that have links, by number
    links: list[list[np.ndarray]]  # per query, per link, the verses that count as finding it
    unread: int  # links whose verses aren't in this Bible

    def __post_init__(self):
        self.answers = [answer(links) for links in self.links]


def answer(links: list[np.ndarray]) -> tuple[dict[int, set[int]], int]:
    """A query's links as a lookup, for fast grading: each verse to the links it finds, and
    how many links there are."""
    finds: dict[int, set[int]] = {}
    for n, link in enumerate(links):
        for v in link.tolist():
            finds.setdefault(v, set()).add(n)
    return finds, len(links)


def build_key(links: pd.DataFrame, bible: Bible) -> Key:
    found: dict[int, list[np.ndarray]] = {}
    unread = 0
    for row in links.itertuples(index=False):
        q = bible.where.get((row.book, row.chapter, row.verse))
        a = bible.where.get((row.to_book, row.to_chapter, row.to_verse))
        b = bible.where.get((row.end_book, row.end_chapter, row.end_verse))
        if q is None or a is None or b is None or b < a:
            unread += 1
            continue
        target = np.arange(a, b + 1)
        target = target[bible.chapter_of[target] != bible.chapter_of[q]]  # just read
        if len(target):
            found.setdefault(q, []).append(target)
    queries = np.array(sorted(found), dtype=int)
    return Key(queries, [found[q] for q in queries], unread)


# ---- The shelves ------------------------------------------------------------------------


def shelves(scores: np.ndarray, rows: np.ndarray, bible: Bible, k: int | None = None):
    """Each row's shelf: the best verse of each of its k best chapters (SHELF unless given),
    never the row's own chapter. scores is one row per query (rows: the query verses), one
    column per verse."""
    k = min(SHELF if k is None else k, len(bible.starts) - 1)  # a small Bible has few chapters
    best = np.maximum.reduceat(scores, bible.starts, axis=1)  # each chapter's best verse
    best[np.arange(len(rows)), bible.chapter_of[rows]] = -np.inf
    top = np.argpartition(-best, k - 1, axis=1)[:, :k]
    order = np.argsort(-np.take_along_axis(best, top, axis=1), axis=1, kind="stable")
    top = np.take_along_axis(top, order, axis=1)  # the k chapters, best first
    candidates = bible.padded[top]  # (rows, k, longest chapter)
    picks = np.take_along_axis(scores[:, None, :], candidates, axis=2).argmax(axis=2)
    return np.take_along_axis(candidates, picks[..., None], axis=2)[..., 0]


def grade(shelf: np.ndarray, answer: tuple[dict[int, set[int]], int]) -> tuple[float, ...]:
    """One query's recall (share of its links found), hit (any found) and precision (share of
    the shelf inside a link). answer comes from answer(links)."""
    finds, n = answer
    found, inside = set(), 0
    for v in shelf.tolist():
        if v in finds:
            inside += 1
            found |= finds[v]
    return len(found) / n, float(bool(found)), inside / len(shelf)


def standardise(scores: np.ndarray) -> np.ndarray:
    """Each row on one scale (mean 0, spread 1), so signals can be added fairly."""
    spread = scores.std(axis=1, keepdims=True)
    return (scores - scores.mean(axis=1, keepdims=True)) / np.where(spread > 0, spread, 1)


def weight_grid(step: int = STEP) -> list[tuple[float, float, float]]:
    """Every way to split 1 between the three signals, in tenths, in a fixed order."""
    return [
        (a / step, b / step, (step - a - b) / step)
        for a, b in product(range(step + 1), repeat=2)
        if a + b <= step
    ]


@dataclass
class Signals:
    """What each recommender scores with: unit-length rows, so a dot product is a cosine."""

    words: object  # a sparse TF-IDF matrix
    meaning: np.ndarray
    topics: np.ndarray

    def scores(self, rows: np.ndarray) -> dict[str, np.ndarray]:
        return {
            "words": (self.words[rows] @ self.words.T).toarray().astype(np.float32),
            "meaning": self.meaning[rows] @ self.meaning.T,
            "topics": self.topics[rows] @ self.topics.T,
        }


def unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return (matrix / np.where(norms > 0, norms, 1)).astype(np.float32)


def word_vectors(texts: list[str]):
    """TF-IDF on the verse text, with settings fixed beforehand (never tuned): a word counts
    less the more verses use it, and words in only one verse are dropped."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    return TfidfVectorizer(sublinear_tf=True, stop_words="english", min_df=2).fit_transform(texts)


def popularity(key: Key, use: np.ndarray, n: int) -> np.ndarray:
    """How often each verse is linked to, counting only the queries in use."""
    counts = np.zeros(n, dtype=np.float32)
    for i in np.flatnonzero(use):
        for link in key.links[i]:
            counts[link] += 1
    return counts


def chunks(items: np.ndarray, size: int = 512):
    for start in range(0, len(items), size):
        yield items[start : start + size]


def blended(scores: dict[str, np.ndarray], weights) -> np.ndarray:
    """The weighted sum of the standardised signals, added into one buffer (each signal is 64 MB
    a batch, so fresh arrays for every step would cost more than the sums)."""
    out = np.zeros_like(scores[SIGNALS[0]])
    for w, s in zip(weights, SIGNALS, strict=True):
        if w:
            out += np.float32(w) * scores[s]
    return out


def grid_table(signals: Signals, key: Key, bible: Bible) -> np.ndarray:
    """Every weighting of the grid, graded on every query: (query, weighting, measure). A
    query's shelf under a weighting doesn't depend on which books are held out, so it's made
    once, and each held-out group picks its weights from the other books' rows."""
    grid = weight_grid()
    table = np.zeros((len(key.queries), len(grid), 3))
    for part in chunks(np.arange(len(key.queries))):
        rows = key.queries[part]
        scores = {s: standardise(v) for s, v in signals.scores(rows).items()}
        for g, weights in enumerate(grid):
            shelf = shelves(blended(scores, weights), rows, bible)
            for j, i in enumerate(part):
                table[i, g] = grade(shelf[j], key.answers[i])
    return table


def pick(recall: np.ndarray) -> int:
    """The weighting with the best mean recall over the queries given (rows: queries, columns:
    weightings); an exact tie goes to the first in the grid's fixed order. Unrounded: rounding
    to whole percents first made a near-tie's pick hang on which side of a half-percent a
    weighting fell, so a tiny wobble could change it (rule 14 in the write-up)."""
    return int(np.argmax(recall.mean(axis=0)))


def chance(key: Key, bible: Bible, rounds: int = CHANCE_ROUNDS) -> np.ndarray:
    """Random shelves by the same rules (10 chapters, one verse each, never the own chapter):
    each query's measures, averaged over the rounds."""
    rng = np.random.default_rng(SEED)
    sizes = np.diff(np.r_[bible.starts, len(bible)])
    out = np.zeros((len(key.queries), 3))
    for _ in range(rounds):
        for part in chunks(np.arange(len(key.queries))):
            rows = key.queries[part]
            luck = rng.random((len(rows), len(bible.starts)))
            luck[np.arange(len(rows)), bible.chapter_of[rows]] = -1
            chosen = np.argsort(-luck, axis=1)[:, :SHELF]
            shelf = bible.starts[chosen] + (rng.random(chosen.shape) * sizes[chosen]).astype(int)
            for j, i in enumerate(part):
                out[i] += grade(shelf[j], key.answers[i])
    return out / rounds


# ---- The race ---------------------------------------------------------------------------


@dataclass
class Result:
    bible: Bible
    signals: Signals
    key: Key
    table: np.ndarray  # every weighting, graded on every query (grid_table)
    graded: pd.DataFrame  # one row per query and method: recall, hit, precision
    board: pd.DataFrame  # one row per method (and chance): the averages
    weights: pd.DataFrame  # the blend's weights, per held-out group
    winner: str


def scored(method: str, scores: dict, rows, popular, weights) -> np.ndarray:
    """One method's scores for a batch, from the batch's three signals (computed once)."""
    if method == "popular":
        return np.broadcast_to(popular, (len(rows), len(popular))).copy()
    if method == "blend":
        return blended({s: standardise(v) for s, v in scores.items()}, weights)
    return scores[method]


def race(signals: Signals, key: Key, bible: Bible) -> Result:
    """Each held-out group graded by recommenders that learned only from the other groups. A
    single signal is a corner of the blend's grid (all its weight on one), so words, meaning
    and topics are read off the same table."""
    grid = weight_grid()
    corner = {s: grid.index(tuple(float(s == t) for t in SIGNALS)) for s in SIGNALS}
    table = grid_table(signals, key, bible)
    groups = bible.verses.book.map(topics.group_of).to_numpy()[key.queries]
    graded, weights = [], []
    for g in range(topics.GROUPS):
        test, train = groups == g, groups != g
        if not test.any():
            continue
        chosen = pick(table[train, :, 0]) if train.any() else corner["meaning"]
        weights.append({"held_out_group": g, **dict(zip(SIGNALS, grid[chosen], strict=True))})
        columns = {"popular": None, **corner, "blend": chosen}
        popular = popularity(key, train, len(bible))
        for part in chunks(np.flatnonzero(test)):
            rows = key.queries[part]
            shelf = shelves(scored("popular", {}, rows, popular, None), rows, bible)
            for method, column in columns.items():
                for j, i in enumerate(part):
                    measures = (
                        grade(shelf[j], key.answers[i]) if column is None else table[i, column]
                    )
                    graded.append((method, i, *measures))
    graded = pd.DataFrame(graded, columns=["method", "query", "recall", "hit", "precision"])
    luck = pd.DataFrame(chance(key, bible), columns=["recall", "hit", "precision"])
    luck = luck.assign(method="chance", query=np.arange(len(key.queries)))
    graded = pd.concat([graded, luck], ignore_index=True)
    board = graded.groupby("method", sort=False)[["recall", "hit", "precision"]].mean()
    board = board.loc[[*METHODS, "chance"]]
    percents = np.round(100 * board.loc[list(METHODS), "recall"])
    winner = percents.index[int(np.argmax(percents.to_numpy()))]  # ties: the simpler
    return Result(bible, signals, key, table, graded, board, pd.DataFrame(weights), winner)


def load_bible(engine, schema: str = ve.SCHEMA) -> tuple[Bible, np.ndarray]:
    """The KJV in Bible order, and its stored 8.1 vectors in the same order."""
    verses = ve.load_verses(engine)
    verses = verses[verses.translation == TRANSLATION].reset_index(drop=True)
    stored = ve.load_vectors(engine, schema).set_index("verse_id").embedding
    return Bible(verses), np.vstack(stored[verses.verse_id].to_numpy())


def topic_chances(bible: Bible, vectors: np.ndarray) -> np.ndarray:
    """Each verse's 30 topic chances, from 8.3's tagger trained on every book of Nave's (what
    the app has). Nave's is a different answer key from the cross-references."""
    tags = topics.load_tags()
    y = topics.labels(bible.verses, pd.read_csv(topics.KEY), tags.tag.tolist())
    return topics.tag_chances(topics.trained_tagger(vectors, y), vectors)


def run(engine, links: pd.DataFrame, chances=None, schema: str = ve.SCHEMA) -> Result:
    """The race on the KJV. chances, if given, stands in for 8.3's topic chances: one row per
    verse, in Bible order."""
    bible, vectors = load_bible(engine, schema)
    chances = topic_chances(bible, vectors) if chances is None else chances
    signals = Signals(
        words=word_vectors(bible.verses.text.map(ve.without_heading).tolist()),
        meaning=unit(vectors),
        topics=unit(chances),
    )
    return race(signals, build_key(links, bible), bible)


def summary(result: Result) -> pd.DataFrame:
    """The record: whole percents and counts, which come out the same on any computer."""
    board = (100 * result.board).round().astype(int).add_suffix("_at_10").reset_index()
    return board.assign(
        queries=len(result.key.queries),
        links=sum(len(links) for links in result.key.links),
        winner=board.method.eq(result.winner),
    )


def by_section(result: Result) -> pd.DataFrame:
    """Recall by the part of the Bible the reader is in (8.1's sections), in whole percents, for
    the winner and for shared words. Only those two: words never touches the vectors, and the
    winner held under a noise test, while the others' section numbers moved by a point when the
    vectors were nudged by another computer's rounding (a small section's average moves with
    a single shelf)."""
    sections = result.bible.verses.section.to_numpy()[result.key.queries]
    graded = result.graded.assign(section=sections[result.graded["query"]])
    graded = graded[graded.method.isin(dict.fromkeys(["words", result.winner]))]
    table = graded.groupby(["section", "method"], sort=False).recall.mean().mul(100).round()
    out = table.astype(int).rename("recall_at_10").reset_index()
    sizes = pd.Series(sections).value_counts()
    return out.assign(queries=out.section.map(sizes).astype(int))


# ---- What the app gets ------------------------------------------------------------------


def verse_shelves(result: Result, weights: np.ndarray, k: int = STORED):
    """Every verse's shelf by the winner: its k best, one per chapter, and their scores.
    weights holds each verse's blend weights (its row of the grid), so a held-out group's
    verses can use the weights learned without them."""
    every = np.ones(len(result.key.queries), dtype=bool)
    popular = popularity(result.key, every, len(result.bible))
    grid = weight_grid()
    k = min(k, len(result.bible.starts) - 1)
    picks = np.zeros((len(result.bible), k), dtype=int)
    scores = np.zeros((len(result.bible), k), dtype=np.float32)
    for g in np.unique(weights):
        for rows in chunks(np.flatnonzero(weights == g)):
            signals = {} if result.winner == "popular" else result.signals.scores(rows)
            s = scored(result.winner, signals, rows, popular, grid[g])
            picks[rows] = shelves(s, rows, result.bible, k)
            scores[rows] = np.take_along_axis(s, picks[rows], axis=1)
    return picks, scores


def final_shelves(result: Result, k: int = STORED) -> tuple[np.ndarray, np.ndarray]:
    """What the app stores: every verse's shelf, with the weights refit on every book."""
    best = pick(result.table[:, :, 0])
    return verse_shelves(result, np.full(len(result.bible), best), k)


# ---- Passages ---------------------------------------------------------------------------


def passages(bible: Bible) -> list[np.ndarray]:
    """The graded passages: each chapter in runs of 6 verses (1-6, 7-12, ...), keeping a
    shorter last run only if it has at least 3."""
    out = []
    for start, end in zip(bible.starts, np.r_[bible.starts[1:], len(bible)], strict=True):
        for first in range(start, end, PASSAGE):
            run = np.arange(first, min(first + PASSAGE, end))
            if len(run) >= SHORTEST:
                out.append(run)
    return out


def passage_links(members: np.ndarray, key: Key) -> list[np.ndarray]:
    """A passage's links: its verses' links together, each distinct one once."""
    where = {q: i for i, q in enumerate(key.queries.tolist())}
    seen: dict[tuple, np.ndarray] = {}
    for v in members.tolist():
        for link in key.links[where[v]] if v in where else []:
            seen.setdefault(tuple(link.tolist()), link)
    return list(seen.values())


def pool(picks: np.ndarray, scores: np.ndarray, members, how: str, bible: Bible, k=None):
    """A passage's shelf from its verses' stored shelves: each candidate's pooled score (sum:
    the scores added; rrf: 1/(60 + rank) added), then its best verse per chapter."""
    pooled: dict[int, float] = {}
    for v in members:
        for rank, (m, score) in enumerate(zip(picks[v], scores[v], strict=True)):
            gain = float(score) if how == "sum" else 1 / (RRF_K + rank + 1)
            pooled[int(m)] = pooled.get(int(m), 0.0) + gain
    best: dict[int, tuple[float, int]] = {}
    for m, score in pooled.items():
        c = bible.chapter_of[m]
        if c not in best or (score, -m) > (best[c][0], -best[c][1]):
            best[c] = (score, m)
    ranked = sorted(best.values(), key=lambda sm: (-sm[0], sm[1]))
    return np.array([m for _, m in ranked[: SHELF if k is None else k]], dtype=int)


def grade_passages(result: Result) -> pd.DataFrame:
    """Every graded passage, by each pooler: recall, hit and precision, on the same held-out
    groups (each verse's shelf made with the weights learned without its group)."""
    bible, key, grid = result.bible, result.key, weight_grid()
    learned = {
        w.held_out_group: grid.index(tuple(w[SIGNALS])) for _, w in result.weights.iterrows()
    }
    groups = bible.verses.book.map(topics.group_of).to_numpy()
    weights = np.array([learned.get(g, 0) for g in groups])
    picks, scores = verse_shelves(result, weights)
    rows = []
    graded = [(p, passage_links(p, key)) for p in passages(bible)]
    graded = [(p, links) for p, links in graded if links]
    for g, column in learned.items():
        mine = [(p, links) for p, links in graded if groups[p[0]] == g]
        for batch in range(0, len(mine), 256):
            part = mine[batch : batch + 256]
            members = np.concatenate([p for p, _ in part])
            signals = result.signals.scores(members)
            z = blended({s: standardise(v) for s, v in signals.items()}, grid[column])
            sizes = np.array([len(p) for p, _ in part])
            means = np.add.reduceat(z, np.r_[0, np.cumsum(sizes)[:-1]], axis=0) / sizes[:, None]
            whole = shelves(means, np.array([p[0] for p, _ in part]), bible)
            for j, (p, links) in enumerate(part):
                found = answer(links)
                rows.append(("full", int(p[0]), *grade(whole[j], found)))
                for how in SERVABLE:
                    rows.append((how, int(p[0]), *grade(pool(picks, scores, p, how, bible), found)))
    return pd.DataFrame(rows, columns=["pooler", "first_verse", "recall", "hit", "precision"])


def passage_summary(graded: pd.DataFrame) -> pd.DataFrame:
    """The passage record, in whole percents: which pooler the app serves."""
    board = graded.groupby("pooler")[["recall", "hit", "precision"]].mean().loc[list(POOLERS)]
    board = (100 * board).round().astype(int).add_suffix("_at_10").reset_index()
    served = SERVABLE[int(np.argmax(board.set_index("pooler").recall_at_10[SERVABLE]))]
    return board.assign(passages=graded.first_verse.nunique(), served=board.pooler.eq(served))


def shelves_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    """A shelf by reference (book by its place in the Bible), so it serves either translation."""
    return Table(
        TABLE,
        metadata,
        Column("from_book", Integer, primary_key=True),
        Column("from_chapter", Integer, primary_key=True),
        Column("from_verse", Integer, primary_key=True),
        Column("rank", Integer, primary_key=True),
        Column("book", Integer, nullable=False),
        Column("chapter", Integer, nullable=False),
        Column("verse", Integer, nullable=False),
        Column("score", Float, nullable=False),
        schema=schema,
    )


def save(engine, bible: Bible, picks: np.ndarray, scores: np.ndarray, schema: str = SCHEMA):
    """Every verse's shelf, replaced in one transaction."""
    v = bible.verses
    book, chapter, verse = (v[c].to_numpy() for c in ("book_order", "chapter", "verse"))
    rows = [
        {
            "from_book": int(book[n]),
            "from_chapter": int(chapter[n]),
            "from_verse": int(verse[n]),
            "rank": r + 1,
            "book": int(book[m]),
            "chapter": int(chapter[m]),
            "verse": int(verse[m]),
            "score": float(scores[n, r]),
        }
        for n in range(len(picks))
        for r, m in enumerate(picks[n])
    ]
    table = shelves_table(MetaData(), schema)
    with engine.begin() as connection:
        connection.execute(text(f"create schema if not exists {schema}"))
        table.create(connection, checkfirst=True)
        connection.execute(table.delete())
        connection.execute(table.insert(), rows)
    return len(rows)


def shelf_for(
    engine,
    book: str,
    chapter: int,
    verse: int = 1,
    end_chapter: int | None = None,
    end_verse: int | None = None,
    translation: str = "KJV",
    k: int = SHELF,
    schema: str = SCHEMA,
) -> pd.DataFrame:
    """A passage's shelf: its verses' shelves pooled (a verse on several scores their sum),
    one verse per chapter, never from the passage's own chapters."""
    end_chapter = chapter if end_chapter is None else end_chapter
    end_verse = 999 if end_verse is None else end_verse  # to the end of the chapter
    with engine.connect() as connection:
        rows = pd.read_sql(
            text(
                f"""
                with passage as (
                    select canonical_order as book from books where name = :book
                ),
                pooled as (
                    select s.book, s.chapter, s.verse, sum(s.score) as score
                    from {schema}.{TABLE} as s
                    join passage as p on p.book = s.from_book
                    where (s.from_chapter, s.from_verse) >= (:chapter, :verse)
                      and (s.from_chapter, s.from_verse) <= (:end_chapter, :end_verse)
                      and not (s.book = p.book and s.chapter between :chapter and :end_chapter)
                    group by s.book, s.chapter, s.verse
                ),
                best as (
                    select distinct on (book, chapter) book, chapter, verse, score
                    from pooled
                    order by book, chapter, score desc, verse
                )
                select b.name as book, v.chapter, v.verse, v.text, best.score
                from best
                join books as b on b.canonical_order = best.book
                join verses as v
                  on v.book_id = b.id and v.chapter = best.chapter and v.verse = best.verse
                join translations as t on t.id = v.translation_id and t.code = :translation
                order by best.score desc, best.book, best.chapter
                limit :k
                """
            ),
            connection,
            params={
                "book": book,
                "chapter": chapter,
                "verse": verse,
                "end_chapter": end_chapter,
                "end_verse": end_verse,
                "translation": translation,
                "k": k,
            },
        )
    rows.insert(0, "reference", [f"{r.book} {r.chapter}:{r.verse}" for r in rows.itertuples()])
    return rows


# ---- Readers like you (built, switched off) ---------------------------------------------


def collab_status(chosen: pd.DataFrame) -> tuple[bool, int]:
    """Is there enough signal? chosen holds one row per reader and chapter they chose
    themselves (reader, book, chapter): readings of the plan's day don't count, because
    everyone on the plan reads the same days. On when MIN_READERS readers have each chosen
    MIN_CHOSEN chapters. Returns (on, how many readers qualify)."""
    per_reader = chosen.drop_duplicates().groupby("reader").size()
    ready = int((per_reader >= MIN_CHOSEN).sum())
    return ready >= MIN_READERS, ready


def readers_like_you(chosen: pd.DataFrame, min_together: int = MIN_TOGETHER) -> pd.DataFrame:
    """Readers who chose this chapter also chose: every pair of chapters chosen together by at
    least min_together readers, scored by cosine (together / sqrt(readers of each))."""
    chosen = chosen.drop_duplicates()
    chosen = chosen.assign(item=list(zip(chosen.book, chosen.chapter, strict=True)))
    pairs = chosen.merge(chosen, on="reader", suffixes=("", "_also"))
    pairs = pairs[pairs.item != pairs.item_also]
    together = pairs.groupby(["item", "item_also"]).size().rename("readers").reset_index()
    together = together[together.readers >= min_together]
    readers = chosen.groupby("item").size()
    score = together.readers / np.sqrt(
        together.item.map(readers).to_numpy() * together.item_also.map(readers).to_numpy()
    )
    out = pd.DataFrame(
        {
            "book": together.item.str[0],
            "chapter": together.item.str[1],
            "also_book": together.item_also.str[0],
            "also_chapter": together.item_also.str[1],
            "readers": together.readers,
            "score": score,
        }
    )
    return out.sort_values(["book", "chapter", "score"], ascending=[True, True, False])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.parse_args()
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    links = load_links(fetch_xrefs())
    result = run(engine, links)
    key = result.key
    print(
        f"{len(key.queries):,} verses with links ({sum(map(len, key.links)):,} links, "
        f"{key.unread} not in the {TRANSLATION}), graded on books each recommender never saw\n"
    )
    print((result.board * 100).round(1).to_string())
    print(f"\nThe blend's weights ({', '.join(SIGNALS)}), per held-out group:")
    print(result.weights.to_string(index=False))
    print(f"\nThe app uses: {METHODS[result.winner]}")
    passage_record = passage_summary(grade_passages(result))
    print(f"\nPassages of {PASSAGE} verses, each pooling its verses' shelves:")
    print(passage_record.to_string(index=False))
    stored = save(engine, result.bible, *final_shelves(result))
    print(f"Stored {stored:,} shelf verses in {SCHEMA}.{TABLE}")
    on, ready = collab_status(pd.DataFrame(columns=["reader", "book", "chapter"]))
    print(
        f"Readers like you: {'on' if on else 'off'} ({ready} of {MIN_READERS} readers have "
        f"chosen {MIN_CHOSEN} chapters themselves; the app doesn't record choices yet)"
    )
    results = HERE / "results"
    summary(result).to_csv(results / "shelves.csv", index=False, lineterminator="\n")
    by_section(result).to_csv(results / "shelves_by_section.csv", index=False, lineterminator="\n")
    result.weights.to_csv(results / "shelves_weights.csv", index=False, lineterminator="\n")
    passage_record.to_csv(results / "shelves_passages.csv", index=False, lineterminator="\n")
    print("The record: ml/results/shelves.csv, and shelves_by_section, _weights and _passages")
