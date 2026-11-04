"""Shared by the registry's and the service's tests: a small race, and a throwaway store."""

import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_streak_risk import pretend_nights  # noqa: E402

import streak_risk as sr  # noqa: E402


@pytest.fixture(scope="session")
def race():
    """Four models trained on small made-up nights: the leaderboard, models, and both splits."""
    nights = pretend_nights()
    learn, test = sr.split(nights, date(2026, 9, 21))
    trained = [sr.train(name, learn, tries=2, folds=2) for name in sr.candidates()]
    return sr.leaderboard(trained, test), trained, learn, test


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A fresh, empty store for each test. MLflow sets MLFLOW_TRACKING_URI itself when it's
    pointed somewhere, so it's cleared before and after, or one test would write into another's."""
    os.environ.pop("MLFLOW_TRACKING_URI", None)
    monkeypatch.chdir(tmp_path)
    yield tmp_path / "mlruns"
    os.environ.pop("MLFLOW_TRACKING_URI", None)
