"""Topic tags (Card 8.3): Nave's read correctly, graded fairly, stored for the app.

No model is downloaded: the stand-in encoder from 8.1's tests plays BGE. The database tests use
8.2's pretend Bible (shepherds in the Psalms, fishermen in Matthew) and are skipped without a
Postgres locally, but fail in CI.
"""

import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import ProgrammingError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_search import ASK, bible, pretend_bible  # noqa: E402, F401 (bible is a fixture)

import serve  # noqa: E402
import topics  # noqa: E402
import topics_charts as charts  # noqa: E402

# Fingerprints of the tags and the key, frozen before any tagger ran: changing either after
# seeing results would grade the taggers on themselves
TAGS_MD5 = "4ce6495a60e25b9bbf1180eaee24cf79"
KEY_MD5 = "c31bb32bc74a34fbb4a0d992f67c39dc"
SIZES = {
    ("Exodus", 6): 30,
    ("Numbers", 17): 13,
    ("Genesis", 1): 31,
    ("Genesis", 2): 25,
    ("1 Chronicles", 6): 81,
    ("1 Chronicles", 23): 32,
    ("1 Chronicles", 24): 31,
    ("Jude", 1): 25,
    ("Song of Solomon", 8): 14,
    ("Matthew", 8): 34,
    ("Mark", 6): 56,
}


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_naves_references_become_verses():
    found, unread = topics.references("EXO 6:16-20; 1CH 6:2,3; 23:13; 24", SIZES)
    assert unread == 0
    assert len(found) == 5 + 2 + 1 + 31  # the book carries over; "24" is all of chapter 24
    assert ("1 Chronicles", 23, 13) in found and ("1 Chronicles", 24, 31) in found
    found, _ = topics.references("GEN 1:31-2:2", SIZES)  # across a chapter
    assert found == {("Genesis", 1, 31), ("Genesis", 2, 1), ("Genesis", 2, 2)}
    found, _ = topics.references("NUM 17; MRK 6:31,32; with MAT 8:18", SIZES)
    assert len(found) == 13 + 2 + 1
    found, _ = topics.references("Jude 1:20; So 8:6,7", SIZES)  # the two books written oddly
    assert found == {("Jude", 1, 20), ("Song of Solomon", 8, 6), ("Song of Solomon", 8, 7)}
    _, unread = topics.references("XYZ 1:2; nonsense", SIZES)
    assert unread == 2


def test_only_the_chosen_headings_line_counts():
    entry = "-General scriptures concerning PSA 9:18; 16:9\n-OF THE WICKED JOB 8:13"
    assert topics.heading_refs(entry, "General scriptures concerning") == "PSA 9:18; 16:9"
    assert topics.heading_refs(entry, "OF THE WICKED") == "JOB 8:13"
    with pytest.raises(KeyError):
        topics.heading_refs(entry, "OF THE RIGHTEOUS")


def test_building_the_key_from_naves(tmp_path):
    naves = tmp_path / "naves.csv"
    naves.write_text(
        "section,subject,entry\n"
        'H,HOPE,"-General scriptures concerning EXO 6:1-25\n-OF THE WICKED NUM 17:1-13"\n'
        "R,REST,-SPIRITUAL GEN 1:1-3\n",
        encoding="utf-8",
    )
    tags = pd.DataFrame(
        {
            "tag": ["hope", "rest"],
            "label": ["Hope", "Rest"],
            "description": ["hope", "rest"],
            "keywords": ["hope", "rest"],
            "naves": ["HOPE > General scriptures concerning", "REST > SPIRITUAL"],
        }
    )
    tags["headings"] = tags.naves.str.split(r"\s*\|\s*")
    key, report = topics.build_key(naves, tags, SIZES)
    assert set(key.tag) == {"hope"}  # rest has 3 verses, under the 20 a tag needs
    assert len(key) == 25 and not key.chapter.ne(6).any()  # never the wicked's verses
    assert report.set_index("tag").verses.to_dict() == {"hope": 25, "rest": 3}


def test_the_tags_and_key_are_frozen():
    assert md5(topics.TAGS) == TAGS_MD5, "the tags changed after they were frozen"
    assert md5(topics.KEY) == KEY_MD5, "the answer key changed after it was frozen"
    key = pd.read_csv(topics.KEY)
    assert key.groupby("tag").size().min() >= topics.MIN_VERSES
    assert set(key.tag) == set(topics.load_tags().tag)
    assert not key.duplicated().any()


def test_every_book_has_a_code_and_a_group():
    books = set(topics.CODES.values())
    assert len(books) == 66
    groups = {topics.group_of(b) for b in books}
    assert groups == set(range(topics.GROUPS))
    assert topics.group_of("Psalms") == topics.group_of("Psalms")


def test_grading():
    scores = np.array([0.9, 0.8, 0.1, 0.0])
    truth = np.array([True, False, True, False])
    assert topics.precision_at(scores, truth, k=2) == 0.5
    scores = np.array([[0.9, 0.1], [0.2, 0.0], [0.0, 0.0]])  # the last verse has no tag
    y = np.array([[True, False], [False, True], [False, False]])
    assert topics.top_hits(scores, y, 1) == 0.5  # verse 2's best tag is wrong
    assert topics.top_hits(scores, y, 2) == 0.5  # its right tag scores 0: not tagged
    luck = topics.chance(y)
    assert luck["top1"] == 0.5 and luck["top3"] == 1.0  # 2 tags: 3 guesses cover everything


