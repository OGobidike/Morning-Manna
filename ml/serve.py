"""The streak-at-risk service (Card 7.4): the champion model behind a small web API.

It loads models:/streak_risk@champion from the registry once, when it starts, and answers:

    GET  /health          is it up, and is a model loaded?
    GET  /model           which version is serving, and how it scored on held-out nights
    POST /streak-risk     for a batch of streak nights, each reader's chance of missing tomorrow

It's a service of its own, apart from the app's API in backend/, so the app never carries the
model libraries (over 200 MB) and either one can be restarted or updated without the other.
To pick up a new champion, restart it.

Run it from the repo root (http://localhost:8001/docs shows every endpoint, and lets you try them):
    ml/.venv/bin/uvicorn --app-dir ml serve:app --port 8001
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import mlflow
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import model_registry as mr  # also switches MLflow's telemetry off
import streak_risk as sr

MAX_NIGHTS = 1000  # one request's batch; the nightly scoring (Card 7.5) sends several


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


@dataclass
class Champion:
    model: object
    version: str
    held_out_roc_auc: str | None


def load_champion(store: Path = mr.STORE) -> Champion | None:
    """The registry's current champion, ready to predict, or None if there isn't one yet."""
    mr.use_store(store)
    record = mr.champion_version()
    if record is None:
        return None
    model = mlflow.sklearn.load_model(f"models:/{mr.MODEL_NAME}/{record.version}")
    # MLflow numbers versions; the API always answers with text, the way the registry shows them
    return Champion(model, str(record.version), record.tags.get("held_out_roc_auc"))


def as_features(nights: list[Night]) -> pd.DataFrame:
    """The API speaks the reader's terms; the model wants the exact columns it learned from."""
    frame = pd.DataFrame([night.model_dump() for night in nights])
    frame["wording_b"] = (frame.reminder_variant == "B").astype(int)
    frame["read_time_spread_14d"] = frame.read_time_spread_14d.astype(float)  # None becomes NaN
    for column in sr.NUMERIC:
        frame[column] = frame[column].astype(float)
    frame["tomorrow_weekday"] = frame.tomorrow_weekday.astype(int)
    return frame[sr.FEATURES]


def create_app(store: Path = mr.STORE) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.champion = load_champion(store)
        yield

    app = FastAPI(
        title="Morning Manna: streak risk",
        description="Tonight, how likely is each reader on a streak to miss tomorrow morning?",
        lifespan=lifespan,
    )

    def champion() -> Champion:
        if app.state.champion is None:
            raise HTTPException(
                503, "No champion model yet: run python ml/model_registry.py, then restart"
            )
        return app.state.champion

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

    return app


app = create_app()
