

# Morning Manna
![Morning Manna](docs/images/hero.png)

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
The text comes from the King James Version and the American Standard Version (both public domain).

**Status: the API, the Android app, the data platform (lake, loader, Airflow, dbt) and the first analytics (a notebook and a dashboard) are built. See [backend/README.md](backend/README.md), [mobile/README.md](mobile/README.md), [pipelines/README.md](pipelines/README.md) and [analytics/README.md](analytics/README.md).**

## 📊 The reading dashboard

![The reading dashboard: who reads each day, the reading clock, the reading rhythm, finish rate, streak survival and retention cohorts](docs/images/dashboard.png)

Who reads, when, how steadily, and who comes back: six charts and four headline tiles drawn from the dbt marts, rebuilt every night by Airflow, with a filter that recolours the whole page by reader persona. See [analytics/README.md](analytics/README.md).

## License

MIT