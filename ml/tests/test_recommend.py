"""Because you read (Card 8.4): the key read right, shelves built by the rules, graded fairly.

No model and no download: the stand-in encoder from 8.1's tests plays BGE, and the answer key
is made up. The database tests use 8.2's pretend Bible (shepherds in the Psalms, fishermen in
Matthew) and are skipped without a Postgres locally, but fail in CI.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_search import bible, pretend_bible  # noqa: E402, F401 (bible is a fixture)

import recommend  # noqa: E402
import recommend_charts as charts  # noqa: E402
import serve  # noqa: E402

LINKS = ["book", "chapter", "verse", "to_book", "to_chapter", "to_verse"]
LINKS += ["end_book", "end_chapter", "end_verse", "votes"]


def tiny_bible() -> recommend.Bible:
    """Ruth 1 (3 verses), Ruth 2 (2), Ruth 3 (1), Esther 1 (2), Esther 2 (2): verses 0 to 9."""
    return recommend.Bible(
        pd.DataFrame(
            {
                "book_order": [8] * 6 + [17] * 4,
                "book": ["Ruth"] * 6 + ["Esther"] * 4,
                "chapter": [1, 1, 1, 2, 2, 3, 1, 1, 2, 2],
                "verse": [1, 2, 3, 1, 2, 1, 1, 2, 1, 2],
                "text": "x",
            }
        )
    )


def test_book_codes():
    assert len(recommend.OSIS) == len(set(recommend.OSIS)) == 66
    assert recommend.osis("1Cor.13.4") == (46, 13, 4)
    assert recommend.osis("Ps.23.1") == (19, 23, 1) and recommend.osis("Rev.22.21")[0] == 66


def test_loading_the_links(tmp_path):
    path = tmp_path / "cross_references.txt"
    path.write_text(
        "From Verse\tTo Verse\tVotes\t#www.openbible.info CC-BY 2024-11-04\n"
        "Gen.1.1\tProv.8.22-Prov.8.30\t59\n"
        "Gen.1.1\tJohn.1.1\t10\n"
        "Gen.1.1\tJob.38.4\t9\n"  # under 10 votes
        "Exod.31.18\tDeut.9.10\t-31\n",  # voted down
        encoding="utf-8",
    )
    links = recommend.load_links(path)
    assert len(links) == 2 and links.votes.min() == 10
    first = links.iloc[0]
    assert (first.to_book, first.to_chapter, first.to_verse) == (20, 8, 22)
    assert (first.end_chapter, first.end_verse) == (8, 30)
    second = links.iloc[1]
    assert (second.to_book, second.to_verse) == (second.end_book, second.end_verse) == (43, 1)


def test_a_damaged_download_is_refused(tmp_path):
    wrong = tmp_path / "cross_references.txt"
    wrong.write_text("not the file", encoding="utf-8")
    with pytest.raises(ValueError, match="has changed"):
        recommend.fetch_xrefs(wrong)


def test_the_key_never_answers_with_the_chapter_just_read():
    tiny = tiny_bible()
    links = pd.DataFrame(
        [
            (8, 1, 1, 8, 1, 3, 8, 2, 2, 12),  # Ruth 1:3 to 2:2: only Ruth 2 counts
            (8, 1, 1, 17, 1, 1, 17, 1, 1, 10),  # Esther 1:1
            (8, 1, 1, 8, 1, 2, 8, 1, 3, 30),  # all in Ruth 1: dropped
            (8, 1, 2, 66, 1, 1, 66, 1, 1, 10),  # not in this Bible
            (8, 2, 1, 8, 3, 1, 8, 1, 1, 10),  # a backwards range
        ],
        columns=LINKS,
    )
    key = recommend.build_key(links, tiny)
    assert key.queries.tolist() == [0]
    assert [link.tolist() for link in key.links[0]] == [[3, 4], [6]]
    assert key.unread == 2


def test_a_shelf_is_one_verse_per_chapter_never_its_own():
    tiny = tiny_bible()
    scores = np.array([[9, 8, 7, 1, 5, 2, 3, 6, 4, 0]], dtype=np.float32)
    shelf = recommend.shelves(scores, np.array([0]), tiny, k=3)
    assert shelf.tolist() == [[7, 4, 8]]  # Ruth 1 scores highest, but was just read
    assert len(set(tiny.chapter_of[shelf[0]])) == 3


def test_grading():
    answer = recommend.answer([np.array([3, 4]), np.array([6])])
    assert recommend.grade(np.array([4, 7, 8]), answer) == pytest.approx((0.5, 1.0, 1 / 3))
    assert recommend.grade(np.array([4, 6, 3]), answer) == pytest.approx((1.0, 1.0, 1.0))
    assert recommend.grade(np.array([5, 7, 8]), answer) == (0.0, 0.0, 0.0)


def test_the_blend():
    grid = recommend.weight_grid()
    assert len(grid) == 66 and all(abs(sum(w) - 1) < 1e-9 for w in grid)
    assert grid[0] == (0.0, 0.0, 1.0)  # the fixed order ties are settled by
    flat = recommend.standardise(np.array([[1.0, 1.0, 1.0], [1.0, 2.0, 3.0]]))
    assert np.allclose(flat[0], 0) and np.allclose(flat[1], [-1.2247, 0, 1.2247], atol=1e-4)


def test_chance_is_low_and_the_same_every_time():
    tiny = tiny_bible()
    links = pd.DataFrame([(8, 1, 1, 17, 1, 1, 17, 1, 1, 10)], columns=LINKS)
    key = recommend.build_key(links, tiny)
    first, second = recommend.chance(key, tiny), recommend.chance(key, tiny)
    assert (first == second).all()
    assert 0 < first[0, 0] < 1  # one verse of 7 outside Ruth 1, one shelf of 10 chapters... of 4


def test_passages_are_runs_of_six_verses():
    one = pd.DataFrame(
        {"book_order": 8, "book": "Ruth", "chapter": 1, "verse": range(1, 16), "text": "x"}
    )
    runs = recommend.passages(recommend.Bible(one))  # 15 verses: 1-6, 7-12 and 13-15
    assert [r.tolist() for r in runs] == [list(range(6)), list(range(6, 12)), [12, 13, 14]]
    runs = recommend.passages(recommend.Bible(one.iloc[:14]))  # 13-14 is under 3: dropped
    assert len(runs) == 2
    assert recommend.passages(tiny_bible())[0].tolist() == [0, 1, 2]  # Ruth 1: 3 verses


def test_a_passage_counts_each_link_once():
    key = recommend.Key(
        np.array([0, 1]), [[np.array([6]), np.array([3, 4])], [np.array([6])]], unread=0
    )
    links = recommend.passage_links(np.array([0, 1, 2]), key)
    assert [link.tolist() for link in links] == [[6], [3, 4]]


def test_pooling_a_passage():
    tiny = tiny_bible()
    picks = np.zeros((10, 3), dtype=int)
    scores = np.zeros((10, 3), dtype=np.float32)
    picks[0], scores[0] = [3, 6, 7], [9.0, 1.0, 0.1]  # 6 and 7 share a chapter: one is shown
    picks[1], scores[1] = [6, 8, 3], [1.0, 0.5, 0.0]
    members = np.array([0, 1])
    assert recommend.pool(picks, scores, members, "sum", tiny).tolist() == [3, 6, 8]
    assert recommend.pool(picks, scores, members, "rrf", tiny).tolist() == [6, 3, 8]
    assert recommend.pool(picks, scores, members, "sum", tiny, k=1).tolist() == [3]


def pretend_links(verses: pd.DataFrame) -> pd.DataFrame:
    """Every pretend verse links to the whole chapter two on, in its own book: shepherds to
    shepherds, fishermen to fishermen."""
    rows = []
    for v in verses.itertuples():
        there = verses[(verses.book == v.book) & (verses.chapter == v.chapter + 2)]
        if len(there):
            first, last = there.verse.min(), there.verse.max()
            rows.append((v.book_order, v.chapter, v.verse, v.book_order, v.chapter + 2, first))
            rows[-1] += (v.book_order, v.chapter + 2, last, 20)
    return pd.DataFrame(rows, columns=LINKS)


def test_the_race_and_the_stored_shelves(bible, store, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr(recommend, "SHELF", 2)  # 12 pretend chapters: a shelf of 10 is most
    engine, schema = bible
    verses = pretend_bible().sort_values(["book_order", "chapter", "verse"])  # Bible order
    # Four pretend topics, one per book and odd or even chapter: chapter 1's topic is chapter 3's
    topic = 2 * verses.book.eq("Psalms").to_numpy() + verses.chapter.to_numpy() % 2
    chances = np.eye(4)[topic] * 0.8 + 0.05
    result = recommend.run(engine, pretend_links(verses), chances=chances, schema=schema)
    assert list(result.board.index) == [*recommend.METHODS, "chance"]
    assert result.key.unread == 0 and len(result.key.queries) == 40  # chapters 1-2, 5-6
    board = result.board.recall
    assert (board[["words", "meaning", "topics", "blend"]] > board["chance"]).all()
    assert set(result.weights.held_out_group) == {
        recommend.topics.group_of(b) for b in ("Psalms", "Matthew")
    }
    record = recommend.summary(result)
    assert record.winner.sum() == 1 and record.queries.eq(40).all()
    assert record.recall_at_10.dtype.kind == "i"  # whole percents: the same on any computer
    sections = recommend.by_section(result)
    assert set(sections.section) == {"Poetry and wisdom", "Gospels and Acts"}
    assert set(sections.method) == {"words", result.winner}  # what survives another computer
    assert sections.drop_duplicates("section").queries.sum() == 40
    passages = recommend.passage_summary(recommend.grade_passages(result))
    assert passages.pooler.tolist() == list(recommend.POOLERS) and passages.served.sum() == 1
    assert passages.served[passages.pooler == "full"].eq(False).all()  # a ceiling, not served
    assert passages.recall_at_10.dtype.kind == "i" and passages.passages.gt(0).all()

    picks, scores = recommend.final_shelves(result, k=5)
    assert picks.shape == (len(verses), 5)
    stored = recommend.save(engine, result.bible, picks, scores, schema=schema)
    assert stored == len(verses) * 5
    shelf = recommend.shelf_for(engine, "Psalms", 1, 1, 1, 3, k=4, schema=schema)
    assert 0 < len(shelf) <= 4 and shelf.chapter.nunique() == len(shelf)
    assert not ((shelf.book == "Psalms") & (shelf.chapter == 1)).any()  # just read
    assert shelf.reference.iloc[0].startswith(shelf.book.iloc[0])

    def find(*args):
        return recommend.shelf_for(engine, *args, schema=schema)

    with TestClient(serve.create_app(store, shelves_with=find)) as client:
        answer = client.get("/because-you-read", params={"book": "Psalms", "chapter": 1, "k": 3})
        assert answer.status_code == 200
        body = answer.json()
        assert body["passage"] == "Psalms 1" and len(body["verses"]) == 3
        assert body["readers_like_you"] is False
        passage = {"book": "Psalms", "chapter": 1, "verse": 1, "end_verse": 3}
        assert client.get("/because-you-read", params=passage).json()["passage"] == "Psalms 1:1-3"
        alone = {"book": "Psalms", "chapter": 1, "verse": 3}
        assert client.get("/because-you-read", params=alone).json()["passage"] == "Psalms 1:3"
        nowhere = client.get("/because-you-read", params={"book": "Psalms", "chapter": 99})
        assert nowhere.status_code == 404
        backwards = {"book": "Psalms", "chapter": 2, "end_chapter": 1}
        assert client.get("/because-you-read", params=backwards).status_code == 422


def test_the_api_says_plainly_when_there_are_no_shelves(store):
    def no_table(*_):
        raise ProgrammingError(
            "select", {}, Exception('relation "ml.verse_shelves" does not exist')
        )

    with TestClient(serve.create_app(store, shelves_with=no_table)) as client:
        answer = client.get("/because-you-read", params={"book": "Psalms", "chapter": 23})
        assert answer.status_code == 503 and "recommend.py" in answer.json()["detail"]


def chosen_readings() -> pd.DataFrame:
    """Six made-up readers: four who chose Ruth 1 also chose Esther 4; Jonah 2 has one reader."""
    rows = [(r, "Ruth", 1) for r in range(4)] + [(r, "Esther", 4) for r in range(4)]
    rows += [(4, "Ruth", 1), (5, "Jonah", 2), (5, "Ruth", 1), (0, "Ruth", 1)]  # 0: twice
    return pd.DataFrame(rows, columns=["reader", "book", "chapter"])


def test_readers_like_you_on_a_tiny_made_up_example():
    pairs = recommend.readers_like_you(chosen_readings())
    ruth = pairs[(pairs.book == "Ruth") & (pairs.chapter == 1)]
    assert ruth[["also_book", "also_chapter", "readers"]].values.tolist() == [["Esther", 4, 4]]
    assert ruth.score.iloc[0] == pytest.approx(4 / np.sqrt(6 * 4))  # 6 chose Ruth 1, 4 Esther 4
    assert "Jonah" not in set(pairs.also_book)  # one reader together: under the 3 needed


def test_readers_like_you_stays_off_until_there_is_signal():
    assert recommend.collab_status(chosen_readings()) == (False, 0)
    empty = pd.DataFrame(columns=["reader", "book", "chapter"])
    assert recommend.collab_status(empty) == (False, 0)
    enough = pd.DataFrame(
        [(r, "Psalms", c) for r in range(recommend.MIN_READERS) for c in range(5)],
        columns=["reader", "book", "chapter"],
    )
    assert recommend.collab_status(enough) == (True, recommend.MIN_READERS)
    assert recommend.collab_status(enough[enough.reader > 0]) == (False, 199)


def test_the_charts():
    board = pd.DataFrame(
        {
            "method": [*recommend.METHODS, "chance"],
            "recall_at_10": [3, 9, 12, 4, 14, 0],
            "hit_at_10": [8, 20, 26, 10, 30, 1],
            "precision_at_10": [2, 6, 8, 3, 9, 0],
            "queries": 6591,
            "links": 30000,
            "winner": [False, False, False, False, True, False],
        }
    )
    sections = pd.DataFrame(
        {
            "section": ["Poetry", "Gospels"] * 2,
            "method": ["words", "words", "blend", "blend"],
            "recall_at_10": [8, 9, 12, 15],
            "queries": [900, 1200] * 2,
        }
    )
    figures = [charts.leaderboard(board), charts.by_section(sections)]
    assert all(figure.data and figure.layout.title.text for figure in figures)
    assert "14%" in figures[0].layout.title.text
    assert figures[1].layout.title.text.startswith("<b>Reading Gospels: 15%")
