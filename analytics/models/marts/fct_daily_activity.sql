-- One row per day per persona, in each reader's own time zone: how many readers had
-- joined, how many read, and how many of those who opened a reading finished one.
-- The dashboard reads this, so it never has to touch raw events.

with users as (

    select
        user_key,
        -- Real app users have no persona: they get their own group
        coalesce(persona, 'app') as persona,
        timezone
    from {{ ref('stg_users') }}

),

readers as (

    select
        d.local_day,
        u.persona,
        count(*) as readers_so_far,
        count(*) filter (where d.did_read) as active_readers,
        count(*) filter (where d.opened_app) as opened_app
    from {{ ref('int_daily_reading') }} as d
    join users as u using (user_key)
    group by d.local_day, u.persona

),

reading_days as (

    -- Per reader per day: did they open a reading, and did they finish one?
    -- Counting readers, not events, keeps the rate honest if an app reading starts
    -- before midnight and finishes after it.
    select
        e.user_key,
        (e.occurred_at at time zone u.timezone)::date as local_day,
        bool_or(e.event_type = 'reading_opened') as opened_reading,
        bool_or(e.event_type = 'reading_completed') as finished_reading
    from {{ ref('stg_events') }} as e
    join users as u using (user_key)
    group by e.user_key, local_day

),

readings as (

    select
        r.local_day,
        u.persona,
        count(*) filter (where r.opened_reading) as opened_reading,
        count(*) filter (where r.opened_reading and r.finished_reading) as finished_reading
    from reading_days as r
    join users as u using (user_key)
    group by r.local_day, u.persona

)

select
    r.local_day || '/' || r.persona as activity_id,
    r.local_day,
    r.persona,
    r.readers_so_far,
    r.active_readers,
    r.opened_app,
    coalesce(x.opened_reading, 0) as opened_reading,
    coalesce(x.finished_reading, 0) as finished_reading,
    round(x.finished_reading::numeric / nullif(x.opened_reading, 0), 3) as completion_rate
from readers as r
left join readings as x using (local_day, persona)
