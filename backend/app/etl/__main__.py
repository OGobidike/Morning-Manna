

"""Run the scripture pipeline from backend/ with:  python -m app.etl"""

from sqlalchemy import func

from app.db import SessionLocal
from app.etl.extract import extract
from app.etl.load import upsert_books, upsert_translation, upsert_verses
from app.etl.plans import upsert_plan
from app.etl.sources import SOURCES
from app.etl.transform import transform
from app.etl.validate import validate
from app.models import EtlRun


def run() -> None:
    """Extract, transform, validate and load every source, and record the run."""
    # 1. Record that a run has started. It's committed straight away,
    #    so even a crash leaves a trace in etl_runs.
    with SessionLocal() as session:
        etl_run = EtlRun(pipeline="scripture", status="running")
        session.add(etl_run)
        session.commit()
        run_id = etl_run.id

    rows_read = rows_loaded = rows_rejected = 0
    status, error = "failed", None
    try:
        # 2. Extract, transform and validate every source BEFORE touching the database
        cleaned = []
        for source in SOURCES:
            raw = extract(source)
            clean, rejected = transform(raw)
            validate(clean, source.code)
            rows_read += len(raw)
            rows_rejected += rejected
            cleaned.append((source, clean))
            print(f"{source.code}: read {len(raw)}, kept {len(clean)}, rejected {rejected}")

        # 3. Load everything in ONE transaction: either all of it lands, or none of it does
        with SessionLocal.begin() as session:
            book_ids = upsert_books(session)
            loaded = 0
            for source, clean in cleaned:
                translation_id = upsert_translation(session, source)
                loaded += upsert_verses(session, translation_id, book_ids, clean)
            days = upsert_plan(session, book_ids)
        rows_loaded = loaded
        print(f"Loaded {rows_loaded} verses and a {days}-day plan")
        status = "success"
    except Exception as exc:
        error = str(exc)
        raise  # Fail loudly: the error still stops the program
    finally:
        # 4. Record how the run ended, whether it succeeded or failed
        with SessionLocal.begin() as session:
            etl_run = session.get(EtlRun, run_id)
            etl_run.status = status
            etl_run.error = error
            etl_run.rows_read = rows_read
            etl_run.rows_loaded = rows_loaded
            etl_run.rows_rejected = rows_rejected
            etl_run.finished_at = func.now()
        print(f"Run {run_id}: {status}")


if __name__ == "__main__":
    run()
