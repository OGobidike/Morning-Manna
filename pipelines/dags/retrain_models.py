

"""Every week: retrain the models on the latest reading data.

A placeholder for now. Phase 7 builds the models; this DAG is where they will be retrained.
"""

from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

with DAG(
    dag_id="retrain_models",
    description="Weekly retraining (a placeholder until Phase 7)",
    schedule="@weekly",  # Sundays at 00:00 UTC
    start_date=datetime(2026, 10, 1),
    catchup=False,
    default_args={"owner": "kai"},
    tags=["ml", "placeholder"],
    doc_md=__doc__,
):
    BashOperator(
        task_id="retrain",
        bash_command="echo 'Nothing to retrain yet: the models arrive in Phase 7.'",
    )
