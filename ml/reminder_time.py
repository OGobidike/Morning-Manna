"""The best reminder time (Card 7.7): when is each reader about to read?

The app sends the morning reminder at the reader's wake time. For an early riser that's
right: they start reading about ten minutes later. A commuter reads on the train, over an
hour after waking, so by then the reminder is long gone. This learns, for every reader, how
long after waking they usually start, on weekdays and at weekends, and picks the time most
likely to land in the half hour before they start (WINDOW).

The data can say when people read, not whether a better-timed reminder makes them read
more: in the simulator, the reminder's timing changes nothing. Proving that takes an
experiment with real readers.

How it picks a time, for one reader and one kind of day (weekday or weekend):
    1. Each of Card 7.6's groups has its usual gaps after waking, learned from its readers.
    2. The reader's own reads say which group they look like (Bayes' rule). After a few
       reads it's nearly certain; with none, it's just how common each group is.
    3. Their own gaps are blended in, trusted more as they pile up (partial pooling). How
       much to trust them (k) is tuned on the last learning weeks.
    4. The time with the best chance of landing in the half hour before they start wins.
       With no history, that's usually the wake time itself: the safest guess.

It's graded on the streak model's three held-out weeks, replayed as if it re-ran every
night: each morning's pick uses only the reads before that morning. The truth, from the
simulator's own recipe, is the best any pick could do. It's the answer key, read in one
place only (load_truth), the way the personas were.

Run it from the repo root after dbt build and python ml/personas.py (a few seconds):
    python ml/reminder_time.py
It prints the leaderboard, writes ml/results/reminder_time.csv, and saves every reader's
reminder times to ml.reminder_times.
"""

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, create_engine, text
from sqlalchemy.exc import ProgrammingError

import simulate

TEST_FROM = date(2026, 10, 6)  # the streak model's three held-out weeks
TUNE_DAYS = 21  # the last three learning weeks, for tuning k
WINDOW = 30  # a reminder is on time if it lands in the half hour before they start
GRID = np.arange(0, 241, 5)  # the times it can pick: 0 to 4 hours after waking
KS = (0, 1, 2, 5, 10, 20, 50, 100, np.inf)  # how much to trust the group over their own reads
# The practice run learns from the pretend readers only, so the record comes out the same on
# any warehouse built from the same simulation. Real readers still get their times.
LEARN_FROM = "synthetic"
SCHEMA, TABLE = "ml", "reminder_times"
CONTESTANTS = {
    "wake": "At wake time (today's app)",
    "everyone": "One time for everyone",
    "own": "Their own reads",
    "model": "The model: the group their reads look like",
    "truth": "The truth (answer key)",
}


# ---- The data ----------------------------------------------------------------------------


def load_starts(engine) -> pd.DataFrame:
    """Every reader's daily reading starts, oldest first, with the gap after waking."""
    with engine.connect() as connection:
        starts = pd.read_sql(
            text(
                """
                select user_key, source, local_day, at_weekend, minutes_after_wake
                from analytics.fct_reader_starts
                order by user_key, local_day
                """
            ),
            connection,
        )
    starts["at_weekend"] = starts.at_weekend.astype(bool)
    starts["minutes_after_wake"] = starts.minutes_after_wake.astype(float)
    return starts


def load_groups(engine) -> pd.Series:
    """Each grouped reader's group, found by Card 7.6 from their habits alone."""
    try:
        with engine.connect() as connection:
            groups = pd.read_sql(
                text(f"select user_key, persona_group from {SCHEMA}.reader_personas"), connection
            )
    except ProgrammingError as missing:
        raise RuntimeError("No reader groups yet: run python ml/personas.py first") from missing
    return groups.set_index("user_key").persona_group.astype(int)


