

# Backend: t# Morning Manna API

The FastAPI backend for Morning Manna: a reader signs up with their phone, starts a reading plan, gets one short passage each morning in their own time zone, marks it read, and builds a streak.

Python 3.11+ · FastAPI · PostgreSQL 16 · SQLAlchemy 2 · Alembic · pandas · pytest

## The morning loop

1. **Sign up** with a device id, time zone and wake time. The API returns a secret token, once.
2. **Start a plan**, such as *30 Mornings*: thirty short passages from the Psalms, the Gospels and the prophets.
3. **Read today's passage**. It's always the next unread day of the plan, so a missed morning is picked up, never skipped.
4. **Mark it read**. That moves the reader to the next day and extends their streak.

## Quick start

You need Docker and Python 3.11 or newer (CI uses 3.12). From the repo root:

```bash
docker compose up -d db            # Postgres 16 on localhost:5432
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head               # create the tables
python -m app.etl                  # load the Bible and the 30-day plan
uvicorn app.main:app --reload
```

The API is now at http://localhost:8000. Interactive docs are at http://localhost:8000/docs.

`python -m app.etl` downloads the King James Version and the American Standard Version (both public domain) into `data/raw/` the first time. It then loads 66 books, 62,188 verses and the *30 Mornings* plan. Running it again changes nothing.

## Try it

Each command is copy-and-paste in bash. The token is saved in `$TOKEN` and the reading id in `$READING`.

```bash
# Sign up and keep the token (it is shown only once)
TOKEN=$(curl -s -X POST localhost:8000/users -H "Content-Type: application/json" \
  -d '{"device_id": "readme-demo-phone", "timezone": "Africa/Lagos", "wake_time": "06:00"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['token'])")

# Start the 30-day plan
curl -s -X POST localhost:8000/users/me/plans -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"plan_id": 1}'
# {"id":1,"plan_id":1,"start_date":"2026-10-23","current_day":1}

# This morning's passage
curl -s localhost:8000/today -H "Authorization: Bearer $TOKEN"
# {"plan_name":"30 Mornings","day_number":1,"total_days":30,"completed":false,
#  "reference":"Psalms 1:1-6","verses":[{"chapter":1,"verse":1,"text":"Blessed is the man..."}, ...]}

# Open the reading, then mark it read
READING=$(curl -s -X POST localhost:8000/readings -H "Authorization: Bearer $TOKEN" \
  | python -c "import sys, json; print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/readings/$READING/complete -H "Authorization: Bearer $TOKEN"

# Tomorrow's passage is now waiting, and the streak has started
curl -s localhost:8000/users/me/streak -H "Authorization: Bearer $TOKEN"
# {"current":1,"longest":1,"last_read_on":"2026-10-23"}

# Send app events in a batch
curl -s -X POST localhost:8000/events -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"events": [{"event_type": "app_opened", "occurred_at": "2026-10-23T05:30:00Z"},
                  {"event_type": "reminder_snoozed", "occurred_at": "2026-10-23T05:31:00Z",
                   "properties": {"minutes": 10}}]}'
# {"accepted":2}
```

## Endpoints

Every endpoint except `GET /health`, `GET /plans` and `POST /users` needs `Authorization: Bearer <token>`.

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Liveness check |
| GET | `/plans` | List the reading plans |
| POST | `/users` | Sign up a device and return its token (rate-limited) |
| GET | `/users/me` | The reader's settings |
| PATCH | `/users/me` | Change time zone or wake time |
| POST | `/users/me/plans` | Start a plan |
| GET | `/today` | Today's passage, in the reader's translation |
| POST | `/readings` | Open a reading for the current day |
| POST | `/readings/{id}/complete` | Mark it read and move to the next day |
| GET | `/users/me/streak` | Current and longest streak |
| POST | `/events` | Store a batch of app events |

## Design decisions

- **Progress, not the calendar.** `/today` serves the reader's next unread day (`user_plans.current_day`). A missed morning is resumed, never skipped.
- **Tokens are never stored.** Only a SHA-256 hash of each token is kept, so a database leak gives away no working tokens.
- **Someone else's data looks missing.** Asking for another reader's reading returns the same 404 as a reading that doesn't exist.
- **Safe to retry.** Completing a reading twice, for example when a phone retries on a bad signal, counts once. An old reading can't skip a day.
- **The reader's own time zone.** "Today", plan start dates and streak days all follow the reader's time zone, not the server's.
- **Streaks with gaps and islands.** In SQL, `day - row_number()` is the same for every day in an unbroken run, so grouping by it finds each streak.
- **Events: all or nothing.** A batch is checked before anything is stored: known event types only, times must carry a time zone and can't be in the future, 1 to 100 per batch. One bad event rejects the batch, and the 422 says which one.
- **Sign-ups are rate-limited.** 5 per hour per address, then 429 with `Retry-After`.
- **Structured logs.** One JSON line per request: method, path, status and duration. Headers and query strings are never logged, so tokens can't leak into logs.

## Data pipeline

`python -m app.etl` is a small ETL job:

1. **Extract**: download each translation's CSV once, from a source pinned to one commit.
2. **Transform**: clean the rows with pandas: normalise book names ("II Kings" becomes "2 Kings"), tidy the text, and reject unusable rows.
3. **Validate**: stop loudly if the data breaks a rule: all 66 books present, the right number of chapters in each, no empty or duplicate verses.
4. **Load**: upsert everything in one transaction, so a failed run leaves nothing half-loaded and a repeat run changes nothing.

Each run is recorded in the `etl_runs` table: status, rows read, loaded and rejected, and any error. The database schema is drawn in [docs/ERD.md](../docs/ERD.md).

## Tests and CI

```bash
pytest --cov
```

The suite has 88 tests and runs against a real Postgres database. Each test runs inside a transaction that is rolled back afterwards, so tests never leave data behind. CI fails if coverage drops below 80% (currently about 88%).

On every push, GitHub Actions runs:

1. `ruff check .`
2. Migrations on an empty database
3. The tests with coverage
4. A full migration rollback and re-apply
5. `alembic check`, which confirms the models and migrations agree

## Layout

```
app/
  main.py        the FastAPI app: routers, logging middleware
  routers/       one file per area: users, plans, today, readings, events
  models.py      the database tables (SQLAlchemy)
  schemas.py     request and response shapes (Pydantic)
  auth.py        Bearer-token authentication
  progress.py    which plan and day a reader is on
  streaks.py     streak calculation
  ratelimit.py   sliding-window rate limiter
  logs.py        structured JSON request logs
  etl/           the scripture pipeline
alembic/         database migrations
tests/           pytest suite
```

## Known limits

- The rate limiter keeps its counts in memory, so it applies per server process and resets on restart. Running several servers would need a shared store such as Redis.
- Behind a proxy, every caller shares the proxy's address for rate limiting.
- `app/etl/extract.py` (network downloads) and the pipeline runner aren't covered by tests. The transform, validate and load steps are.
he FastAPI service, database models, migrations, and tests.
