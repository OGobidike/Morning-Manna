-- One row per reader per day, in the reader's own time zone, from the day they joined
-- to the last day with any data. Days with no reading are rows too: retention and
-- streaks are about the mornings that were missed as much as the ones that weren't.

with users as (

    select * from {{ ref('stg_users') }}

),

events as (

    select
        e.user_key,
        -- A 05:30 read in Lagos belongs to the Lagos morning, whatever UTC says
        (e.occurred_at at time zone u.timezone)::date as local_day,
        e.event_type
    from {{ ref('stg_events') }} as e
    join users as u using (user_key)

),

last_day as (

    select max(local_day) as day from events

),

calendar as (

    -- Every day of each reader's life in the app, read or not
    select
        u.user_key,
        u.signed_up_on,
        gs.day::date as local_day
    from users as u
    cross join last_day
    cross join lateral generate_series(u.signed_up_on, last_day.day, interval '1 day') as gs (day)

),

activity as (

    select
        user_key,
        local_day,
        count(*) as events,
        bool_or(event_type = 'app_opened') as opened_app,
        bool_or(event_type = 'reading_completed') as read
    from events
    group by user_key, local_day

)

select
    c.user_key,
    c.local_day,
    c.local_day - c.signed_up_on as days_since_signup,
    coalesce(a.read, false) as did_read,
    coalesce(a.opened_app, false) as opened_app,
    coalesce(a.events, 0) as events
from calendar as c
left join activity as a using (user_key, local_day)
