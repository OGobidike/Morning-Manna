

"""Every night: bring yesterday's events from the lake into the warehouse, then rebuild
the retention tables with dbt.

    load_events  -->  dbt_build

The lake files each event under the day it arrived (in UTC), so by 00:30 UTC yesterday's
folder is complete. Loading a day again replaces it, so re-running any night is safe.
To load a different day, trigger this DAG by hand and fill in "day".
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Param

# Each job's own Python, built into the image by pipelines/Dockerfile
VENVS = "/home/airflow/venvs"

# The day to load: the one chosen by hand, or else the day before the run's date.
# The run's date is its logical date. A run started by hand may have none (and then "ds"
# doesn't exist), so fall back to when it was started.
DAY = (
    "{% set run_date = dag_run.logical_date or dag_run.run_after %}"
    "{{ params.day or macros.ds_add(run_date | ds, -1) }}"
)

with DAG(
    dag_id="daily_events",
    description="Lake to warehouse, then dbt: fresh retention numbers every morning",
    schedule="30 0 * * *",  # 00:30 UTC, every day
    start_date=datetime(2026, 10, 1),
    catchup=False,  # on first start, don't run every night since start_date
    max_active_runs=1,  # two dbt builds at once would fight over the same tables
    default_args={"owner": "kai", "retries": 2, "retry_delay": timedelta(minutes=5)},
    params={
        "day": Param(
            None,
            type=["null", "string"],
            format="date",
            description="Load this day instead of yesterday, e.g. 2026-10-27",
        )
    },
    tags=["lake", "dbt"],
    doc_md=__doc__,
):
    load_events = BashOperator(
        task_id="load_events",
        bash_command=f"{VENVS}/pipelines/bin/python -m ingest.load_events --date {DAY}",
    )

    # "build" runs each model and then its tests, before anything downstream is built,
    # so a model that fails its tests never feeds bad rows to the tables after it
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=f"{VENVS}/dbt/bin/dbt build",
    )

    load_events >> dbt_build
