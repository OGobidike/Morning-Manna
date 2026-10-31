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
| `ml/` | `simulate.py`: deterministic synthetic readers; models come in Phase 7 | NumPy |
| `docs/` | `ERD.md` (database schema), screenshots | |

## How data flows

```
mobile app ──POST /events──> backend ──> Postgres (public.events)
                                  └──background task──> SeaweedFS lake (S3, bucket morning-manna-lake)
                                                         events/dt=YYYY-MM-DD/*.jsonl  (filed by UTC arrival day)
ml/simulate.py ──> data/lake/ ──ingest.upload──> same bucket
Airflow daily_events (00:30 UTC): ingest.load_events (yesterday's folder → raw.events) ──> dbt build (→ analytics schema)
```

- The backend's lake write (`app/lake.py`) runs after the response and never fails the request; `LAKE_URL=""` disables it.
- `load_events` replaces a whole day in one transaction (idempotent), rejects and counts bad lines, and logs runs in `raw.load_runs`.
- The scripture ETL (`python -m app.etl`) downloads KJV/ASV into `data/raw/`, validates (66 books, chapter counts, no dupes), upserts in one transaction, and logs to `etl_runs`. Re-running changes nothing.
- dbt `stg_users` unions synthetic readers (`raw.readers`) with real app users (as `app:<id>`).

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

Local services (from repo root): `docker compose up -d db lake` (Postgres on 5432, S3 on 8333). Airflow: `docker compose up -d --build airflow` (UI on 127.0.0.1:8080).

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

`pytest`. Run `python ml/simulate.py --end 2026-10-27` (from the root) for reproducible data. Seed 7 with that end date yields exactly 5,000 readers and 166,154 events; CI and the analytics README numbers depend on this, so changing the simulator changes them.

### Mobile (`cd mobile`)

`npm ci`, `npx tsc --noEmit` (the only CI check), `npx expo start`. **Read `mobile/AGENTS.md` first**: Expo APIs change every SDK, so check versioned docs instead of relying on memory. Use `npx expo install <pkg>`, never `npm install <pkg>`. Never hand-edit `ios/`/`android/`. The app needs a development build (not Expo Go) because of `expo-notifications`.

## Testing conventions

- Backend tests run against a **real Postgres**. The `db` fixture (`backend/tests/conftest.py`) wraps each test in a transaction rolled back afterwards (commits become savepoints). `client` overrides `get_db` with it.
- Autouse fixtures reset the rate limiter and force `settings.lake_url = ""`, so tests never write to the real lake. Lake tests use their own moto lake.
- The `world` fixture is a tiny Bible ("Testbook") and a two-day plan. Use it instead of loading real scripture.

## Conventions

- ruff, line length 100, rules `E, W, F, I`. Alembic versions are exempt from E501/I001. A project hook (`.claude/settings.json`) formats and lints each edited `.py` file, and runs backend pytest on Stop.
- Airflow mounts the repo read-only at `/opt/manna` (only `data/` is writable). Each job has its own venv in the image, so a new dependency means rebuilding: `docker compose up -d --build airflow`.
- Commit messages follow the "Card X.Y" project-card pattern seen in `git log`.
