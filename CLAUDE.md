# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Morning Manna: a daily Bible-reading app (one short passage each morning, in the reader's own time zone, with streaks) built as a full data platform. It is a monorepo of independent packages, each with its own `pyproject.toml`/`package.json`, its own tests, and its own CI job. Every folder has a detailed README; read the relevant one before changing that area.

| Folder | What | Stack |
|---|---|---|
| `backend/` | The API (Python package `app`) | FastAPI, SQLAlchemy 2, Alembic, Postgres 16, pandas |
| `mobile/` | Android app | Expo SDK 57, React Native, TypeScript, Expo Router |
| `pipelines/` | Lake → warehouse loader (package `ingest`) and Airflow DAGs | boto3, psycopg 3, Airflow 3.3 |
| `analytics/` | dbt models (staging → intermediate → marts) | dbt-core 1.12, dbt-postgres |
| `ml/` | `simulate.py`: deterministic synthetic readers; `streak_risk.py`: the streak-at-risk models; `model_registry.py`: MLflow tracking and the registry (Phase 7) | NumPy, scikit-learn, XGBoost (`xgboost-cpu`), LightGBM, MLflow |
| `docs/` | `ERD.md` (database schema), screenshots | |

## How data flows

```
mobile app ──POST /events──> backend ──> Postgres (public.events)
                                  └──background task──> SeaweedFS lake (S3, bucket morning-manna-lake)
                                                         events/dt=YYYY-MM-DD/*.jsonl  (filed by UTC arrival day)
ml/simulate.py ──> data/lake/ ──ingest.upload──> same bucket
          └──> data/answer_key/  (true daily finish chances: never loaded, only for grading models)
Airflow daily_events (00:30 UTC): ingest.load_events (yesterday's folder → raw.events) ──> dbt build (→ analytics schema) ──> score_tonight (→ ml.streak_risk_scores)
Airflow retrain_models (Sundays 02:00 UTC): ml/model_registry.py ──> MLflow server (records in mlflow-db, models in the lake's mlflow-artifacts bucket) ──> @champion, if better
                                                                     ml service (port 8001) and score_tonight read @champion from it
```