def load_readers(engine) -> pd.DataFrame:
    """Every reader and their wake time, in minutes after midnight."""
    with engine.connect() as connection:
        readers = pd.read_sql(
            text(
                """
                select user_key, source,
                       extract(hour from wake_time) * 60 + extract(minute from wake_time)
                           as wake_minute
                from analytics.stg_users
                order by user_key
                """
            ),
            connection,
        )
    readers["wake_minute"] = readers.wake_minute.astype(int)
    return readers


def load_truth(engine) -> pd.DataFrame:
    """The answer key: each pretend reader's persona, and whether their reminders are on (a
    snoozed reminder delays a reading by ten minutes). Only grading uses it."""
    with engine.connect() as connection:
        truth = pd.read_sql(
            text(
                """
                select u.user_key, u.persona, r.reminders_on
                from analytics.dim_users as u
                join raw.readers as r using (user_key)
                where u.source = 'synthetic'
                """
            ),
            connection,
        )
    truth["reminders_on"] = truth.reminders_on.astype(bool)
    return truth.set_index("user_key")


# ---- What the groups usually do ----------------------------------------------------------


def on_time(gaps) -> np.ndarray:
    """One row per gap, one column per time on GRID: 1 if a reminder at that time would land
    in the half hour before the reader started."""
    gaps = np.asarray(gaps, dtype=float)[:, None]
    return ((gaps > GRID) & (gaps <= GRID + WINDOW)).astype(float)


@dataclass
class Profiles:
    """Each group's usual gaps after waking, from the learning days. Index 0 is weekdays,
    1 weekends."""

    groups: list[int]
    share: np.ndarray  # how common each group is
    mean: np.ndarray  # groups x 2: the average gap
    spread: np.ndarray  # groups x 2: how much it wanders
    weekend_share: np.ndarray  # how much of each group's reading falls at weekends
    curves: np.ndarray  # 2 x groups x GRID: the chance each time lands on time
    everyone: np.ndarray  # 2 x GRID: the same, for all readers together


def learn_profiles(starts: pd.DataFrame, groups: pd.Series, until: date) -> Profiles:
    learn = starts[(starts.local_day < until) & (starts.source == LEARN_FROM)]
    grouped = learn.join(groups.rename("group"), on="user_key", how="inner")
    names = sorted(grouped.group.unique())
    counts = grouped.groupby("group").user_key.nunique().reindex(names).to_numpy(float)
    mean, spread = np.zeros((len(names), 2)), np.zeros((len(names), 2))
    curves = np.zeros((2, len(names), len(GRID)))
    for i, group in enumerate(names):
        for day in (0, 1):
            gaps = grouped[(grouped.group == group) & (grouped.at_weekend == bool(day))]
            gaps = gaps.minutes_after_wake
            mean[i, day], spread[i, day] = gaps.mean(), gaps.std()
            curves[day, i] = on_time(gaps).mean(axis=0)
    everyone = np.vstack(
        [
            on_time(learn[learn.at_weekend == bool(day)].minutes_after_wake).mean(axis=0)
            for day in (0, 1)
        ]
    )
    weekend_share = grouped.groupby("group").at_weekend.mean().reindex(names).to_numpy()
    return Profiles(names, counts / counts.sum(), mean, spread, weekend_share, curves, everyone)


# ---- Picking a time ----------------------------------------------------------------------


def _likelihood(profiles: Profiles, gaps: np.ndarray, weekend: np.ndarray) -> np.ndarray:
    """How likely each read is under each group: its gap, and the kind of day it fell on."""
    day = weekend.astype(int)
    mean, spread = profiles.mean[:, day].T, profiles.spread[:, day].T
    which_day = np.where(weekend[:, None], profiles.weekend_share, 1 - profiles.weekend_share)
    return norm.logpdf(gaps[:, None], mean, spread) + np.log(which_day)


