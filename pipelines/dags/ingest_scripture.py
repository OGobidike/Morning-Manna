

"""On demand: load the Bible translations into the app's database.

It runs the Phase 2 pipeline (backend/app/etl): download KJV and ASV (only once), clean and
check every verse, then load them all in one transaction, and log the run in etl_runs.
Running it again is safe: rows already there are updated, never doubled.
"""

from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# Each job's own Python, built into the image by pipelines/Dockerfile
VENVS = "/home/airflow/venvs"

with DAG(
    dag_id="ingest_scripture",
    description="Download, check and load the Bible translations (Phase 2's ETL)",
    schedule=None,  # only when triggered by hand
    start_date=datetime(2026, 10, 1),
    catchup=False,
    default_args={"owner": "kai"},
    tags=["scripture", "etl"],
    doc_md=__doc__,
):
    BashOperator(
        task_id="run_etl",
        bash_command=f"{VENVS}/backend/bin/python -m app.etl",
    )
