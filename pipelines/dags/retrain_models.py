"""Every Sunday: retrain the streak-at-risk models, and crown a new champion only if it's better.

    retrain   (python ml/model_registry.py, Card 7.3)

It trains the four models on every streak night in the warehouse, holding out the latest three
weeks, logs the race to the MLflow server (http://localhost:5000), and registers the best one.
The new model takes @champion only if it strictly beats the current champion, re-scored on the
same held-out nights; otherwise the champion stays, and the new version is kept for the record.
The nightly scoring and the ML service pick up a new champion by themselves.

It runs at 02:00 UTC on Sundays, after that night's daily_events has rebuilt the tables. Run it
by hand once after first starting the stack, to crown the first champion.

Only one retrain ever runs at a time (Card 9b). Training takes about 1 GB of memory, and on an
8 GB laptop WSL has under 4 GB: when two runs left over from an old schedule started beside a
manual one, all three died. max_active_runs alone didn't stop them, because those runs already
existed; the limit on the task itself holds however its runs were made.
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

# Each job's own Python, built into the image by pipelines/Dockerfile
VENVS = "/home/airflow/venvs"

with DAG(
    dag_id="retrain_models",
    description="Weekly: retrain streak risk, crown it only if it beats the champion",
    schedule="0 2 * * 0",  # Sundays at 02:00 UTC, after daily_events
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,  # two races at once would register their versions in a muddle
    default_args={"owner": "kai", "retries": 1, "retry_delay": timedelta(minutes=10)},
    tags=["ml"],
    doc_md=__doc__,
):
    BashOperator(
        task_id="retrain",
        bash_command=f"{VENVS}/ml/bin/python /opt/manna/ml/model_registry.py",
        max_active_tis_per_dag=1,  # one retrain at a time, whichever run it belongs to
    )
