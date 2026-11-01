-- One row per persona per half hour of the reader's own day: how many readings were
-- finished then. The dashboard draws its reading clock from this.

with users as (

    select
        user_key,
        -- Real app users have no persona: they get their own group
        coalesce(persona, 'app') as persona,
        timezone
    from {{ ref('stg_users') }}

),

finished as (

    select
        u.persona,
        -- 0 is 00:00 to 00:29, 1 is 00:30 to 00:59 ... 47 is 23:30 to 23:59, local time
        (
            extract(hour from e.occurred_at at time zone u.timezone) * 2
            + floor(extract(minute from e.occurred_at at time zone u.timezone) / 30)
        )::int as half_hour
    from {{ ref('stg_events') }} as e
    join users as u using (user_key)
    where e.event_type = 'reading_completed'

)

select
    persona || '/' || half_hour as slot_id,
    persona,
    half_hour,
    count(*) as readings
from finished
group by persona, half_hour