def _choose(
    profiles: Profiles,
    likelihood: np.ndarray,
    own_sum: np.ndarray,
    own_count: np.ndarray,
    weekend: np.ndarray,
    k: float,
) -> dict[str, np.ndarray]:
    """Every contestant's pick, from a reader's history: the summed likelihood of their reads
    under each group, and their own on-time rows for this kind of day, summed and counted."""
    day = weekend.astype(int)
    log_post = np.log(profiles.share) + likelihood
    posterior = np.exp(log_post - log_post.max(axis=1, keepdims=True))
    posterior /= posterior.sum(axis=1, keepdims=True)
    prior = np.einsum("ng,ngt->nt", posterior, profiles.curves[day])
    own = np.divide(
        own_sum, own_count[:, None], out=np.zeros_like(own_sum), where=own_count[:, None] > 0
    )
    if np.isinf(k):
        trust = np.zeros(len(own_count))
    else:
        with np.errstate(invalid="ignore"):
            trust = np.nan_to_num(own_count / (own_count + k))  # no reads and k = 0: none
    blend = trust[:, None] * own + (1 - trust[:, None]) * prior
    return {
        "wake": np.zeros(len(day), dtype=int),
        "everyone": GRID[profiles.everyone[day].argmax(axis=1)],
        "own": np.where(own_count > 0, GRID[own.argmax(axis=1)], 0),
        "model": GRID[blend.argmax(axis=1)],
        "likely_group": np.asarray(profiles.groups)[posterior.argmax(axis=1)],
    }


def replay(starts: pd.DataFrame, profiles: Profiles, k: float) -> pd.DataFrame:
    """Every start with every contestant's pick for that morning, made from the reads before
    it only: as if the model re-ran every night."""
    gaps = starts.minutes_after_wake.to_numpy()
    weekend = starts.at_weekend.to_numpy()
    likelihood = _likelihood(profiles, gaps, weekend)
    readers = starts.user_key.to_numpy()
    before = pd.DataFrame(likelihood).groupby(readers).cumsum().to_numpy() - likelihood
    rows = on_time(gaps)
    kind = starts.user_key + np.where(weekend, "|weekend", "|weekday")
    own_sum = pd.DataFrame(rows).groupby(kind.to_numpy()).cumsum().to_numpy() - rows
    own_count = starts.groupby(kind).cumcount().to_numpy()
    picks = _choose(profiles, before, own_sum, own_count, weekend, k)
    return starts.assign(reads_before=own_count, **picks)


def score(gaps, picks) -> dict[str, float]:
    """On time (in the half hour before they start), late (after they'd started), or too
    early; and how long the on-time-or-early reminders waited."""
    ahead = np.asarray(gaps) - np.asarray(picks)
    return {
        "on_time": round(float(((ahead > 0) & (ahead <= WINDOW)).mean()), 4),
        "late": round(float((ahead <= 0).mean()), 4),
        "too_early": round(float((ahead > WINDOW).mean()), 4),
        "median_wait": round(float(np.median(ahead[ahead > 0])), 1),
    }


def tune(starts: pd.DataFrame, groups: pd.Series) -> tuple[float, pd.DataFrame]:
    """Pick k on the last learning weeks: profiles from before them, replayed across them."""
    tune_from = TEST_FROM - timedelta(days=TUNE_DAYS)
    profiles = learn_profiles(starts, groups, tune_from)
    inside = (
        (starts.local_day >= tune_from)
        & (starts.local_day < TEST_FROM)
        & (starts.source == LEARN_FROM)
    ).to_numpy()
    rows = []
    for k in KS:
        tried = replay(starts, profiles, k)[inside]
        rows.append({"k": k, **score(tried.minutes_after_wake, tried.model)})
    table = pd.DataFrame(rows)
    return float(table.k[table.on_time.idxmax()]), table


# ---- Grading -----------------------------------------------------------------------------


