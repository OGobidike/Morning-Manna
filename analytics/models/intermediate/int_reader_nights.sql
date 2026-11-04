-- What was known about each reader by the end of each day: the streak-at-risk model's
-- features, worked out once (Card 7.5). Two tables read from here, so the features the model
-- learns from and the features it's asked about tonight can never drift apart:
--
--     fct_reader_nights    every night whose next morning is known: the training data
--     fct_reader_tonight   each reader's last night, whose next morning hasn't come yet
--
-- No peeking: every feature looks only at that night and the days before it (each window
-- ends at the current row). reads_tomorrow is the only thing that looks ahead, and it's
-- empty on a reader's last night.

with days as (

    select user_key, local_day, days_since_signup, did_read
    from {{ ref('int_daily_reading') }}

),

first_reads as (

    -- When each reader first finished a reading each day, on their own clock
    select
        e.user_key,
        (e.occurred_at at time zone u.timezone)::date as local_day,
        min(e.occurred_at at time zone u.timezone) as first_read
    from {{ ref('stg_events') }} as e
    join {{ ref('stg_users') }} as u using (user_key)
    where e.event_type = 'reading_completed'
    group by e.user_key, local_day

),

nights as (

    select
        d.user_key,
        d.local_day,
        d.days_since_signup,
        d.did_read,
        -- Each missed morning starts a new run, so the run number is the misses so far
        count(*) filter (where not d.did_read) over to_date as misses_so_far,
        max(case when d.did_read then d.local_day end) over to_date as last_read_on,
        avg(d.did_read::int) over last_7 as read_rate_7d,
        avg(d.did_read::int) over last_28 as read_rate_28d,
        -- How much their reading time wanders, in minutes (needs two reads in 14 days)
        stddev_samp(
            extract(hour from f.first_read) * 60 + extract(minute from f.first_read)
        ) over last_14 as read_time_spread_14d,
        lead(d.did_read) over by_day as reads_tomorrow
    from days as d
    left join first_reads as f using (user_key, local_day)
    window
        by_day as (partition by d.user_key order by d.local_day),
        to_date as (partition by d.user_key order by d.local_day
            rows between unbounded preceding and current row),
        last_7 as (partition by d.user_key order by d.local_day
            rows between 6 preceding and current row),
        last_14 as (partition by d.user_key order by d.local_day
            rows between 13 preceding and current row),
        last_28 as (partition by d.user_key order by d.local_day
            rows between 27 preceding and current row)

),

streaks as (

    -- Mornings read in a row up to tonight: the reads since the last miss
    select
        *,
        sum(did_read::int) over (
            partition by user_key, misses_so_far order by local_day
            rows between unbounded preceding and current row
        ) as streak_days
    from nights

)

select
    s.user_key,
    u.source,
    u.reminder_variant,
    s.local_day as night,
    s.days_since_signup,
    s.did_read as read_today,
    s.streak_days,
    s.last_read_on is not null as ever_read,
    -- Never read yet: counted from the day before they joined
    coalesce(s.local_day - s.last_read_on, s.days_since_signup + 1) as days_since_last_read,
    round(s.read_rate_7d, 4) as read_rate_7d,
    round(s.read_rate_28d, 4) as read_rate_28d,
    round(s.read_time_spread_14d, 2) as read_time_spread_14d,
    -- The morning being predicted: 1 is Monday, 7 is Sunday
    extract(isodow from s.local_day + 1)::int as tomorrow_weekday,
    -- Empty on a reader's last night: that morning hasn't happened yet
    s.reads_tomorrow
from streaks as s
join {{ ref('stg_users') }} as u using (user_key)
