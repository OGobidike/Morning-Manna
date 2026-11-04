"""Tonight's streak risk (Card 7.5): score every reader on a streak, and pick who gets a nudge.

    analytics.fct_reader_tonight  -->  the champion model  -->  ml.streak_risk_scores

Each reader who read on the last day of their source's data has a streak to protect. The
champion (models:/streak_risk@champion) gives each one a chance of missing tomorrow, and
anyone above the nudge cut-off is flagged for a gentle nudge. The cut-off is set once, on the
held-out nights the model was graded on (Card 7.2): the chance that marks their riskiest fifth.
So the rule works the same for 10,000 readers or for one, and a calm night nudges fewer
people than a shaky one. The app reads the flags (the next card).

Run it from the repo root, after dbt build, once a champion is crowned:
    python ml/score_tonight.py
Scoring the same night again replaces its scores, so a re-run is always safe. Card 9 hands it
to Airflow, to run every night after dbt.
"""

import os
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    MetaData,
    Table,
    Text,
    create_engine,
    text,
)

import model_registry as mr  # also switches MLflow's telemetry off
import streak_risk as sr

SCHEMA = "ml"  # the models' output, apart from the app's tables and dbt's
TABLE = "streak_risk_scores"


def scores_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    """One row per reader per night: their chance of a miss, and whether to nudge them."""
    return Table(
        TABLE,
        metadata,
        Column("night", Date, primary_key=True),
        Column("user_key", Text, primary_key=True),
        Column("source", Text, nullable=False),
        Column("miss_chance", Float, nullable=False),
        Column("nudge", Boolean, nullable=False),
        Column("nudge_cutoff", Float, nullable=False),  # the chance at or above which we nudge
        Column("model_version", Text, nullable=False),  # which champion said so
        Column("scored_at", DateTime(timezone=True), nullable=False),
        schema=schema,
    )


def load_tonight(engine) -> pd.DataFrame:
    """Everyone on a streak tonight, with the features the model learned from."""
    with engine.connect() as connection:
        tonight = pd.read_sql(
            text("select * from analytics.fct_reader_tonight order by source, user_key"),
            connection,
        )
    return sr.prepare(tonight)


def nudge_cutoff(
    champion: mr.Champion, held_out: pd.DataFrame, share: float = sr.NUDGE_SHARE
) -> float:
    """The chance that marks the riskiest share of the held-out nights the model was graded
    on. Set from those nights, never from tonight's crowd, so it can't shift with how many
    readers happen to be on a streak."""
    chances = np.round(sr.miss_chance(champion.model, held_out), 4)
    return float(np.quantile(chances, 1 - share))


def score(tonight: pd.DataFrame, champion: mr.Champion, cutoff: float) -> pd.DataFrame:
    """Each reader's chance of missing tomorrow, and a nudge for everyone at the cut-off or
    above it."""
    chances = np.round(sr.miss_chance(champion.model, tonight), 4)
    return pd.DataFrame(
        {
            "night": tonight.night.dt.date,
            "user_key": tonight.user_key,
            "source": tonight.source,
            "miss_chance": chances,
            "nudge": chances >= cutoff,
            "nudge_cutoff": round(cutoff, 4),
            "model_version": champion.version,
        }
    )


def save(engine, scores: pd.DataFrame, schema: str | None = SCHEMA) -> None:
    """Replace these nights' scores in one transaction: all of them land, or none do."""
    metadata = MetaData()
    table = scores_table(metadata, schema)
    rows = scores.assign(scored_at=datetime.now(UTC)).to_dict("records")
    with engine.begin() as connection:
        if schema:
            connection.execute(text(f"create schema if not exists {schema}"))
        metadata.create_all(connection)
        connection.execute(table.delete().where(table.c.night.in_(set(scores.night))))
        connection.execute(table.insert(), rows)


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    tonight = load_tonight(engine)
    if tonight.empty:
        raise SystemExit("Nobody is on a streak tonight, so there's nothing to score")
    champion = mr.load_champion()
    if champion is None:
        raise SystemExit("No champion yet: run python ml/model_registry.py first")
    _, held_out = sr.split(sr.load_nights(engine))
    cutoff = nudge_cutoff(champion, held_out)
    scores = score(tonight, champion, cutoff)
    save(engine, scores)
    print(f"Scored with streak_risk version {champion.version}, saved to {SCHEMA}.{TABLE}.")
    print(f"Nudge anyone with a {cutoff:.1%} chance of a miss or more (the riskiest "
          f"{sr.NUDGE_SHARE:.0%} of the nights it was graded on):")
    for (source, night), readers in scores.groupby(["source", "night"]):
        print(
            f"  {source}, the night of {night}: {len(readers):,} on a streak, "
            f"{int(readers.nudge.sum()):,} to nudge, average chance of a miss "
            f"{readers.miss_chance.mean():.0%}, highest {readers.miss_chance.max():.0%}"
        )
