-- One row per reader: their reading habits, for finding reader personas (Card 7.6).
--
-- Only behaviour goes in: when they read on weekdays and at weekends, how much of their
-- reading falls at weekends, and how much their reading time wanders. The simulator's
-- persona (dim_users.persona) is the answer key the groups are graded against afterwards,
-- so it must never come in here.

with first_reads as (

    -- Each reader's first finished reading each day, on their own clock
    select
        e.user_key,
        (e.occurred_at at time zone u.timezone)::date as local_day,
        min(e.occurred_at at time zone u.timezone) as first_read
    from {{ ref('stg_events') }} as e
    join {{ ref('stg_users') }} as u using (user_key)
    where e.event_type = 'reading_completed'
    group by e.user_key, local_day

),

reads as (

    select
        user_key,
        extract(isodow from local_day) >= 6 as at_weekend,
        -- Minutes after midnight: 330 is 05:30
        extract(hour from first_read) * 60 + extract(minute from first_read) as read_minute
    from first_reads

)

select
    u.user_key,
    u.source,
    count(r.user_key) as reads,
    count(r.user_key) filter (where not r.at_weekend) as weekday_reads,
    count(r.user_key) filter (where r.at_weekend) as weekend_reads,
    round(avg(r.read_minute) filter (where not r.at_weekend), 1) as weekday_minute,
    round(avg(r.read_minute) filter (where r.at_weekend), 1) as weekend_minute,
    round(
        (count(r.user_key) filter (where r.at_weekend))::numeric / nullif(count(r.user_key), 0), 4
    ) as weekend_share,
    -- How much their reading time wanders, in minutes (needs two reads)
    round(stddev_samp(r.read_minute), 2) as read_minute_spread
from {{ ref('stg_users') }} as u
left join reads as r using (user_key)
group by u.user_key, u.source
