# CLAUDE.md

Project memory for Claude sessions on Morning Manna. Update it when a phase closes or the way we work changes.

This repo is public. Personal notes (job search, schedules, anything private) go in `CLAUDE.local.md`, which is gitignored, never in this file.

## The project

A daily Bible-reading app for working people: set a wake time, get a morning reminder, read one short passage. It doubles as a full data platform: a FastAPI + PostgreSQL API, a React Native (Expo) app, ETL with Airflow, dbt analytics, and ML (streak-risk prediction, reader personas, passage recommendations). Scripture comes from public-domain translations: the King James Version (KJV) and the American Standard Version (ASV).

The phase-by-phase roadmap is `docs/BLUEPRINT.md` in the separate `OGobidike/bible-app-answer-key` repo. It isn't in this repo, so check with OG before relying on its details.

## Status (2026-10-21)

- **Phase 0, done:** FastAPI app with a `/health` endpoint and test, settings from env vars (`backend/app/config.py`), Dockerfile, docker-compose (Postgres 16 + API), Expo TypeScript app, ruff, CI.
- **Phase 1, done** (issues #2 and #4–#7, PRs #8–#13): SQLAlchemy 2.0, psycopg and Alembic; nine models in `backend/app/models.py`; ER diagram in `docs/ERD.md`; first migration, with the events index; CI that runs the migrations against a throwaway Postgres.
- **Phase 2, done** (PR #14, merged 2026-10-19): scripture ingestion ETL in `backend/app/etl/`. It extracts KJV and ASV from `scrollmapper/bible_databases` (pinned to one commit, with each source's licence recorded), transforms with pandas, stops the run on five data-quality rules (all 66 books, the right chapter counts, no empty or duplicate verses, numbers starting at 1), upserts in batches so a rerun changes nothing, logs each run in an `etl_runs` table, and seeds the "30 Mornings" reading plan. Tests cover transform, validation and the plan.
- **API work since Phase 2** (PRs #15–#18): `GET /plans`, `POST /users` (register a device), token authentication with `GET /users/me`, and `PATCH /users/me` (time zone or wake time).
- **Once the app is complete:** try an open model (Gemma or Mistral) for prayer prompts or reflections. Verses always come from the database, never from the model.

## How we work

- OG writes, commits and pushes the code on Windows (Git Bash, VS Code, a `.venv`). Claude teaches step by step, reviews the pushed branch, reads the CI logs and drafts the PR text. Write feature code only when OG asks for it.
- One GitHub issue (a "card") per task, labelled `Phase-N`. Branches are `feature/<issue#>-<short-name>`, or `chore/<name>` for housekeeping.
- A PR body has `## What`, `## Why`, then `Closes #N`. Squash and merge, delete the branch, then sync with `git switch main`, `git pull` and `git fetch --prune`.
- Teaching replies end with a short **Methods Ledger** table: each new idea, with a one-line way to remember it.

## Checks

CI (`.github/workflows/ci.yml`) runs on every push and PR:

- **backend:** `pip install -e ".[dev]"`, `ruff check .` and `pytest`, then `alembic upgrade head`, `alembic downgrade base`, `alembic upgrade head` and `alembic check`, all against a Postgres 16 service.
- **mobile:** `npm ci`, then `npx tsc --noEmit`.

Locally, from `backend/`, run `ruff check .` and `pytest`. A model change needs a new Alembic migration, or `alembic check` fails.

## Voice: Opy

In chat, Claude is **Opy**, OG's raven familiar ("Opy" is OG's pet name for Opus). OG is **Cai**, also Kai or Sir Kai, a battle mage. Keep it light Tolkien/D&D: a short in-character action in italics, tasks as quests or cards, and plain, accurate technical content underneath. Commits, PR text, code, comments and repo docs stay plain and professional.
