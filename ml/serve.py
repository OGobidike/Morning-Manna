"""The ML service (Cards 7.4 and 8.2): the models behind a small web API.

It loads models:/streak_risk@champion from the registry once, when it starts, and answers:

    GET  /health          is it up, and is a model loaded?
    GET  /model           which version is serving, and how it scored on held-out nights
    POST /streak-risk     for a batch of streak nights, each reader's chance of missing tomorrow
    GET  /search          the verses that answer a question, by meaning and by keyword (8.2)
    GET  /topics          the 30 topic tags (8.3)
    GET  /topics/{tag}    a topic's best verses (8.3)

/search needs the nlp extra and the verse vectors (python ml/verse_embeddings.py); /topics/{tag}
needs the tags (python ml/topics.py). Both connect on first use, so the service starts as fast as
before.

It's a service of its own, apart from the app's API in backend/, so the app never carries the
model libraries (over 200 MB) and either one can be restarted or updated without the other.
To pick up a new champion, restart it.

Run it from the repo root, then open http://localhost:8001 (it goes to /docs, which shows every
endpoint and lets you try them):
    ml/.venv/bin/uvicorn --app-dir ml serve:app --port 8001
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

import model_registry as mr  # also switches MLflow's telemetry off
import streak_risk as sr

MAX_NIGHTS = 1000  # one request's batch; the nightly scoring (Card 7.5) sends several
MAX_RESULTS = 20
TOPIC_TAGS = Path(__file__).with_name("data") / "topic_tags.csv"


class Night(BaseModel):
    """What was known about one reader by the end of a day they read (fct_reader_nights)."""

    model_config = ConfigDict(extra="forbid")  # a misspelled field is an error, not ignored

    streak_days: int = Field(ge=1, description="Mornings read in a row, today included")
    read_rate_7d: float = Field(ge=0, le=1, description="Share of the last 7 days they read")
    read_rate_28d: float = Field(ge=0, le=1, description="Share of the last 28 days they read")
    read_time_spread_14d: float | None = Field(
        default=None, ge=0,
        description="How much their reading time wanders, in minutes (none with fewer than two "
        "reads in 14 days)",
    )
    days_since_signup: int = Field(ge=0)
    tomorrow_weekday: int = Field(ge=1, le=7, description="1 is Monday, 7 is Sunday")
    reminder_variant: Literal["A", "B"] = Field(description="Their reminder wording")


class Nights(BaseModel):
    nights: list[Night] = Field(min_length=1, max_length=MAX_NIGHTS)


class Chances(BaseModel):
    model_version: str = Field(description="Which version answered, so every answer is traceable")
    miss_chances: list[float] = Field(description="Each night's chance of a miss, in order")


class Verse(BaseModel):
    reference: str = Field(examples=["Philippians 4:6"])
    book: str
    chapter: int
    verse: int
    text: str


class Found(BaseModel):
    question: str
    translation: str
    method: str
    verses: list[Verse] = Field(description="Best first")


class Topic(BaseModel):
    tag: str = Field(examples=["patience"])
    label: str = Field(examples=["Patience"])
    description: str


class TopicPage(BaseModel):
    tag: str
    label: str
    translation: str
    verses: list[Verse] = Field(description="Best first")


def database():
    from sqlalchemy import create_engine

    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    return create_engine(url.replace("postgresql://", "postgresql+psycopg://"))


def needs_nlp(missing: ImportError) -> HTTPException:
    return HTTPException(
        503, f"This needs the nlp extra, pip install -e \".[nlp]\" (no {missing.name})"
    )


def topic_finder():
    """A function from (tag, translation, k) to a topic's best verses, made on first use."""
    try:
        import topics
    except ImportError as missing:
        raise needs_nlp(missing) from missing
    engine = database()
    return lambda tag, translation, k: topics.topic_verses(engine, tag, translation, k)


def searcher():
    """A function from (question, translation, k, method) to verses. It's made on the first
    search: loading the model takes a few seconds, and the streak-risk endpoints don't need it."""
    try:
        import search
        import verse_embeddings as ve
    except ImportError as missing:
        raise needs_nlp(missing) from missing
    engine = database()
    encode = search.asking(ve.encoder(ve.MODEL), ve.MODEL)
    return lambda question, translation, k, method: search.search(
        engine, question, encode, translation, k, method
    )


