

"""The DAG files load without errors, are wired as planned, and pick the right day to load.

These need Airflow installed, so CI runs them in their own job:  pytest dag_tests
"""

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from airflow.dag_processing.dagbag import DagBag
from airflow.sdk.execution_time import macros

DAGS = Path(__file__).resolve().parents[1] / "dags"


@pytest.fixture(scope="module")
def dagbag():
    return DagBag(dag_folder=DAGS)


def test_every_dag_file_loads(dagbag):
    assert dagbag.import_errors == {}
    assert set(dagbag.dag_ids) == {"daily_events", "ingest_scripture", "retrain_models"}


def test_daily_events_loads_the_lake_then_builds(dagbag):
    dag = dagbag.dags["daily_events"]
    assert dag.get_task("load_events").downstream_task_ids == {"dbt_build"}
    assert dag.schedule == "30 0 * * *"
    assert dag.max_active_runs == 1
    assert dag.catchup is False


def test_the_other_dags_run_when_planned(dagbag):
    assert dagbag.dags["ingest_scripture"].schedule is None  # only by hand
    assert dagbag.dags["retrain_models"].schedule == "@weekly"


def day_loaded(dagbag, day=None, logical_date=None, run_after=None) -> str:
    """The day daily_events would load, by filling in its command as Airflow does."""
    dag = dagbag.dags["daily_events"]
    command = dag.get_template_env().from_string(dag.get_task("load_events").bash_command)
    run = SimpleNamespace(logical_date=logical_date, run_after=run_after)
    return command.render(params={"day": day}, macros=macros, dag_run=run).split("--date ")[1]


def test_each_night_loads_the_day_before(dagbag):
    due = datetime(2026, 10, 29, 0, 30)
    assert day_loaded(dagbag, logical_date=due, run_after=due) == "2026-10-28"


def test_a_run_started_by_hand_with_no_date_loads_yesterday(dagbag):
    assert day_loaded(dagbag, run_after=datetime(2026, 10, 29, 10, 0)) == "2026-10-28"


def test_a_run_dated_by_hand_loads_the_day_before_its_date(dagbag):
    # Started on the 29th, but dated the 28th: it loads the 27th, as that night would have
    loaded = day_loaded(
        dagbag, logical_date=datetime(2026, 10, 28, 7, 0), run_after=datetime(2026, 10, 29)
    )
    assert loaded == "2026-10-27"


def test_a_chosen_day_wins(dagbag):
    loaded = day_loaded(dagbag, day="2026-10-20", run_after=datetime(2026, 10, 29))
    assert loaded == "2026-10-20"
