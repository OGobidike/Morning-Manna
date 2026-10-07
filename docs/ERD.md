# Morning Manna – Entity Relationship Diagram

How the nine tables connect. Source of truth: `backend/app/models.py`.

```mermaid
erDiagram
    %% Bible content
    translations  ||--o{ verses           : "contains"
    books         ||--o{ verses           : "contains"
    books         ||--o{ plan_days        : "read in"

    %% Reading plans
    reading_plans ||--o{ plan_days        : "has"
    reading_plans ||--o{ user_plans       : "followed in"

    %% Readers
    translations  ||--o{ users            : "read by"
    users         ||--o{ user_plans       : "enrolls in"
    users         ||--o{ reading_sessions : "opens"
    plan_days     ||--o{ reading_sessions : "read during"
    users         ||--o{ events           : "logs"

    translations {
        int id PK
        string code UK
        string name
        string license
    }

    books {
        int id PK
        string code UK
        string name UK
        string testament
        int canonical_order UK
    }

    verses {
        int id PK
        int translation_id FK
        int book_id FK
        int chapter
        int verse
        text text
    }

    reading_plans {
        int id PK
        string name UK
        text description
    }

    plan_days {
        int id PK
        int plan_id FK
        int day_number
        int book_id FK
        int start_chapter
        int start_verse
        int end_chapter
        int end_verse
    }

    users {
        int id PK
        string device_id UK
        string timezone
        time wake_time
        int translation_id FK
        datetime created_at
    }

    user_plans {
        int id PK
        int user_id FK
        int plan_id FK
        date start_date
        int current_day
    }

    reading_sessions {
        int id PK
        int user_id FK
        int plan_day_id FK
        datetime opened_at
        datetime completed_at "nullable"
        int seconds_spent "nullable"
    }

    events {
        int id PK
        int user_id FK
        string event_type
        datetime occurred_at
        jsonb properties
    }
```

## Unique rules

Mermaid can only mark single columns as `UK`. These rules span several columns:

| Table | Unique together | Meaning |
|---|---|---|
| `verses` | `translation_id, book_id, chapter, verse` | Each verse appears once per translation |
| `plan_days` | `plan_id, day_number` | Each plan has one row per day |
| `user_plans` | `user_id, plan_id` | A reader joins each plan only once |