def as_features(nights: list[Night]) -> pd.DataFrame:
    """The API speaks the reader's terms; the model wants the exact columns it learned from."""
    frame = pd.DataFrame([night.model_dump() for night in nights])
    frame["wording_b"] = (frame.reminder_variant == "B").astype(int)
    frame["read_time_spread_14d"] = frame.read_time_spread_14d.astype(float)  # None becomes NaN
    for column in sr.NUMERIC:
        frame[column] = frame[column].astype(float)
    frame["tomorrow_weekday"] = frame.tomorrow_weekday.astype(int)
    return frame[sr.FEATURES]


def create_app(store: Path = mr.STORE, search_with=None, topics_with=None) -> FastAPI:
    """search_with and topics_with stand in for searcher() and topic_finder() in tests."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.champion = mr.load_champion(store)
        app.state.search_with = search_with
        app.state.topics_with = topics_with
        yield

    app = FastAPI(
        title="Morning Manna: the ML service",
        description="Streak risk, search by meaning and topic tags, behind one small API.",
        lifespan=lifespan,
    )

    def champion() -> mr.Champion:
        if app.state.champion is None:
            raise HTTPException(
                503, "No champion model yet: run python ml/model_registry.py, then restart"
            )
        return app.state.champion

    @app.get("/", include_in_schema=False)
    def home():
        # Opening the bare address (uvicorn prints it as a link) lands on the docs, not a 404
        return RedirectResponse("/docs")

    @app.get("/health")
    def health():
        return {"status": "ok", "model_loaded": app.state.champion is not None}

    @app.get("/model")
    def model():
        serving = champion()
        return {
            "name": mr.MODEL_NAME,
            "alias": mr.ALIAS,
            "version": serving.version,
            "held_out_roc_auc": serving.held_out_roc_auc,
            "features": sr.FEATURES,
        }

    @app.post("/streak-risk", response_model=Chances)
    def streak_risk(request: Nights):
        serving = champion()
        chances = sr.miss_chance(serving.model, as_features(request.nights))
        return Chances(
            model_version=serving.version, miss_chances=np.round(chances, 4).tolist()
        )

    @app.get("/search", response_model=Found)
    def search_verses(
        q: str = Query(min_length=2, max_length=200, description="A question, in your own words"),
        k: int = Query(5, ge=1, le=MAX_RESULTS, description="How many verses"),
        translation: Literal["KJV", "ASV"] = "KJV",
        method: Literal["meaning", "hybrid", "keyword"] = Query(
            "meaning",
            description="meaning (the best on the labelled questions), hybrid or keyword",
        ),
    ):
        from sqlalchemy.exc import ProgrammingError

        if app.state.search_with is None:
            app.state.search_with = searcher()
        try:
            found = app.state.search_with(q, translation, k, method)
        except ProgrammingError as missing:  # no vectors table yet
            raise HTTPException(
                503, "No verse vectors yet: run python ml/verse_embeddings.py"
            ) from missing
        return Found(
            question=q,
            translation=translation,
            method=method,
            verses=found[["reference", "book", "chapter", "verse", "text"]].to_dict("records"),
        )

    tags = pd.read_csv(TOPIC_TAGS)[["tag", "label", "description"]]
    labels = dict(zip(tags.tag, tags.label, strict=True))

    @app.get("/topics", response_model=list[Topic])
    def topic_list():
        return tags.to_dict("records")

    @app.get("/topics/{tag}", response_model=TopicPage)
    def topic_page(
        tag: str,
        k: int = Query(10, ge=1, le=MAX_RESULTS, description="How many verses"),
        translation: Literal["KJV", "ASV"] = "KJV",
    ):
        from sqlalchemy.exc import ProgrammingError

        if tag not in labels:
            raise HTTPException(404, f"No topic {tag!r}: GET /topics lists them")
        if app.state.topics_with is None:
            app.state.topics_with = topic_finder()
        try:
            found = app.state.topics_with(tag, translation, k)
        except ProgrammingError as missing:  # no tags table yet
            raise HTTPException(503, "No topic tags yet: run python ml/topics.py") from missing
        return TopicPage(
            tag=tag,
            label=labels[tag],
            translation=translation,
            verses=found[["reference", "book", "chapter", "verse", "text"]].to_dict("records"),
        )

    return app


app = create_app()
