"""Tracking and versioning the streak-at-risk models with MLflow (Card 7.3).

Every race (python ml/model_registry.py) is written down as MLflow runs: one parent run
for the race, with the charts and the leaderboard, and one run per model, with its settings,
its scores and the model itself. The best model is then registered as a new version of
"streak_risk", and it takes the "@champion" alias only if it beats the current champion on the
same held-out nights. The API (Card 7.4) asks for models:/streak_risk@champion, so a worse
model can never reach readers by accident.

Where the records live: MLFLOW_TRACKING_URI if it's set (the MLflow server in docker compose,
Card 9, at http://localhost:5000), otherwise a SQLite file in ml/mlruns/, which git ignores. To
look around the SQLite one, from the repo root:
    MLFLOW_DISABLE_TELEMETRY=true mlflow ui --backend-store-uri sqlite:///ml/mlruns/mlflow.db
then open localhost:5000.

Airflow runs it every Sunday (the retrain_models DAG, Card 9). The simulator's answer key is
used only if it's there: without it, the race is graded on what happened, with no truth row
and no charts, which is all a real deployment would have.
"""

import logging
import os
import tempfile
import warnings
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

# MLflow 3 sends usage statistics to its makers unless told not to; nothing leaves this machine
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")
# It also prints a hint for AI coding tools on every import; nothing here needs it
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
# uv venvs have no pip, and MLflow only wants pip's version for a conda file nothing here uses
logging.getLogger("mlflow.utils.environment").setLevel(logging.ERROR)
# MLflow warns that whole-number columns can't hold a missing value. Ours (tomorrow's weekday,
# reminder wording B) are never missing: the warehouse always fills them in
warnings.filterwarnings("ignore", message="Hint: Inferred schema contains integer column")

import mlflow  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from mlflow import MlflowClient  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

import streak_risk as sr  # noqa: E402

STORE = Path(__file__).with_name("mlruns")
EXPERIMENT = "streak-risk"
MODEL_NAME = "streak_risk"
ALIAS = "champion"
# The exact libraries each saved model needs, so loading it later rebuilds the same thing
LIBRARIES = ["scikit-learn", "xgboost-cpu", "lightgbm", "pandas", "numpy", "skops"]
# MLflow saves scikit-learn models with skops, which (unlike pickle) rebuilds only the types it's
# told to trust, so a tampered model file can't run code. Each model gets just what it needs
TRUSTED = {
    "streak_rule": ["streak_risk.StreakRule"],
    "logistic_regression": ["numpy.dtype"],
    "xgboost": ["xgboost.core.Booster", "xgboost.sklearn.XGBClassifier"],
    "lightgbm": ["collections.OrderedDict", "lightgbm.basic.Booster",
                 "lightgbm.sklearn.LGBMClassifier"],
}


def use_store(store: Path = STORE) -> str:
    """Point MLflow at the tracking server if one is set, or at a SQLite file in store."""
    # Read before MLflow is pointed anywhere: set_tracking_uri() sets this variable itself
    server = os.environ.get("MLFLOW_TRACKING_URI")
    uri = server or f"sqlite:///{store.resolve() / 'mlflow.db'}"
    if not server:
        store.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    if mlflow.get_experiment_by_name(EXPERIMENT) is None:
        # Saved models go next to the database, unless a server decides for itself
        artifacts = None if server else (store.resolve() / "artifacts").as_uri()
        mlflow.create_experiment(EXPERIMENT, artifact_location=artifacts)
    mlflow.set_experiment(EXPERIMENT)
    return uri


def libraries() -> list[str]:
    return [f"{name}=={version(name)}" for name in LIBRARIES]


@dataclass
class Decision:
    version: str
    challenger_roc_auc: float
    champion_roc_auc: float | None  # the old champion, re-scored on the same nights
    promoted: bool


def log_race(board: pd.DataFrame, trained: list[sr.Trained], learn: pd.DataFrame,
             test: pd.DataFrame, charts: dict | None = None) -> dict[str, str]:
    """Write one race down: a parent run, and a run per model holding the model itself.

    Returns where each saved model lives (a models:/ address). Call use_store() first.
    """
    scores = board.set_index("model")
    runs = {}
    with mlflow.start_run(run_name="race"):
        mlflow.log_params(
            {"test_from": f"{test.night.min():%Y-%m-%d}", "folds": sr.FOLDS,
             "nudge_share": sr.NUDGE_SHARE,
             "seed": sr.SEED, "features": ",".join(sr.FEATURES)}
        )
        mlflow.set_tags(
            {"learn_nights": len(learn), "test_nights": len(test),
             "test_miss_rate": round(float(test[sr.LABEL].mean()), 4),
             "libraries": " ".join(libraries())}
        )
        # The truth is the ceiling every model is measured against, when there's an answer key
        if "truth" in scores.index:
            mlflow.log_metrics({f"truth_{k}": float(v) for k, v in scores.loc["truth"].items()
                                if k in ("roc_auc", "pr_auc", "brier", "nudge_recall")})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "leaderboard.csv"
            board.to_csv(path, index=False, lineterminator="\n")
            mlflow.log_artifact(str(path))
            for name, figure in (charts or {}).items():
                page = Path(folder) / f"streak-risk-{name}.html"
                figure.write_html(page, include_plotlyjs="cdn")
                mlflow.log_artifact(str(page), artifact_path="charts")
        for t in trained:
            with mlflow.start_run(run_name=sr.MODEL_NAMES[t.name], nested=True):
                mlflow.log_params({"model": t.name, **t.settings})
                metrics = scores.loc[t.name].drop(["settings"]).dropna().astype(float)
                mlflow.log_metrics({**metrics.to_dict(), "train_seconds": round(t.seconds, 2)})
                saved = mlflow.sklearn.log_model(
                    t.model,
                    name="model",
                    # Asking the saved model for a prediction gives the chance of a miss
                    pyfunc_predict_fn="predict_proba",
                    input_example=test[sr.FEATURES].head(3),
                    pip_requirements=libraries(),
                    # The streak rule is our own class, so its code travels with the model
                    code_paths=[sr.__file__],
                    skops_trusted_types=TRUSTED[t.name],
                )
                runs[t.name] = saved.model_uri
    return runs


