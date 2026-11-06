# The night watchman's image: Airflow, plus a separate Python for each job it runs.
# docker compose builds it from the repo root (see the airflow service). The MLflow server and
# the ML service run from it too (Card 9), each with its own Python, so there's one image to
# build and nothing extra to download.
FROM apache/airflow:slim-3.3.2-python3.12

# The postgres extra lets Airflow keep its records in Postgres. The constraints file pins
# every library to the versions this Airflow release was tested with.
RUN pip install --no-cache-dir "apache-airflow[postgres]==3.3.2" \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt"

# Our code is mounted at /opt/manna when the container runs. Make the folder airflow's.
# LightGBM needs the GNU OpenMP library, which the slim image leaves out
USER root
RUN mkdir /opt/manna && chown airflow /opt/manna \
 && apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*
USER airflow

# Just enough of each project to install what it depends on
COPY --chown=airflow backend/pyproject.toml /opt/manna/backend/
COPY --chown=airflow backend/app /opt/manna/backend/app
COPY --chown=airflow pipelines/pyproject.toml /opt/manna/pipelines/
COPY --chown=airflow pipelines/ingest /opt/manna/pipelines/ingest
COPY --chown=airflow analytics/requirements.txt /opt/manna/analytics/
COPY --chown=airflow ml/pyproject.toml ml/*.py /opt/manna/ml/

# One venv per job, so their libraries never clash with Airflow's, or with each other's.
# The -e (editable) installs point at /opt/manna, where your live code is mounted, so
# changing code needs no rebuild. Only a new dependency does.
# To keep the image small (Card 9b): no precompiled bytecode, which Python makes itself on first
# import. These venvs keep their libraries' tests/ folders: dbt keeps its built-in test macros
# (not_null, unique) in one, and deleting it broke every dbt test
RUN python -m venv /home/airflow/venvs/backend \
 && /home/airflow/venvs/backend/bin/pip install --no-cache-dir --no-compile -e /opt/manna/backend \
 && python -m venv /home/airflow/venvs/pipelines \
 && /home/airflow/venvs/pipelines/bin/pip install --no-cache-dir --no-compile -e /opt/manna/pipelines \
 && python -m venv /home/airflow/venvs/dbt \
 && /home/airflow/venvs/dbt/bin/pip install --no-cache-dir --no-compile \
    -r /opt/manna/analytics/requirements.txt

# The models (Card 9): the weekly retrain, the nightly scoring, the ML service and the MLflow
# server all run from this one Python. The server's extra (tracking-server) adds what only it
# uses, boto3 for the lake; a Python of its own would repeat 0.9 GB of the same libraries.
# Here the libraries' own test suites are deleted too, in the same step (a later step can't
# shrink this one): every job that uses this venv was run on the trimmed image (Card 9b)
RUN python -m venv /home/airflow/venvs/ml \
 && /home/airflow/venvs/ml/bin/pip install --no-cache-dir --no-compile \
    -e "/opt/manna/ml[models,tracking,serving,nlp,tracking-server]" \
 && find /home/airflow/venvs/ml -path "*/site-packages/*/tests" -type d -prune -exec rm -rf {} + \
 && mkdir -p /home/airflow/.cache/fastembed