def test_the_trained_tagger_only_learns_from_other_books():
    rng = np.random.default_rng(7)
    y = rng.random((300, 2)) < 0.2
    vectors = rng.normal(size=(300, 8)) + y @ np.array([[3.0] * 8, [-3.0] * 8])
    groups = np.arange(300) % topics.GROUPS
    scores = topics.trained_scores(vectors, y, groups)
    graded = topics.grade(scores, y, ["a", "b"])
    assert (graded.average_precision > 0.8).all()  # learnable, and learned (chance: 0.2)
    leaky = topics.trained_scores(vectors, np.zeros_like(y), groups)
    assert not leaky.any()  # a tag with nothing to learn from scores 0, and doesn't crash


def test_what_gets_stored():
    scores = np.array([[0.9, 0.1, 0.5], [0.2, 0.8, 0.1], [0.3, 0.2, 0.4]])
    kept = topics.keep(scores)
    assert kept.sum(axis=1).min() >= min(topics.PER_VERSE, 3)  # each verse's best tags
    assert kept[:, 0].sum() == 3  # each tag's best verses (all 3, fewer than PER_TAG)


@pytest.fixture
def pretend_tags():
    tags = pd.DataFrame(
        {
            "tag": ["hope", "joy"],
            "label": ["Hope", "Joy"],
            "description": ["the lord is my shepherd", "fishers of men"],
            "keywords": ["shepherd sheep", "fish nets"],
            "naves": ["-", "-"],
        }
    )
    verses = pretend_bible()
    key = pd.DataFrame(
        {
            "tag": np.where(verses.book == "Psalms", "hope", "joy"),
            "book": verses.book,
            "chapter": verses.chapter,
            "verse": verses.verse,
        }
    )
    return tags, key


def test_the_race_and_the_stored_tags(bible, pretend_tags, store):  # noqa: F811 (the fixture)
    engine, schema = bible
    tags, key = pretend_tags
    result = topics.run(engine, ASK, key=key, tags=tags, schema=schema)
    assert list(result.board.index) == [*topics.METHODS, "chance"]
    assert result.board.loc["zero_shot", "average_precision"] == 1.0  # words alone separate them
    assert result.board.loc["keyword", "top1"] == 1.0
    per_tag = topics.by_tag(result)  # whole percents, so another computer's float agrees
    assert per_tag.precision_at_20.dtype.kind == "i" and per_tag.average_precision.max() <= 100
    record = topics.summary(result)
    assert record.winner.sum() == 1 and record.tags.eq(2).all()
    stored = topics.save(engine, result, topics.final_scores(result), schema=schema)
    assert stored == 60 * 2  # every pretend verse keeps both tags (fewer than 3 exist)
    page = topics.topic_verses(engine, "hope", k=5, schema=schema)
    assert len(page) == 5 and (page.book == "Psalms").all()
    assert page.reference.str.startswith("Psalms ").all()

    def find(tag, translation, k):
        return topics.topic_verses(engine, tag, translation, k, schema=schema)

    with TestClient(serve.create_app(store, topics_with=find)) as client:
        listed = client.get("/topics").json()
        assert len(listed) == 30 and {"tag", "label", "description"} <= set(listed[0])
        answer = client.get("/topics/hope", params={"k": 3})
        assert answer.status_code == 200
        body = answer.json()
        assert body["label"] == "Hope" and len(body["verses"]) == 3
        assert all(v["book"] == "Psalms" for v in body["verses"])
        assert client.get("/topics/no-such-topic").status_code == 404
        assert client.get("/topics/hope", params={"k": 0}).status_code == 422


def test_the_api_says_plainly_when_there_are_no_tags(store):
    def no_table(*_):
        raise ProgrammingError("select", {}, Exception('relation "ml.verse_topics" does not exist'))

    with TestClient(serve.create_app(store, topics_with=no_table)) as client:
        answer = client.get("/topics/hope")
        assert answer.status_code == 503 and "topics.py" in answer.json()["detail"]


def test_the_charts():
    board = pd.DataFrame(
        {
            "method": [*topics.METHODS, "chance"],
            "precision_at_20": [26, 38, 39, 1],
            "average_precision": [8, 11, 15, 1],
            "top1": [25, 32, 35, 4],
            "top3": [36, 50, 57, 12],
            "tags": 2,
            "tagged_verses": 9,
            "winner": [False, False, True, False],
        }
    )
    per_tag = pd.DataFrame(
        {
            "tag": ["hope", "joy"] * 3,
            "method": [m for m in topics.METHODS for _ in range(2)],
            "precision_at_20": [50, 20, 60, 30, 85, 10],
            "average_precision": 10,
            "verses": 30,
        }
    )
    figures = [charts.leaderboard(board), charts.by_tag(per_tag, {"hope": "Hope", "joy": "Joy"})]
    assert all(figure.data and figure.layout.title.text for figure in figures)
    assert figures[1].layout.title.text.startswith("<b>Hope: 85%")
