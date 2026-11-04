"""Reader personas (Card 7.6): can K-means find the kinds of reader from their habits alone?

The simulator gives each pretend reader a persona (early riser, commuter, weekend reader),
and the dashboard colours by it. Here the model never sees it. It gets only behaviour, from
the warehouse's fct_reader_habits:

    weekday_minute       when they read on weekdays (330 is 05:30)
    weekend_minute       when they read at weekends
    weekend_share        how much of their reading falls at weekends
    read_minute_spread   how much their reading time wanders

and groups readers who behave alike. The persona is the answer key, read in one place only
(grade), the way the A/B test's planted effect was. To keep that grade honest, the readers
are split in two by a hash of their key: the number of groups and the groups themselves are
chosen on the learning half, and graded once on the checking half, which they never saw.

Run it from the repo root after dbt build (a few seconds):
    python ml/personas.py
It prints the grade, writes ml/results/personas.csv, and saves each reader's group to
ml.reader_personas.
"""

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.preprocessing import StandardScaler
from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, create_engine, text

FEATURES = ["weekday_minute", "weekend_minute", "weekend_share", "read_minute_spread"]
MIN_READS = 5  # fewer, and a reader's habits are mostly noise
KS = range(2, 7)  # the numbers of groups to try
SEED = 7
SCHEMA, TABLE = "ml", "reader_personas"
PERSONA_NAMES = {
    "early_riser": "Early risers",
    "commuter": "Commuters",
    "weekend_reader": "Weekend readers",
}


# ---- The data ----------------------------------------------------------------------------


def load_habits(engine) -> pd.DataFrame:
    """Every reader's habits. Behaviour only: no persona."""
    with engine.connect() as connection:
        habits = pd.read_sql(
            text(
                """
                select user_key, source, reads, weekday_reads, weekend_reads,
                       weekday_minute, weekend_minute, weekend_share, read_minute_spread
                from analytics.fct_reader_habits
                order by user_key
                """
            ),
            connection,
        )
    for column in FEATURES:
        habits[column] = habits[column].astype(float)
    return habits


def load_truth(engine) -> pd.Series:
    """The answer key: each pretend reader's persona. Only grade() and the charts use it."""
    with engine.connect() as connection:
        truth = pd.read_sql(
            text("select user_key, persona from analytics.dim_users where source = 'synthetic'"),
            connection,
        )
    return truth.set_index("user_key").persona


def eligible(habits: pd.DataFrame, min_reads: int = MIN_READS) -> pd.DataFrame:
    """Readers with enough reading to show a habit: a weekday read, a weekend read, and at
    least min_reads days in all."""
    enough = (
        (habits.reads >= min_reads) & (habits.weekday_reads >= 1) & (habits.weekend_reads >= 1)
    )
    return habits[enough].dropna(subset=FEATURES).reset_index(drop=True)


def half(user_key: str) -> int:
    """0 (learning) or 1 (checking): fixed by the key itself, so it never changes run to run."""
    return int(hashlib.md5(user_key.encode()).hexdigest(), 16) % 2


# ---- Finding the groups ------------------------------------------------------------------


@dataclass
class Found:
    scaler: StandardScaler
    model: KMeans
    silhouette: dict[int, float]  # how well separated the groups are, for each number tried

    @property
    def k(self) -> int:
        return self.model.n_clusters


def find(readers: pd.DataFrame, ks=KS) -> Found:
    """Pick the number of groups with the best silhouette, then group the readers.

    Each habit is put on the same scale first (minutes would otherwise drown out shares).
    The groups are numbered by their weekday reading time, earliest first, so group 1 is
    always the earliest readers.
    """
    scaler = StandardScaler().fit(readers[FEATURES])
    X = scaler.transform(readers[FEATURES])
    silhouette = {}
    for k in ks:
        labels = KMeans(k, n_init=10, random_state=SEED).fit_predict(X)
        silhouette[k] = round(float(silhouette_score(X, labels)), 4)
    best = max(silhouette, key=silhouette.get)
    model = KMeans(best, n_init=10, random_state=SEED).fit(X)
    # Renumber the groups by weekday reading time (its centre is in the first column)
    order = np.argsort(model.cluster_centers_[:, 0])
    model.cluster_centers_ = model.cluster_centers_[order]
    return Found(scaler, model, silhouette)


def assign(found: Found, readers: pd.DataFrame) -> np.ndarray:
    """Each reader's group, 1 to k: the nearest group centre."""
    return found.model.predict(found.scaler.transform(readers[FEATURES])) + 1


def clock(minute: float) -> str:
    return f"{int(minute // 60):02d}:{int(minute % 60):02d}"


def describe(found: Found) -> pd.DataFrame:
    """Each group's centre, in plain terms."""
    centres = pd.DataFrame(
        found.scaler.inverse_transform(found.model.cluster_centers_), columns=FEATURES
    )
    centres.insert(0, "group", range(1, found.k + 1))
    centres["label"] = [
        f"{clock(row.weekday_minute)} weekdays, {clock(row.weekend_minute)} weekends, "
        f"{row.weekend_share:.0%} of reads at weekends"
        for row in centres.itertuples()
    ]
    return centres


# ---- Grading -----------------------------------------------------------------------------


def grade(groups: np.ndarray, personas: pd.Series) -> float:
    """Adjusted Rand index: 1 when the groups match the personas exactly (whatever they're
    called), 0 when they match no better than chance."""
    return round(float(adjusted_rand_score(personas, groups)), 4)


def crosstab(groups: np.ndarray, personas: pd.Series) -> pd.DataFrame:
    """For each persona, the share of its readers in each group."""
    table = pd.crosstab(pd.Series(personas.values, name="persona"),
                        pd.Series(groups, name="group"), normalize="index")
    return table.reindex([p for p in PERSONA_NAMES if p in table.index])


