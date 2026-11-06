"""The streak-at-risk model (Card 7.2): will a reader on a streak miss tomorrow morning?

Each night, a reader who read today has a streak to protect. This trains four models to say how
likely they are to miss tomorrow, so the app can send a gentle nudge to the ones at risk:

    the streak rule        a lookup: how often readers with this streak length missed
    logistic regression    a straight-line model, the classic first try
    XGBoost, LightGBM      gradient-boosted trees, the workhorses of tabular data

They learn from the warehouse (analytics.fct_reader_nights, Card 7.1) and are graded on the
latest three weeks of nights, which none of them see while learning. The window moves with the
data (Card 9), so a weekly retrain is always graded on the most recent behaviour; on the
practice run it starts on 2026-10-06. The simulator's answer key, when it's there, shows the
best score possible: the truth itself, used as a prediction. A real deployment has no answer
key, and everything still works without it.

Run it from the repo root after `python ml/simulate.py` and `dbt build` (under a minute):
    python ml/streak_risk.py
It prints the leaderboard and writes it to ml/results/streak_risk.csv.
"""

import json
import os
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from scipy.stats import loguniform, randint, uniform
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import RandomizedSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sqlalchemy import create_engine, text

# What the models may know about a night: nothing after it (fct_reader_nights guarantees that)
FEATURES = [
    "streak_days",
    "read_rate_7d",
    "read_rate_28d",
    "read_time_spread_14d",
    "days_since_signup",
    "tomorrow_weekday",
    "wording_b",
]
NUMERIC = [f for f in FEATURES if f != "tomorrow_weekday"]
LABEL = "missed_tomorrow"

TEST_DAYS = 21  # the latest three weeks of nights are held out for grading
FOLDS = 4  # time-ordered folds for tuning, inside the training weeks
NUDGE_SHARE = 0.20  # the nudge budget: the riskiest fifth of streak nights
SEED = 7
MODEL_NAMES = {
    "streak_rule": "Streak rule",
    "logistic_regression": "Logistic regression",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "truth": "The truth (answer key)",
}


# ---- The data ----------------------------------------------------------------------------


def load_nights(engine) -> pd.DataFrame:
    """The pretend readers' streak nights: they read today, so tomorrow is genuinely open."""
    with engine.connect() as connection:
        nights = pd.read_sql(
            text(
                """
                select user_key, night, reminder_variant, streak_days, read_rate_7d,
                       read_rate_28d, read_time_spread_14d, days_since_signup,
                       tomorrow_weekday, missed_tomorrow
                from analytics.fct_reader_nights
                where source = 'synthetic' and read_today
                order by night, user_key
                """
            ),
            connection,
        )
    return prepare(nights)


def prepare(nights: pd.DataFrame) -> pd.DataFrame:
    """Plain numbers for the models: the wording as 0 or 1, the label (if known) as 0 or 1."""
    nights = nights.copy()
    nights["night"] = pd.to_datetime(nights.night)
    nights["wording_b"] = (nights.reminder_variant == "B").astype(int)
    for column in NUMERIC:
        nights[column] = nights[column].astype(float)
    nights["tomorrow_weekday"] = nights.tomorrow_weekday.astype(int)
    if LABEL in nights:  # tonight's nights have no label yet (Card 7.5)
        nights[LABEL] = nights[LABEL].astype(int)
    return nights.reset_index(drop=True)


def attach_truth(nights: pd.DataFrame, answer_key: Path) -> pd.DataFrame:
    """Each night's true chance of a miss tomorrow, from the simulator. For grading only."""
    truth = pd.read_csv(answer_key, parse_dates=["day"])
    tomorrow = nights.night + pd.Timedelta(days=1)
    merged = nights.assign(day=tomorrow).merge(truth, on=["user_key", "day"], how="left")
    merged["true_miss_chance"] = 1 - merged.finish_chance
    if merged.true_miss_chance.isna().any():
        raise ValueError("some nights have no truth: the answer key doesn't match the warehouse")
    return merged.drop(columns=["day", "finish_chance"])


def held_out_from(nights: pd.DataFrame, days: int = TEST_DAYS) -> date:
    """The first held-out night: the latest `days` nights with a label are held out."""
    return (nights.night.max() - pd.Timedelta(days=days - 1)).date()


def split(nights: pd.DataFrame, test_from: date | None = None):
    """Learn from the weeks before test_from, and be graded on the weeks from it on. With no
    date, the latest three weeks are held out (held_out_from)."""
    cut = pd.Timestamp(held_out_from(nights) if test_from is None else test_from)
    return nights[nights.night < cut].reset_index(drop=True), nights[
        nights.night >= cut
    ].reset_index(drop=True)


