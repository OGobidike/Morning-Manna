"""Tracking and versioning (Card 7.3): every race written down, and a champion that must earn it."""

import sys
from pathlib import Path

import mlflow
import numpy as np
import pytest
from mlflow import MlflowClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import model_registry as mr  # noqa: E402
import streak_risk as sr  # noqa: E402

# The race and store fixtures are in conftest.py


def test_a_race_is_written_down_with_every_model(race, store):
    board, trained, learn, test = race
    mr.use_store(store)
    saved = mr.log_race(board, trained, learn, test)
    assert set(saved) == set(sr.candidates())
    runs = mlflow.search_runs(experiment_names=[mr.EXPERIMENT], output_format="list")
    models = [r for r in runs if "model" in r.data.params]
    assert len(runs) == 5 and len(models) == 4  # the race, and a run for each model
    for run in models:
        name = run.data.params["model"]
        expected = board.set_index("model").roc_auc[name]
        assert run.data.metrics["roc_auc"] == pytest.approx(expected)


def test_everything_stays_in_the_store(race, store, tmp_path):
    board, trained, learn, test = race
    mr.track(board, trained, learn, test, store=store)
    assert sorted(p.name for p in store.iterdir()) == ["artifacts", "mlflow.db"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["mlruns"]  # nothing anywhere else


def test_the_first_model_becomes_champion_and_loads_back_exactly(race, store):
    board, trained, learn, test = race
    _, best, decision = mr.track(board, trained, learn, test, store=store)
    assert decision.promoted and decision.champion_roc_auc is None
    champion = mlflow.sklearn.load_model(f"models:/{mr.MODEL_NAME}@{mr.ALIAS}")
    model = next(t.model for t in trained if t.name == best)
    assert mr.same_predictions(model, champion, test)


def test_a_tie_or_a_worse_model_never_takes_the_crown(race, store):
    board, trained, learn, test = race
    mr.use_store(store)
    saved = mr.log_race(board, trained, learn, test)
    first = mr.promote(saved["lightgbm"], test)
    tie = mr.promote(saved["lightgbm"], test)
    worse = mr.promote(saved["streak_rule"], test)
    assert first.promoted and not tie.promoted and not worse.promoted
    client = MlflowClient()
    assert client.get_model_version_by_alias(mr.MODEL_NAME, mr.ALIAS).version == first.version
    # Each one is still registered and labelled, so the history is complete
    tags = client.get_model_version(mr.MODEL_NAME, worse.version).tags
    assert tags["promoted"] == "False"
    assert float(tags["held_out_roc_auc"]) < first.challenger_roc_auc


def test_a_better_model_takes_the_crown(race, store):
    board, trained, learn, test = race
    mr.use_store(store)
    saved = mr.log_race(board, trained, learn, test)
    rule = mr.promote(saved["streak_rule"], test)
    tree = mr.promote(saved["lightgbm"], test)
    assert rule.promoted and tree.promoted
    assert tree.champion_roc_auc == pytest.approx(rule.challenger_roc_auc)
    client = MlflowClient()
    assert client.get_model_version_by_alias(mr.MODEL_NAME, mr.ALIAS).version == tree.version


def test_the_streak_rule_loads_back_without_pickle(race, store):
    """Our own class goes through skops, trusted by name, and comes back working."""
    board, trained, learn, test = race
    mr.use_store(store)
    saved = mr.log_race(board, trained, learn, test)
    flavor = mlflow.models.get_model_info(saved["streak_rule"]).flavors["sklearn"]
    assert flavor["serialization_format"] == "skops"
    loaded = mlflow.sklearn.load_model(saved["streak_rule"])
    rule = next(t.model for t in trained if t.name == "streak_rule")
    assert type(loaded).__name__ == "StreakRule" and mr.same_predictions(rule, loaded, test)


def test_a_race_without_an_answer_key_is_tracked_too(race, store):
    """A real deployment has no answer key: the race is still logged, and still crowns."""
    _, trained, learn, test = race
    test = test.drop(columns="true_miss_chance")
    plain = sr.leaderboard(trained, test)
    _, _, decision = mr.track(plain, trained, learn, test, store=store)
    assert decision.promoted
    parent = mlflow.search_runs(filter_string="tags.mlflow.runName = 'race'").iloc[0]
    assert "metrics.truth_roc_auc" not in parent.index or np.isnan(parent["metrics.truth_roc_auc"])
    assert parent["params.test_from"] == f"{test.night.min():%Y-%m-%d}"