def champion_version():
    """The registry's record of the current champion, or None if there's no champion yet."""
    client = MlflowClient()
    try:
        registered = client.get_registered_model(MODEL_NAME)
    except mlflow.exceptions.MlflowException as error:
        # Only "never registered" means no champion; any other failure must stop the caller, or
        # a hiccup could crown a worse model, or serve none at all
        if error.error_code == "RESOURCE_DOES_NOT_EXIST":
            return None
        raise
    version = registered.aliases.get(ALIAS)
    return None if version is None else client.get_model_version(MODEL_NAME, version)


@dataclass
class Champion:
    model: object
    version: str
    held_out_roc_auc: str | None


def load_champion(store: Path = STORE) -> Champion | None:
    """The registry's current champion, ready to predict, or None if there isn't one yet.

    Shared by the service (Card 7.4) and the nightly scoring (Card 7.5)."""
    use_store(store)
    record = champion_version()
    if record is None:
        return None
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{record.version}")
    # MLflow numbers versions; we always say them as text, the way the registry shows them
    return Champion(model, str(record.version), record.tags.get("held_out_roc_auc"))


def champion_score(test: pd.DataFrame) -> float | None:
    """The current champion's ROC-AUC on these nights, or None if there's no champion yet."""
    if champion_version() is None:
        return None
    champion = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{ALIAS}")
    return float(roc_auc_score(test[sr.LABEL], sr.miss_chance(champion, test)))


def promote(model_uri: str, test: pd.DataFrame) -> Decision:
    """Register a saved model, and make it the champion only if it does strictly better.

    Both models are scored on the same held-out nights, so the comparison is fair even if
    the champion was trained on older data.
    """
    challenger = mlflow.sklearn.load_model(model_uri)
    new = float(roc_auc_score(test[sr.LABEL], sr.miss_chance(challenger, test)))
    old = champion_score(test)
    promoted = old is None or new > old
    registered = mlflow.register_model(model_uri, MODEL_NAME)
    client = MlflowClient()
    client.set_model_version_tag(MODEL_NAME, registered.version, "held_out_roc_auc", f"{new:.4f}")
    client.set_model_version_tag(MODEL_NAME, registered.version, "promoted", str(promoted))
    if promoted:
        client.set_registered_model_alias(MODEL_NAME, ALIAS, registered.version)
    return Decision(registered.version, new, old, promoted)


def track(board, trained, learn, test, charts=None, store: Path = STORE):
    """Log the race, then put its best model up against the champion."""
    uri = use_store(store)
    runs = log_race(board, trained, learn, test, charts)
    contenders = board[board.model.isin(runs)]
    best = contenders.sort_values("roc_auc", ascending=False, kind="stable").model.iloc[0]
    return uri, best, promote(runs[best], test)


def same_predictions(model, loaded, test: pd.DataFrame) -> bool:
    """A saved model must predict exactly what it did before it was saved."""
    return bool(np.array_equal(sr.miss_chance(model, test), sr.miss_chance(loaded, test)))


if __name__ == "__main__":
    from sqlalchemy import create_engine

    import streak_risk_charts as charts

    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    repo = Path(__file__).resolve().parents[1]
    key = repo / "data" / "answer_key" / "finish_chance.csv.gz"
    key = key if key.exists() else None
    board, trained, learn, test = sr.run(create_engine(url), key)
    if key is None:
        print("No answer key here: graded on what happened, without the truth or the charts")
    drawn = None if key is None else charts.draw(trained, test, board)
    uri, best, decision = track(board, trained, learn, test, drawn)
    print(f"Logged the race: {len(trained)} models, to {uri}")
    print(f"Registered {sr.MODEL_NAMES[best]} as {MODEL_NAME} version {decision.version} "
          f"(held-out ROC-AUC {decision.challenger_roc_auc:.4f})")
    if decision.champion_roc_auc is None:
        print(f"No champion yet, so it becomes @{ALIAS}")
    elif decision.promoted:
        print(f"It beats the champion ({decision.champion_roc_auc:.4f}), so it becomes @{ALIAS}")
    else:
        print(f"It doesn't beat the champion ({decision.champion_roc_auc:.4f}), "
              f"so @{ALIAS} stays where it is")
    loaded = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}/{decision.version}")
    model = next(t.model for t in trained if t.name == best)
    print("Loaded back from the registry, it predicts exactly as before: "
          f"{same_predictions(model, loaded, test)}")