def time_folds(train: pd.DataFrame, folds: int = FOLDS) -> list[tuple[np.ndarray, np.ndarray]]:
    """Folds for tuning that respect time: each one learns from earlier nights only.

    The training nights are cut into folds + 1 blocks of calendar days. Fold k learns from
    blocks 1 to k and is checked on block k + 1, so no fold ever learns from its own future.
    """
    days = np.sort(train.night.unique())
    blocks = np.array_split(days, folds + 1)
    result = []
    for k in range(1, folds + 1):
        learn = np.flatnonzero(train.night < blocks[k][0])
        check = np.flatnonzero(train.night.isin(blocks[k]))
        result.append((learn, check))
    return result


# ---- The models --------------------------------------------------------------------------


class StreakRule(ClassifierMixin, BaseEstimator):
    """The simplest sensible guess: how often readers with this streak length missed."""

    def __init__(self, cap: int = 10):
        self.cap = cap

    def fit(self, X, y):
        streak = np.minimum(np.asarray(X["streak_days"]), self.cap)
        frame = pd.DataFrame({"streak": streak, "missed": np.asarray(y)})
        self.rates_ = frame.groupby("streak").missed.mean().to_dict()
        self.overall_ = float(np.mean(y))
        self.classes_ = np.array([0, 1])
        return self

    def predict_proba(self, X):
        streak = np.minimum(np.asarray(X["streak_days"]), self.cap)
        miss = np.array([self.rates_.get(s, self.overall_) for s in streak])
        return np.column_stack([1 - miss, miss])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def candidates() -> dict[str, tuple[object, dict]]:
    """Each model, and the settings its tuning may try."""
    linear = Pipeline(
        [
            (
                "prepare",
                ColumnTransformer(
                    [
                        (
                            "numbers",
                            Pipeline(
                                [
                                    # Too few reads for a spread: the middle value, flagged
                                    ("fill", SimpleImputer(strategy="median", add_indicator=True)),
                                    ("scale", StandardScaler()),
                                ]
                            ),
                            NUMERIC,
                        ),
                        ("weekday", OneHotEncoder(handle_unknown="ignore"), ["tomorrow_weekday"]),
                    ]
                ),
            ),
            ("model", LogisticRegression(max_iter=2000)),
        ]
    )
    return {
        "streak_rule": (StreakRule(), {}),
        "logistic_regression": (linear, {"model__C": loguniform(1e-3, 1e2)}),
        "xgboost": (
            # Trees handle a missing spread on their own, and need no scaling
            xgb.XGBClassifier(tree_method="hist", n_jobs=1, random_state=SEED, verbosity=0),
            {
                "n_estimators": randint(100, 600),
                "max_depth": randint(2, 7),
                "learning_rate": loguniform(0.01, 0.2),
                "subsample": uniform(0.6, 0.4),
                "colsample_bytree": uniform(0.6, 0.4),
                "min_child_weight": loguniform(1, 50),
                "reg_lambda": loguniform(0.1, 10),
            },
        ),
        "lightgbm": (
            lgb.LGBMClassifier(
                n_jobs=1, random_state=SEED, deterministic=True, force_row_wise=True, verbose=-1
            ),
            {
                "n_estimators": randint(100, 600),
                "num_leaves": randint(4, 64),
                "learning_rate": loguniform(0.01, 0.2),
                "min_child_samples": randint(20, 300),
                "subsample": uniform(0.6, 0.4),
                "subsample_freq": [1],
                "colsample_bytree": uniform(0.6, 0.4),
                "reg_lambda": loguniform(0.1, 10),
            },
        ),
    }


@dataclass
class Trained:
    name: str
    model: object
    cv_roc_auc: float  # the tuning score, from the time-ordered folds
    settings: dict
    seconds: float


def train(name: str, nights: pd.DataFrame, tries: int = 25, folds: int = FOLDS) -> Trained:
    """Tune a model on time-ordered folds, then fit the best settings on all training nights."""
    model, space = candidates()[name]
    started = time.perf_counter()
    if not space:  # nothing to tune
        model.fit(nights[FEATURES], nights[LABEL])
        return Trained(name, model, float("nan"), {}, time.perf_counter() - started)
    search = RandomizedSearchCV(
        model,
        space,
        n_iter=tries if name != "logistic_regression" else min(tries, 10),
        scoring="roc_auc",
        cv=time_folds(nights, folds),
        random_state=SEED,
        n_jobs=-1,
        refit=True,
    )
    search.fit(nights[FEATURES], nights[LABEL])
    settings = {k: _plain(v) for k, v in search.best_params_.items()}
    return Trained(
        name, search.best_estimator_, search.best_score_, settings, time.perf_counter() - started
    )


def _plain(value):
    """Settings as plain numbers, so they read cleanly in the results file."""
    if isinstance(value, (np.floating, float)):
        return round(float(value), 4)
    if isinstance(value, np.integer):
        return int(value)
    return value