def matches(groups: np.ndarray, personas: pd.Series) -> dict[int, str]:
    """Each group's most common persona, for colouring it like the dashboard does."""
    table = pd.crosstab(pd.Series(groups, name="group"), pd.Series(personas.values))
    return {int(group): str(row.idxmax()) for group, row in table.iterrows()}


BANDS = [1, 4, 7, 11, 19, 10_000]
BAND_NAMES = ["2–4", "5–7", "8–11", "12–19", "20+"]


def clarity(habits: pd.DataFrame, truth: pd.Series, found: Found) -> pd.DataFrame:
    """How well the groups match the personas, by how much a reader has read: graded on the
    checking half only, including readers below MIN_READS, to show why the line is there."""
    readers = eligible(habits, min_reads=2)
    readers = readers[readers.source == "synthetic"]
    readers = readers[[half(key) == 1 for key in readers.user_key]]
    groups = assign(found, readers)
    bands = pd.cut(readers.reads, BANDS, labels=BAND_NAMES)
    rows = []
    for name in BAND_NAMES:
        inside = (bands == name).values
        if not inside.any():
            continue
        rows.append(
            {"reads": name, "readers": int(inside.sum()),
             "ari": grade(groups[inside], truth[readers.user_key[inside]])}
        )
    return pd.DataFrame(rows)


# ---- Saving ------------------------------------------------------------------------------


def personas_table(metadata: MetaData, schema: str | None = SCHEMA) -> Table:
    return Table(
        TABLE,
        metadata,
        Column("user_key", Text, primary_key=True),
        Column("source", Text, nullable=False),
        Column("persona_group", Integer, nullable=False),
        Column("group_label", Text, nullable=False),
        Column("reads", Integer, nullable=False),
        Column("grouped_at", DateTime(timezone=True), nullable=False),
        schema=schema,
    )


def save(engine, readers: pd.DataFrame, groups: np.ndarray, found: Found,
         schema: str | None = SCHEMA) -> None:
    """Replace every reader's group in one transaction: all of them land, or none do."""
    labels = describe(found).set_index("group").label
    rows = pd.DataFrame(
        {
            "user_key": readers.user_key,
            "source": readers.source,
            "persona_group": groups.astype(int),
            "group_label": [labels[g] for g in groups],
            "reads": readers.reads.astype(int),
            "grouped_at": datetime.now(UTC),
        }
    ).to_dict("records")
    metadata = MetaData()
    table = personas_table(metadata, schema)
    with engine.begin() as connection:
        if schema:
            connection.execute(text(f"create schema if not exists {schema}"))
        metadata.create_all(connection)
        connection.execute(table.delete())
        connection.execute(table.insert(), rows)


# ---- The whole run -----------------------------------------------------------------------


@dataclass
class Result:
    found: Found
    readers: pd.DataFrame  # every eligible reader, with half and group
    learn_grade: float
    check_grade: float
    coverage: float  # share of pretend readers with enough reading to be grouped


def run(engine) -> Result:
    habits = load_habits(engine)
    readers = eligible(habits)
    readers["half"] = [half(key) for key in readers.user_key]
    learn = readers[(readers.half == 0) & (readers.source == "synthetic")]
    found = find(learn)
    readers["group"] = assign(found, readers)
    truth = load_truth(engine)
    graded = readers[readers.source == "synthetic"]
    learn_part, check_part = graded[graded.half == 0], graded[graded.half == 1]
    return Result(
        found,
        readers,
        grade(learn_part.group.values, truth[learn_part.user_key]),
        grade(check_part.group.values, truth[check_part.user_key]),
        round(len(graded) / (habits.source == "synthetic").sum(), 4),
    )


def summary(result: Result) -> pd.DataFrame:
    """The record: the grade, and each group in plain terms."""
    groups = describe(result.found)
    # The pretend readers only: real ones are grouped and saved too, but the record must come
    # out the same on any warehouse built from the same simulation
    pretend = result.readers[result.readers.source == "synthetic"]
    groups["readers"] = [int((pretend.group == g).sum()) for g in groups.group]
    for column in FEATURES:
        groups[column] = groups[column].round(2)
    groups["k"] = result.found.k
    groups["silhouette"] = result.found.silhouette[result.found.k]
    groups["learn_ari"] = result.learn_grade
    groups["check_ari"] = result.check_grade
    groups["coverage"] = result.coverage
    return groups


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL", "postgresql+psycopg://manna:manna@localhost:5432/manna")
    engine = create_engine(url)
    result = run(engine)
    found = result.found
    print("Silhouette for each number of groups: "
          + ", ".join(f"{k}: {s:.3f}" for k, s in found.silhouette.items()))
    print(f"K-means chose {found.k} groups, from the learning half's habits alone")
    for row in describe(found).itertuples():
        count = int((result.readers.group == row.group).sum())
        print(f"  Group {row.group}: {row.label} ({count:,} readers)")
    print(f"\nGraded against the true personas: ARI {result.check_grade:.3f} on the checking "
          f"half (never seen), {result.learn_grade:.3f} on the learning half")
    print(f"Grouped {result.coverage:.0%} of the pretend readers: the rest read fewer than "
          f"{MIN_READS} days, or never on a weekday or at a weekend")
    out = Path(__file__).with_name("results") / "personas.csv"
    summary(result).to_csv(out, index=False, lineterminator="\n")
    save(engine, result.readers, result.readers.group.values, found)
    print(f"\nThe record: {out.relative_to(Path(__file__).resolve().parents[1])}; "
          f"every reader's group: {SCHEMA}.{TABLE}")
