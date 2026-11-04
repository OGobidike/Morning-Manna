"""The streak-at-risk service (Card 7.4): it serves the champion, and says exactly what it says."""

import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_registry as mr  # noqa: E402
import serve  # noqa: E402
import streak_risk as sr  # noqa: E402

# The race and store fixtures are in conftest.py

A_NIGHT = {
    "streak_days": 4,
    "read_rate_7d": 0.71,
    "read_rate_28d": 0.6,
    "read_time_spread_14d": 12.5,
    "days_since_signup": 30,
    "tomorrow_weekday": 6,
    "reminder_variant": "B",
}


def as_requests(nights) -> list[dict]:
    """Held-out nights, written the way a caller would send them."""
    rows = []
    for night in nights.itertuples():
        spread = night.read_time_spread_14d
        rows.append(
            {
                "streak_days": int(night.streak_days),
                "read_rate_7d": float(night.read_rate_7d),
                "read_rate_28d": float(night.read_rate_28d),
                "read_time_spread_14d": None if np.isnan(spread) else float(spread),
                "days_since_signup": int(night.days_since_signup),
                "tomorrow_weekday": int(night.tomorrow_weekday),
                "reminder_variant": "B" if night.wording_b else "A",
            }
        )
    return rows


@pytest.fixture
def crowned(race, store):
    """A store whose champion is the race's best model."""
    board, trained, learn, test = race
    _, best, decision = mr.track(board, trained, learn, test, store=store)
    return store, next(t.model for t in trained if t.name == best), str(decision.version)


def test_with_no_champion_it_says_so_plainly(store):
    with TestClient(serve.create_app(store)) as client:
        assert client.get("/health").json() == {"status": "ok", "model_loaded": False}
        answer = client.post("/streak-risk", json={"nights": [A_NIGHT]})
        assert answer.status_code == 503 and "model_registry.py" in answer.json()["detail"]


def test_the_bare_address_leads_to_the_docs(store):
    with TestClient(serve.create_app(store)) as client:
        answer = client.get("/", follow_redirects=False)
        assert answer.status_code == 307 and answer.headers["location"] == "/docs"
        assert client.get("/").status_code == 200  # and the docs page is there


def test_it_serves_the_champion_and_says_which(crowned):
    store, _, version = crowned
    with TestClient(serve.create_app(store)) as client:
        assert client.get("/health").json()["model_loaded"] is True
        model = client.get("/model").json()
        assert model["version"] == version and model["alias"] == "champion"
        assert model["features"] == sr.FEATURES


def test_it_answers_exactly_what_the_model_says_offline(race, crowned):
    *_, test = race
    store, model, version = crowned
    nights = test.head(300)
    with TestClient(serve.create_app(store)) as client:
        answer = client.post("/streak-risk", json={"nights": as_requests(nights)}).json()
    assert answer["model_version"] == version
    offline = np.round(sr.miss_chance(model, nights), 4)
    assert np.array_equal(np.array(answer["miss_chances"]), offline)


@pytest.mark.parametrize(
    "change",
    [
        {"tomorrow_weekday": 8},  # there's no 8th day
        {"read_rate_7d": 1.5},  # a rate above 100%
        {"streak_days": 0},  # only nights after a reading have a streak to protect
        {"reminder_variant": "C"},  # only two wordings exist
        {"read_rate_28": 0.5},  # a misspelled field is refused, not quietly ignored
    ],
)
def test_impossible_nights_are_refused(crowned, change):
    store, *_ = crowned
    with TestClient(serve.create_app(store)) as client:
        answer = client.post("/streak-risk", json={"nights": [{**A_NIGHT, **change}]})
    assert answer.status_code == 422


def test_batches_must_be_a_sensible_size(crowned):
    store, *_ = crowned
    with TestClient(serve.create_app(store)) as client:
        assert client.post("/streak-risk", json={"nights": []}).status_code == 422
        too_many = {"nights": [A_NIGHT] * (serve.MAX_NIGHTS + 1)}
        assert client.post("/streak-risk", json=too_many).status_code == 422
        a_full_batch = {"nights": [A_NIGHT] * serve.MAX_NIGHTS}
        assert len(client.post("/streak-risk", json=a_full_batch).json()["miss_chances"]) == 1000


def test_a_reader_with_too_few_reads_for_a_spread_still_gets_an_answer(crowned):
    store, *_ = crowned
    with TestClient(serve.create_app(store)) as client:
        night = {**A_NIGHT, "read_time_spread_14d": None}
        answer = client.post("/streak-risk", json={"nights": [night]})
    assert answer.status_code == 200 and 0 < answer.json()["miss_chances"][0] < 1