# ---- Grading -----------------------------------------------------------------------------


def miss_chance(model, nights: pd.DataFrame) -> np.ndarray:
    return model.predict_proba(nights[FEATURES])[:, 1]


def grade(chance: np.ndarray, missed: np.ndarray, share: float = NUDGE_SHARE) -> dict:
    """How good a set of predictions is, on the measures the plan names.

    roc_auc:   how often a night that ended in a miss was ranked riskier than one that didn't
    pr_auc:    average precision, for the nights that did end in a miss
    brier:     the mean squared gap between the chance given and what happened (lower is better)
    precision and recall at the nudge budget: nudge the riskiest share of nights, then see
    how many nudges went to a reader who really missed, and how many misses got a nudge
    """
    chance, missed = np.asarray(chance, dtype=float), np.asarray(missed, dtype=int)
    nudged = np.zeros(len(chance), dtype=bool)
    nudged[np.argsort(-chance, kind="stable")[: int(round(share * len(chance)))]] = True
    return {
        "roc_auc": round(roc_auc_score(missed, chance), 4),
        "pr_auc": round(average_precision_score(missed, chance), 4),
        "brier": round(brier_score_loss(missed, chance), 4),
        "log_loss": round(log_loss(missed, np.clip(chance, 1e-6, 1 - 1e-6)), 4),
        "nudge_precision": round(missed[nudged].mean(), 4),
        "nudge_recall": round(missed[nudged].sum() / missed.sum(), 4),
    }


def leaderboard(trained: list[Trained], test: pd.DataFrame) -> pd.DataFrame:
    """Every model graded on the held-out weeks, with the truth as the best possible."""
    rows = []
    for t in trained:
        rows.append(
            {
                "model": t.name,
                **grade(miss_chance(t.model, test), test[LABEL]),
                "cv_roc_auc": round(t.cv_roc_auc, 4) if t.cv_roc_auc == t.cv_roc_auc else None,
                "settings": json.dumps(t.settings, sort_keys=True) if t.settings else "",
            }
        )
    if "true_miss_chance" not in test:  # no answer key: graded on what happened, nothing more
        return pd.DataFrame(rows).assign(gap_closed=None)
    truth = grade(test.true_miss_chance, test[LABEL])
    rows.append({"model": "truth", **truth, "cv_roc_auc": None, "settings": ""})
    board = pd.DataFrame(rows)
    # How much of the way from the streak rule to perfect knowledge each model got
    rule, best = board.set_index("model").roc_auc[["streak_rule", "truth"]]
    board["gap_closed"] = ((board.roc_auc - rule) / (best - rule)).round(3)
    return board


def importance(trained: Trained) -> pd.Series:
    """What a tree model leaned on: each feature's share of the total gain."""
    if trained.name == "xgboost":
        gain = trained.model.get_booster().get_score(importance_type="gain")
        totals = pd.Series({f: gain.get(f, 0.0) for f in FEATURES})
    elif trained.name == "lightgbm":
        totals = pd.Series(
            trained.model.booster_.feature_importance(importance_type="gain"), index=FEATURES
        )
    else:
        raise ValueError(f"{trained.name} has no tree importance")
    return (totals / totals.sum()).sort_values(ascending=False)


def run(engine, answer_key: Path | None, tries: int = 25):
    """Load, split, train every model, and grade them. Returns the leaderboard and the models.
    With an answer key, the truth joins the leaderboard as the best possible score."""
    nights = load_nights(engine)
    if answer_key is not None:
        nights = attach_truth(nights, answer_key)
    learn, test = split(nights)
    trained = [train(name, learn, tries) for name in candidates()]
    return leaderboard(trained, test), trained, learn, test


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    repo = Path(__file__).resolve().parents[1]
    board, trained, learn, test = run(
        create_engine(url), repo / "data" / "answer_key" / "finish_chance.csv.gz"
    )
    print(f"Learned from {len(learn):,} streak nights; graded on {len(test):,} held-out ones")
    print(f"(from {test.night.min():%Y-%m-%d}; {test[LABEL].mean():.1%} of them ended in a miss)\n")
    shown = board.assign(model=board.model.map(MODEL_NAMES)).drop(columns="settings")
    print(shown.to_string(index=False))
    times = ", ".join(f"{MODEL_NAMES[t.name]} {t.seconds:.0f}s" for t in trained)
    print(f"\nTraining time: {times}")
    out = Path(__file__).with_name("results") / "streak_risk.csv"
    out.parent.mkdir(exist_ok=True)
    board.to_csv(out, index=False, lineterminator="\n")
    print(f"\nThe leaderboard: {out.relative_to(repo)}")
