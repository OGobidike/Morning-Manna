# Morning Manna analytics

The dbt project that turns raw events into the answers that matter most for a daily reading app: who comes back, and who keeps reading.

dbt-core 1.12 · dbt-postgres 1.11 · PostgreSQL 16

## The answers so far

From the pretend readers ([ml/simulate.py](../ml/simulate.py): 5,000 readers, the 90 days to 27 October 2026, seed 7). These are practice data, not real people.

| Measure | Value |
|---|---|
| Came back on day 1 | 46.7% |
| Came back on day 7 | 37.6% |
| Came back on day 30 | 21.2% |
| Median streak | 2 mornings |
| Longest streak | 35 mornings |
| Signed up but never read | 969 of 5,000 |

## How the tables are built

```
raw.events, raw.readers, public.users        (the loader and the app)
        │
        ▼  staging: tidy names and types (views)
stg_events, stg_users
        │
        ▼  intermediate: one row per reader per day (table)
int_daily_reading
        │
        ▼  marts: the answers (tables)
fct_streaks, fct_retention_cohorts, dim_users
```

| Model | One row per | What it holds |
|---|---|---|
| `stg_events` | event | The lake's events, cleaned up |
| `stg_users` | reader | Pretend readers and the app's real users together (as `app:<id>`), with the day each signed up in their own time zone |
| `int_daily_reading` | reader per day | From signup to the last day of data: did they read, did they open the app, how many events |
| `fct_streaks` | streak | Each unbroken run of mornings read: start, end, length, and whether it's still going |
| `fct_retention_cohorts` | signup week | How many came back on day 1, 7 and 30, and the rates |
| `dim_users` | reader | Longest and current streak, active in the last 7 days, never read |

## Decisions

- **The reader's own day.** A morning counts in the reader's own time zone, not the server's. 05:30 in Lagos and 05:30 in Manila are both "this morning".
- **Every reader counts, including those who never came back.** `int_daily_reading` has a row for every day since signup, read or not. Readers who signed up and never read stay in the totals, so retention is never flattered.
- **Only readers who've had time.** Someone who joined yesterday can't have a day 7 yet, so they don't count against day 7 until they've had one.
- **Streaks with gaps and islands.** `day - row_number()` is the same for every day in an unbroken run, so grouping by it finds each streak in one pass.
- **Build, then test, layer by layer.** `dbt build` tests each model before building what depends on it, so a model that fails its tests never feeds the tables after it.

## Run it

dbt has its own venv. You need the warehouse loaded first (see [pipelines/README.md](../pipelines/README.md#the-loader)).

```bash
docker compose up -d db
cd analytics
python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt
dbt build                          # every model, then its tests
```

dbt finds `profiles.yml` in this folder. It builds into the `analytics` schema of the local docker database, and the `DBT_*` environment variables can point it elsewhere.

Read the answers:

```bash
docker compose exec db psql -U manna -c "select cohort_week, readers, day_1_rate, day_7_rate, day_30_rate from analytics.fct_retention_cohorts order by cohort_week"
```

See every model, column and test, with a lineage graph, in your browser (port 8081, because Airflow uses 8080):

```bash
dbt docs generate
dbt docs serve --port 8081
```

Airflow runs `dbt build` every night after the loader, so the tables are fresh each morning.

## Tests

25 data tests: keys that are unique and never empty, events that belong to a known reader, allowed values only, and three custom checks in [tests/](tests/):

- `one_row_per_reader_per_day`: no reader has the same day twice.
- `streaks_add_up`: each streak's length matches its dates, and all the streaks together add up to every morning read.
- `retention_rates_make_sense`: no more readers returned than were eligible, and every rate is between 0 and 1.

The **analytics** job in CI builds the warehouse from nothing on every push:

1. The app's tables (migrations).
2. The pretend readers.
3. A stand-in S3 lake.
4. The loader.
5. `dbt build`.

It then prints the day 1, 7 and 30 retention in the log.
