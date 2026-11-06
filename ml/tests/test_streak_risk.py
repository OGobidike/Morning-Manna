"""The streak-at-risk model (Card 7.2): its folds, its baseline, its grading, and a tiny run."""

import gzip
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streak_risk as sr  # noqa: E402
import streak_risk_charts as charts  # noqa: E402

START = date(2026, 9, 1)


def pretend_nights(readers: int = 150, days: int = 30, seed: int = 3) -> pd.DataFrame:
    """Small made-up streak nights where the 28-day read rate really does drive misses."""
    rng = np.random.default_rng(seed)
    rows = []
    for reader in range(readers):
        keenness = rng.uniform(0.3, 0.95)
        for day in range(days):
            rate = float(np.clip(keenness + rng.normal(0, 0.05), 0, 1))
            rows.append(
                {
                    "user_key": f"r{reader}",
                    "night": pd.Timestamp(START) + pd.Timedelta(days=day),
                    "reminder_variant": "B" if reader % 2 else "A",
                    "streak_days": int(rng.integers(1, 15)),
                    "read_rate_7d": rate,
                    "read_rate_28d": rate,
                    # Some readers have too few reads for a spread: the models must cope
                    "read_time_spread_14d": None if day < 2 else float(rng.uniform(0, 90)),
                    "days_since_signup": day,
                    "tomorrow_weekday": (day % 7) + 1,
                    "missed_tomorrow": bool(rng.random() > keenness),
                    "true_miss_chance": 1 - keenness,
                }
            )
    return sr.prepare(pd.DataFrame(rows))


def test_tuning_folds_never_learn_from_their_own_future():
    nights = pretend_nights()
    folds = sr.time_folds(nights, folds=4)
    assert len(folds) == 4
    for learn, check in folds:
        assert len(learn) and len(check)
        assert nights.night[learn].max() < nights.night[check].min()
    # Every check block is new: together they cover the nights after the first block
    checked = np.concatenate([check for _, check in folds])
    assert len(checked) == len(set(checked))


def test_the_split_puts_every_night_on_exactly_one_side_of_the_line():
    nights = pretend_nights()
    learn, test = sr.split(nights, date(2026, 9, 21))
    assert len(learn) + len(test) == len(nights)
    assert learn.night.max() < pd.Timestamp("2026-09-21") <= test.night.min()


def test_the_streak_rule_is_how_often_that_streak_length_missed():
    X = pd.DataFrame({"streak_days": [1, 1, 1, 1, 3, 3, 12, 20]})
    y = [1, 1, 0, 0, 0, 0, 1, 0]
    rule = sr.StreakRule(cap=10).fit(X, y)
    chances = rule.predict_proba(pd.DataFrame({"streak_days": [1, 3, 50, 2]}))[:, 1]
    # 1 day: half missed. 3 days: none. 10 or more: one of two. Never seen: everyone's rate
    assert list(chances) == [0.5, 0.0, 0.5, 3 / 8]


def test_grading_by_hand():
    chance = np.array([0.9, 0.8, 0.7, 0.2, 0.1])
    missed = np.array([1, 0, 1, 0, 0])
    graded = sr.grade(chance, missed, share=0.4)  # nudge the riskiest two
    assert graded["nudge_precision"] == 0.5  # one of the two nudged really missed
    assert graded["nudge_recall"] == 0.5  # one of the two misses got a nudge
    assert graded["roc_auc"] == round(5 / 6, 4)  # 5 of the 6 miss-vs-read pairs ranked right
    assert sr.grade(missed, missed)["roc_auc"] == 1.0  # knowing the future is perfect