def true_pick(persona: str, weekend: bool, reminders_on: bool) -> int:
    """The best possible pick, from the simulator's own recipe: it opens the reading after a
    gap drawn from a normal curve (never under a minute), ten minutes later if snoozed."""
    mean, spread = simulate.READ_DELAY[persona][1 if weekend else 0]

    def chance_by(minutes):
        started = np.where(minutes >= 1, norm.cdf((minutes - mean) / spread), 0.0)
        if not reminders_on:
            return started
        snoozed = np.where(minutes - 10 >= 1, norm.cdf((minutes - 10 - mean) / spread), 0.0)
        return 0.88 * started + 0.12 * snoozed

    return int(GRID[np.argmax(chance_by(GRID + WINDOW) - chance_by(GRID))])


def attach_truth(replayed: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    graded = replayed.join(truth, on="user_key", how="inner")
    best = {}
    graded["truth"] = [
        best.setdefault(key, true_pick(*key))
        for key in zip(graded.persona, graded.at_weekend, graded.reminders_on)
    ]
    return graded


def leaderboard(graded: pd.DataFrame) -> pd.DataFrame:
    """Every contestant on the held-out weeks, with how much of the gap from today's rule to
    the truth it closed."""
    board = pd.DataFrame(
        [
            {"contestant": CONTESTANTS[name], **score(graded.minutes_after_wake, graded[name])}
            for name in CONTESTANTS
        ]
    )
    wake, best = board.on_time.iloc[0], board.on_time.iloc[-1]
    board["gap_closed"] = ((board.on_time - wake) / (best - wake)).round(3)
    return board


# ---- Tonight's times ---------------------------------------------------------------------


def clock(minute: float) -> str:
    minute = int(round(minute)) % 1440
    return f"{minute // 60:02d}:{minute % 60:02d}"


def tonight(
    starts: pd.DataFrame, readers: pd.DataFrame, profiles: Profiles, k: float
) -> pd.DataFrame:
    """Every reader's reminder times from all their reads so far, on weekdays and weekends."""
    gaps = starts.minutes_after_wake.to_numpy()
    weekend = starts.at_weekend.to_numpy()
    likelihood = (
        pd.DataFrame(_likelihood(profiles, gaps, weekend)).groupby(starts.user_key.to_numpy()).sum()
    )
    rows = (
        pd.DataFrame(on_time(gaps))
        .groupby([starts.user_key.to_numpy(), weekend])
        .agg(["sum", "count"])
    )
    out = readers.copy()
    for day, name in ((False, "weekday"), (True, "weekend")):
        keys = pd.MultiIndex.from_arrays([out.user_key, np.full(len(out), day)])
        sums = rows.xs("sum", axis=1, level=1).reindex(keys).fillna(0).to_numpy()
        counts = rows.xs("count", axis=1, level=1).iloc[:, 0].reindex(keys).fillna(0).to_numpy()
        totals = likelihood.reindex(out.user_key).fillna(0).to_numpy()
        picks = _choose(profiles, totals, sums, counts, np.full(len(out), day), k)
        out[f"{name}_gap"] = picks["model"]
        out[f"{name}_reminder"] = [clock(w + g) for w, g in zip(out.wake_minute, picks["model"])]
        out["likely_group"] = picks["likely_group"]
    out["reads"] = out.user_key.map(starts.user_key.value_counts()).fillna(0).astype(int)
    out.loc[out.reads == 0, "likely_group"] = None
    return out


def times_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    return Table(
        TABLE,
        metadata,
        Column("user_key", Text, primary_key=True),
        Column("source", Text, nullable=False),
        Column("weekday_reminder", Text, nullable=False),
        Column("weekend_reminder", Text, nullable=False),
        Column("weekday_minutes_after_wake", Integer, nullable=False),
        Column("weekend_minutes_after_wake", Integer, nullable=False),
        Column("likely_group", Integer),
        Column("reads", Integer, nullable=False),
        Column("computed_at", DateTime(timezone=True), nullable=False),
        schema=schema,
    )


def save(engine, times: pd.DataFrame, schema: str | None = SCHEMA) -> None:
    """Replace every reader's times in one transaction: all of them land, or none do."""
    rows = pd.DataFrame(
        {
            "user_key": times.user_key,
            "source": times.source,
            "weekday_reminder": times.weekday_reminder,
            "weekend_reminder": times.weekend_reminder,
            "weekday_minutes_after_wake": times.weekday_gap.astype(int),
            "weekend_minutes_after_wake": times.weekend_gap.astype(int),
            "likely_group": times.likely_group.astype("Int64")
            .astype(object)
            .where(times.likely_group.notna(), None),
            "reads": times.reads.astype(int),
            "computed_at": datetime.now(UTC),
        }
    ).to_dict("records")
    metadata = MetaData()
    table = times_table(metadata, schema)
    with engine.begin() as connection:
        if schema:
            connection.execute(text(f"create schema if not exists {schema}"))
        metadata.create_all(connection)
        connection.execute(table.delete())
        connection.execute(table.insert(), rows)


# ---- The whole run -----------------------------------------------------------------------


@dataclass
class Result:
    k: float
    tuning: pd.DataFrame  # the model's on-time share on the tuning weeks, for each k
    graded: pd.DataFrame  # every held-out start, with each contestant's pick and the truth's
    board: pd.DataFrame
    times: pd.DataFrame  # tonight's times, for every reader
    learned_from: int  # starts before TEST_FROM


def run(engine) -> Result:
    starts = load_starts(engine)
    groups = load_groups(engine)
    k, tuning = tune(starts, groups)
    profiles = learn_profiles(starts, groups, TEST_FROM)
    replayed = replay(starts, profiles, k)
    held_out = replayed[(replayed.local_day >= TEST_FROM) & (replayed.source == LEARN_FROM)]
    graded = attach_truth(held_out, load_truth(engine))
    # Tonight's times learn from everything up to the last day
    everything = learn_profiles(starts, groups, date.max)
    times = tonight(starts, load_readers(engine), everything, k)
    learned = int(((starts.local_day < TEST_FROM) & (starts.source == LEARN_FROM)).sum())
    return Result(k, tuning, graded, leaderboard(graded), times, learned)


def summary(result: Result) -> pd.DataFrame:
    """The record: the leaderboard, the tuned k, and how many held-out starts it's graded on."""
    board = result.board.copy()
    board["k"] = "infinite" if np.isinf(result.k) else f"{result.k:g}"
    board["graded_starts"] = len(result.graded)
    return board


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    result = run(engine)
    print(
        f"Learned from {result.learned_from:,} reading starts before {TEST_FROM}; graded on "
        f"{len(result.graded):,} held-out ones, replayed night by night"
    )
    trust = "fully: their own reads add nothing" if np.isinf(result.k) else f"k = {result.k:g}"
    print(
        f"How much to trust the group over a reader's own reads, tuned on the "
        f"{TUNE_DAYS} days before: {trust}\n"
    )
    shown = result.board.assign(
        **{
            c: (result.board[c] * 100).map("{:.1f}%".format)
            for c in ("on_time", "late", "too_early")
        },
        median_wait=result.board.median_wait.map("{:.0f} min".format),
        gap_closed=(result.board.gap_closed * 100).map("{:.0f}%".format),
    )
    print(shown.to_string(index=False))
    pretend = result.times[result.times.source == LEARN_FROM]
    print("\nTonight's typical reminder, minutes after waking, by likely group:")
    for group, mine in pretend.dropna(subset=["likely_group"]).groupby("likely_group"):
        print(
            f"  Group {int(group)}: weekdays +{mine.weekday_gap.median():.0f}, "
            f"weekends +{mine.weekend_gap.median():.0f} ({len(mine):,} readers)"
        )
    out = Path(__file__).with_name("results") / "reminder_time.csv"
    summary(result).to_csv(out, index=False, lineterminator="\n")
    save(engine, result.times)
    print(
        f"\nThe record: {out.relative_to(Path(__file__).resolve().parents[1])}; "
        f"every reader's times: {SCHEMA}.{TABLE}"
    )