- The backend's lake write (`app/lake.py`) runs after the response and never fails the request; `LAKE_URL=""` disables it.
- `load_events` replaces a whole day in one transaction (idempotent), rejects and counts bad lines, and logs runs in `raw.load_runs`.
- The scripture ETL (`python -m app.etl`) downloads KJV/ASV into `data/raw/`, validates (66 books, chapter counts, no dupes), upserts in one transaction, and logs to `etl_runs`. Re-running changes nothing.
- Each reader source has its own last day of data (`int_last_day`): every "has this reader had day N yet" or "still going" check joins it by `source`, never a single global `max(local_day)`, so real app readings can't stretch the synthetic readers' calendar.
- dbt `stg_users` unions synthetic readers (`raw.readers`) with real app users (as `app:<id>`), each with their `reminder_variant`. `fct_experiment` holds one row per reader in the reminder A/B test (docs/analysis/reminder-experiment.md).
- `analytics/experiments/` analyses that test (`analyze.py`), drills it (`drill.py`, record in `drill_runs.csv`) and draws it (`charts.py`, shown by notebook 02), and exports it for Tableau Public (`tableau.py` → `analytics/tableau/*.csv`: pretend readers and counts only; CI fails if the committed files are stale). Group A is green `#008300` and group B magenta `#e87ba4`, never the dashboard's persona colours.
- `fct_reader_habits` (Card 7.6) is behaviour only: never add `persona` to it. `ml/personas.py` clusters it with K-means (k by silhouette on the learning half; halves by an md5 of `user_key`) and grades against `dim_users.persona`, the answer key, only in `grade()`/`load_truth()`. It writes `ml/results/personas.csv` (committed) and `ml.reader_personas`.
- `fct_reader_starts` (Card 7.7) is behaviour only too: never add `persona` to it. `ml/reminder_time.py` needs `ml.reader_personas` (run `ml/personas.py` first), learns from pretend readers only, tunes k on the 21 days before `TEST_FROM`, and grades by replaying the held-out weeks night by night (each pick uses only earlier reads). Only `load_truth()`, `true_pick()` and `attach_truth()` may touch the persona (a test checks). It writes `ml/results/reminder_time.csv` (committed) and `ml.reminder_times`.
- `ml/verse_embeddings.py` (Card 8.1, `nlp` extra: FastEmbed on ONNX, never PyTorch) embeds every verse with `bge-small-en-v1.5` into `ml.verse_embeddings` (pgvector, HNSW cosine index), only the verses not yet embedded with `MODEL`; a different model's vectors are deleted, never mixed. Psalms' verse-1 headings are stripped for the vectors only (`without_heading`); never change `verses.text`. Postgres must have pgvector: docker compose and CI use `pgvector/pgvector:pg16`. Tests use a stand-in encoder (never download the model in CI); storage tests need the db and fail in CI without it. It writes `ml/results/verse_embeddings.csv` (committed, whole percents).
- `ml/search.py` (Card 8.2) grades search against `ml/data/search_questions.csv`, 30 questions with their passages, written and frozen before any search ran: never edit it after seeing results (a test checks its md5). Methods were fixed beforehand (BGE's query prefix, RRF k=60, keyword any-word); don't tune them on these questions. BGE meaning search won (hybrid didn't help), so `search()` and `GET /search` in `ml/serve.py` default to `meaning`, through the HNSW index. `by_index` must never return fewer than asked: the index filters by translation after gathering candidates, so it raises `hnsw.ef_search` and falls back to an exact scan. It writes `ml/results/search.csv` (whole percents) and `search_by_question.csv` (charts read it); CI can't rerun it (needs the models).
- `ml/topics.py` (Card 8.3) tags verses with 30 topics (`ml/data/topic_tags.csv`), graded against Nave's Topical Bible (`ml/data/topic_key.csv`, built by `--build-key` from the BibleData CSV, CC BY 4.0, md5-checked in `data/raw/`). Both files were frozen before any tagger ran: never edit them after seeing results (a test checks both md5s). Mapping rules: teaching headings only, refs on the heading's own line, >=20 verses a tag. Grading holds out whole books in 3 groups (md5 of the book name); never score a verse with a tagger trained on its book. The winner by average precision (the trained logistic regression on BGE vectors) writes `ml.verse_topics` (each tag's best 500 verses, each verse's best 3 tags; the ASV by reference) and `GET /topics/{tag}` serves it. Records: `ml/results/topics.csv` and `topics_by_tag.csv`, both whole percents (Kai's CPU moved the 4th decimal of average precision; a record compared by md5 on his machine never holds raw continuous measures).
- `ml/recommend.py` (Card 8.4) builds "because you read" shelves: 10 verses, one per chapter, never the chapter just read. The answer key is OpenBible.info's cross-references (CC BY, `data/raw/cross_references.txt`, md5-checked; links with >=10 votes, direction kept, the reader's own chapter removed). The rules were frozen before any recommender ran; rule 14 (blend weights by unrounded recall) was amended in writing before its results were seen, and the write-up reports both. Five recommenders race on 8.3's held-out book groups (popular, words = TF-IDF, meaning = BGE, topics = 8.3's tag chances, blend = standardised weighted sum in tenths); only popular's counts and the blend's weights learn from the key, and only from the other groups. The winner (by recall@10) writes `ml.verse_shelves` (every KJV verse's 20 best, by reference, so it serves the ASV too); a passage sums its verses' shelf scores (graded against rank fusion and a whole-passage query). "Readers like you" (`readers_like_you`) stays off until `collab_status` counts 200 readers who each chose 5 chapters themselves: plan readings never count. Records (`ml/results/shelves*.csv`) are whole percents and counts. Under a noise test (vectors nudged by 1e-5) the section numbers for meaning and topics moved, so that record keeps only the winner and words; and group 0's blend weights sit 0.04 points from a neighbour and flipped in 1 run of 4, so another machine's records are checked within 1 point (same winner, same served pooler), not by md5.
- `int_reader_nights` (Card 7.5) computes the streak-at-risk features once; `fct_reader_nights` (labelled nights, for training) and `fct_reader_tonight` (each reader's last night, unlabelled, for scoring) both select from it. Change features there, never in the marts. `ml/score_tonight.py` scores tonight into `ml.streak_risk_scores` (delete-then-insert per night, in one transaction), nudging anyone at or above a cut-off set from the held-out nights, never a per-night quota.
- `fct_reader_nights` (Card 7) is the streak-at-risk model's table: features use only that night and earlier (windows end at the current row); `missed_tomorrow` is the label. `reader_nights_never_peek` guards against leakage. Models are graded against `data/answer_key/`, which must never be loaded into the warehouse or used as a feature.

## Backend invariants (don't break these)

- **Progress, not the calendar:** `/today` serves `user_plans.current_day` (next unread day), never a date-derived day. Logic lives in `app/progress.py`.
- **Reader's time zone everywhere:** "today", plan start dates and streak days use `app/clock.py` (`local_today`), not server time. Pass `now` for testability.
- **Tokens:** only SHA-256 hashes are stored (`app/security.py`, `app/auth.py`). The raw token is returned once at signup.
- **Other readers' data returns 404**, identical to "not found".
- **Completing a reading is idempotent**, and an old reading can't skip a day.
- **Event batches are all-or-nothing:** 1–100 events, known types, tz-aware, not in the future; the 422 names the bad event.
- **Streaks** use the gaps-and-islands trick (`day - row_number()`), in both `app/streaks.py` and dbt `fct_streaks`.
- Logs never include headers or query strings (tokens).
- The signup rate limiter (`app/ratelimit.py`) is in-memory, per process.

## Commands

Local services (from repo root): `docker compose up -d db lake` (Postgres on 5432, S3 on 8333). Everything: `docker compose up -d --build` (Airflow on 127.0.0.1:8080, MLflow on 127.0.0.1:5000, the ML service on 127.0.0.1:8001; Card 9). Airflow, MLflow and the ML service share one image (`pipelines/Dockerfile`, ~3.6 GB); the models' venv also runs the MLflow server, whose `tracking-server` extra is the only place boto3 is declared (clients reach MLflow over HTTP). After a first start, trigger `retrain_models` once to crown a champion. The MLflow server's job workers are off (`MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false`: they cost ~1.5 GB), and the lake runs with `-volume.max=100` (SeaweedFS's default 8 volumes can't hold a second bucket; a full limit or disk shows as S3 "InternalError").

### Backend (`cd backend`)

The README and CI use pip (`pip install -e ".[dev]"`). Locally, uv is in use; dev tools (pytest-cov, httpx, moto) are in the `dev` **extra**, so include it:

```bash
uv sync --extra dev
cp .env.example .env
uv run alembic upgrade head
uv run python -m app.etl                      # load Bible + 30-day plan
uv run uvicorn app.main:app --reload          # http://localhost:8000/docs
uv run ruff check .
uv run pytest --cov                           # needs `docker compose up -d db`; fails under 80% coverage
uv run pytest tests/test_streak.py::test_name -q   # single test
uv run alembic revision --autogenerate -m "..."    # new migration
uv run alembic check                          # models and migrations agree (CI runs this)
```

CI also runs `alembic downgrade base` then `upgrade head`, so every migration needs a working downgrade.

### Pipelines (`cd pipelines`)

```bash
pip install -e ".[dev]"   # installed into the backend's venv
pytest                    # needs db; uses moto for S3 and a fresh schema per test
python -m ingest.upload && python -m ingest.load_events --all   # or --date YYYY-MM-DD
```

DAG tests need Airflow, so run them in the container:
`docker compose exec airflow bash -c "pip install -q pytest && python -m pytest -p no:cacheprovider /opt/manna/pipelines/dag_tests"`

### Analytics (`cd analytics`, own venv from `requirements.txt`)

`dbt build` (models plus tests, layer by layer), `dbt build --select fct_streaks`, `dbt docs serve --port 8081`. `profiles.yml` is in this folder; `DBT_*` env vars override the target.

### ML (`cd ml`)

`pytest`. Run `python ml/simulate.py --end 2026-10-27` (from the root) for reproducible data. Seed 7 with that end date yields exactly 5,000 readers and 179,077 events; CI and the analytics README numbers depend on this, so changing the simulator changes them. Each reader gets reminder wording A or B; `WORDING_B_LIFT` is the planted effect, the practice run's answer key: the Card 6.4 analysis must never read it, and is compared with it only once the analysis is done.

The models need the `models` extra: `pip install -e ".[dev,models]"` (it is `xgboost-cpu`, not `xgboost`, which would pull ~290 MB of unused GPU libraries; ask before adding heavy packages). On Linux, LightGBM also needs the system package `libgomp1` (minimal Ubuntu and WSL lack it; CI's runner has it). `ml/serve.py` (Card 7.4, `serving` extra) serves `@champion` with FastAPI on port 8001, separate from `backend/` so the app never carries the model libraries: `uvicorn --app-dir ml serve:app --port 8001`, or the `ml` compose service. It re-checks the registry for a new `@champion` at most every `RECHECK_SECONDS` (600) and keeps serving the old one if the registry is unreachable. Its `Night` schema speaks domain terms (`reminder_variant`), and `as_features()` must build exactly `streak_risk.FEATURES` with the training dtypes; a test checks the API matches offline predictions exactly. `python ml/model_registry.py` (needs the `tracking` extra, full `mlflow`; skinny can't use a local store) logs every race to MLflow (SQLite in `ml/mlruns/`, git-ignored; `MLFLOW_TRACKING_URI` overrides, as compose sets it to the MLflow server). It uses `data/answer_key/` only if present (then the truth row and charts); without it, it grades on what happened and registers the best model; it takes `@champion` only if it strictly beats the re-scored champion on the same held-out nights. Models are saved with skops, so a new model class needs its types added to `TRUSTED`; telemetry is switched off in code. `python ml/streak_risk.py` (from the root, after `dbt build`) trains and grades the streak-at-risk models holding out the latest `TEST_DAYS` (21) nights (`held_out_from`: 2026-10-06 on the practice data, so the committed record is unchanged) with time-ordered tuning folds; never shuffle nights across time. It writes `ml/results/streak_risk.csv`, which is committed; `ml/charts/` is not.

### Mobile (`cd mobile`)

`npm ci`, `npx tsc --noEmit` (the only CI check), `npx expo start`. **Read `mobile/AGENTS.md` first**: Expo APIs change every SDK, so check versioned docs instead of relying on memory. Use `npx expo install <pkg>`, never `npm install <pkg>`. Never hand-edit `ios/`/`android/`. The app needs a development build (not Expo Go) because of `expo-notifications`.

## Testing conventions

- Backend tests run against a **real Postgres**. The `db` fixture (`backend/tests/conftest.py`) wraps each test in a transaction rolled back afterwards (commits become savepoints). `client` overrides `get_db` with it.
- Autouse fixtures reset the rate limiter and force `settings.lake_url = ""`, so tests never write to the real lake. Lake tests use their own moto lake.
- The `world` fixture is a tiny Bible ("Testbook") and a two-day plan. Use it instead of loading real scripture.

## Conventions

- ruff, line length 100, rules `E, W, F, I`. Alembic versions are exempt from E501/I001. A project hook (`.claude/settings.json`) formats and lints each edited `.py` file, and runs backend pytest on Stop.
- Airflow mounts the repo read-only at `/opt/manna` (only `data/` is writable). Each job has its own venv in the image (`backend`, `pipelines`, `dbt`, `ml`), so a new dependency means rebuilding: `docker compose up -d --build`.
- Commit messages follow the "Card X.Y" project-card pattern seen in `git log`.
