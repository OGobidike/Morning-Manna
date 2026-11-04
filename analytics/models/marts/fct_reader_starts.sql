-- One row per reader per day they started reading: when, on their own clock, and how long
-- after their wake time (Card 7.7, the best reminder time).
--
-- A reminder has to arrive before the reading starts, so this takes the first reading each
-- reader opened each day, not the one they finished. The gap is measured from the wake time
-- they set in the app; someone who starts before their alarm has a negative gap.

with first_starts as (

    select
        e.user_key,
        (e.occurred_at at time zone u.timezone)::date as local_day,
        min(e.occurred_at at time zone u.timezone) as started
    from {{ ref('stg_events') }} as e
    join {{ ref('stg_users') }} as u using (user_key)
    where e.event_type = 'reading_opened'
    group by e.user_key, local_day

)

select
    s.user_key,
    u.source,
    s.local_day,
    extract(isodow from s.local_day) >= 6 as at_weekend,
    -- Minutes after midnight: 330.5 is 05:30:30
    round(extract(epoch from s.started::time) / 60, 2) as started_minute,
    extract(hour from u.wake_time) * 60 + extract(minute from u.wake_time) as wake_minute,
    round(extract(epoch from s.started::time - u.wake_time) / 60, 2) as minutes_after_wake
from first_starts as s
join {{ ref('stg_users') }} as u using (user_key)