def test_the_truth_lines_up_with_the_morning_after(tmp_path):
    nights = sr.prepare(
        pd.DataFrame(
            {
                "user_key": ["a", "a"],
                "night": ["2026-10-01", "2026-10-02"],
                "reminder_variant": ["A", "A"],
                **{column: [1, 1] for column in sr.NUMERIC if column != "wording_b"},
                "tomorrow_weekday": [5, 6],
                "missed_tomorrow": [False, True],
            }
        )
    )
    key = tmp_path / "finish_chance.csv.gz"
    with gzip.open(key, "wt") as f:
        f.write("user_key,day,finish_chance\na,2026-10-01,0.1\na,2026-10-02,0.8\na,2026-10-03,0.3\n")
    graded = sr.attach_truth(nights, key)
    # Tonight's truth is about tomorrow morning: not today's chance, which already happened
    assert list(graded.true_miss_chance.round(6)) == [0.2, 0.7]
    with gzip.open(key, "wt") as f:
        f.write("user_key,day,finish_chance\na,2026-10-02,0.8\n")
    with pytest.raises(ValueError, match="no truth"):
        sr.attach_truth(nights, key)


@pytest.fixture(scope="module")
def tiny_run():
    nights = pretend_nights()
    learn, test = sr.split(nights, date(2026, 9, 21))
    trained = [sr.train(name, learn, tries=2, folds=2) for name in sr.candidates()]
    return sr.leaderboard(trained, test), trained, test


def test_every_model_trains_and_is_graded_against_the_rule_and_the_truth(tiny_run):
    board, trained, _ = tiny_run
    assert list(board.model) == [*sr.candidates(), "truth"]
    gap = board.set_index("model").gap_closed
    assert gap.streak_rule == 0 and gap.truth == 1
    # The read rate is the whole story here, and the streak rule can't see it
    assert (board.set_index("model").roc_auc.drop("streak_rule") > 0.6).all()


def test_the_trees_find_the_feature_that_matters(tiny_run):
    _, trained, _ = tiny_run
    for t in trained:
        if t.name in ("xgboost", "lightgbm"):
            shares = sr.importance(t)
            assert shares.sum() == pytest.approx(1)
            assert shares.index[0] in ("read_rate_28d", "read_rate_7d")


def test_training_twice_gives_the_same_model():
    learn, test = sr.split(pretend_nights(readers=60), date(2026, 9, 21))
    first, second = (sr.train("lightgbm", learn, tries=2, folds=2) for _ in range(2))
    assert first.settings == second.settings
    assert np.array_equal(sr.miss_chance(first.model, test), sr.miss_chance(second.model, test))


def test_the_charts_draw(tiny_run):
    board, trained, test = tiny_run
    figures = [
        charts.races(trained, test, board),
        charts.budget(trained, test, board),
        charts.honesty(trained, test, "lightgbm"),
        charts.learned(trained),
    ]
    for figure in figures:
        assert figure.data and figure.layout.title.text


def test_the_held_out_weeks_move_with_the_data():
    nights = pretend_nights()
    first = sr.held_out_from(nights)
    assert (nights.night.max() - pd.Timestamp(first)).days == sr.TEST_DAYS - 1
    learn, test = sr.split(nights)
    assert test.night.min() == pd.Timestamp(first) and learn.night.max() < test.night.min()
    a_week_on = nights.assign(night=nights.night + pd.Timedelta(days=7))
    assert sr.held_out_from(a_week_on) == first + pd.Timedelta(days=7)
    # The practice run's last labelled night is 2026-10-26, so its window is unchanged
    practice = pd.DataFrame({"night": pd.to_datetime(["2026-07-30", "2026-10-26"])})
    assert sr.held_out_from(practice) == date(2026, 10, 6)


def test_without_an_answer_key_it_grades_what_happened(race):
    board, trained, _, test = race
    plain = sr.leaderboard(trained, test.drop(columns="true_miss_chance"))
    assert "truth" not in set(plain.model) and plain.gap_closed.isna().all()
    with_truth = board.set_index("model").roc_auc.drop("truth")
    assert plain.set_index("model").roc_auc.equals(with_truth)  # the models' grades don't change
