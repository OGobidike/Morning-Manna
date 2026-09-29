

# Morning Manna

Hihi! OG here! smiley day to ya! This project will create a daily Bible reading app for working class people: you can set your wake time, get reminders in the morning,
read one short passage, and other features! 

This is also a full data platform: Contains everything from Python API, ETL pipelines, Airflow, dbt, and analytics dashboards,
and machine learning models for streak-risk prediction, reader personas, and passage
recommendations.

**status Early-Dev**

## Da Stack

| Layer | Tools |
|---|---|
| Mobile | React Native (Expo), TypeScript |
| API | Python, FastAPI, PostgreSQL |
| Data | pandas, Airflow, dbt, AWS S3 |
| ML / NLP | scikit-learn, sentence embeddings, pgvector, LLM API |
| Ops | Docker, GitHub Actions, AWS(mayyybe we'll see) |

## Repository layout

```
backend/     FastAPI service
mobile/      React Native (Expo) app
pipelines/   ETL jobs and Airflow DAGs
analytics/   dbt models and dashboard
ml/          models and experiments
docs/        blueprint and design notes
```

## What will run locally

```
bash, Docker, cd mobile && npm install && expo start

```
The text comes from the: (World English Bible, as well as King James).

## License

MIT