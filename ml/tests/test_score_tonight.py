"""Tonight's scores (Card 7.5): the right readers nudged, and re-runs that replace, not pile up."""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import MetaData, create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_registry as mr  # noqa: E402
import score_tonight as st  # noqa: E402
import streak_risk as sr  # noqa: E402

# The race fixture is in conftest.py


@pytest.fixture(scope="module")
def champion(race):
    """The race's LightGBM, standing in for the registry's champion."""
    _, trained, *_ = race
    return mr.Champion(next(t.model for t in trained if t.name == "lightgbm"), "7", "0.66")


def tonight_from(nights: pd.DataFrame, day: str, source: str = "synthetic") -> pd.DataFrame:
    """Some nights, dressed as tonight's: no label, one night, one source, and one row per
    reader, as fct_reader_tonight guarantees (the scores table's key refuses anything else)."""
    return nights.drop(columns=[sr.LABEL, "true_miss_chance"]).assign(
        night=pd.Timestamp(day), source=source
    )


def readers(nights: pd.DataFrame) -> pd.DataFrame:
    """Each reader's first night only."""
    return nights.drop_duplicates("user_key").reset_index(drop=True)


def test_nights_without_a_label_can_be_prepared():
    raw = pd.DataFrame(
        {"user_key": ["a"], "night": ["2026-10-27"], "reminder_variant": ["B"],
         **{c: [1] for c in sr.NUMERIC if c != "wording_b"}, "tomorrow_weekday": [3]}
    )
    prepared = sr.prepare(raw)
    assert prepared.wording_b.tolist() == [1] and sr.LABEL not in prepared


def test_the_cutoff_marks_the_riskiest_fifth_of_the_graded_nights(race, champion):
    *_, test = race
    cutoff = st.nudge_cutoff(champion, test)
    chances = np.round(sr.miss_chance(champion.model, test), 4)
    assert (chances >= cutoff).mean() == pytest.approx(sr.NUDGE_SHARE, abs=0.02)


def test_everyone_at_or_above_the_cutoff_is_nudged_and_nobody_else(race, champion):
    *_, test = race
    tonight = tonight_from(readers(test).head(120), "2026-10-27")
    scores = st.score(tonight, champion, cutoff=0.3)
    assert (scores.nudge == (scores.miss_chance >= 0.3)).all()
    assert set(scores.model_version) == {"7"} and set(scores.nudge_cutoff) == {0.3}
    assert set(scores.night) == {date(2026, 10, 27)}


def test_a_crowd_of_one_still_gets_its_nudge(race, champion):
    """The rule caught in rehearsal: 'the riskiest fifth' of one reader is nobody, but a reader
    above the cut-off must be nudged however few are on a streak tonight."""
    *_, test = race
    chances = sr.miss_chance(champion.model, test)
    risky = tonight_from(test.iloc[[int(np.argmax(chances))]], "2026-10-28", source="app")
    assert st.score(risky, champion, cutoff=0.3).nudge.tolist() == [True]


@pytest.fixture
def warehouse(tmp_path):
    """A small SQLite stand-in for Postgres, so the saving can be tested anywhere."""
    return create_engine(f"sqlite:///{tmp_path / 'scores.db'}")


def saved(engine) -> pd.DataFrame:
    table = st.scores_table(MetaData(), schema=None)
    with engine.connect() as connection:
        return pd.DataFrame(connection.execute(select(table)).mappings().all())


def test_scoring_a_night_again_replaces_it(race, champion, warehouse):
    *_, test = race
    first = st.score(tonight_from(readers(test).head(50), "2026-10-27"), champion, cutoff=0.3)
    other = st.score(tonight_from(readers(test).iloc[50:80], "2026-10-26"), champion, cutoff=0.3)
    st.save(warehouse, other, schema=None)
    st.save(warehouse, first, schema=None)
    st.save(warehouse, first, schema=None)  # the same night, scored again
    rows = saved(warehouse)
    assert len(rows) == 80  # 50 tonight, once, plus the other night's 30 untouched
    assert rows.groupby("night").size().to_dict() == {date(2026, 10, 26): 30,
                                                      date(2026, 10, 27): 50}


def test_a_failed_save_leaves_the_old_scores_in_place(race, champion, warehouse):
    *_, test = race
    good = st.score(tonight_from(readers(test).head(20), "2026-10-27"), champion, cutoff=0.3)
    st.save(warehouse, good, schema=None)
    broken = good.assign(miss_chance=None)  # a score that can't be saved
    with pytest.raises(Exception):
        st.save(warehouse, broken, schema=None)
    assert len(saved(warehouse)) == 20  # all or nothing: the earlier scores survive
