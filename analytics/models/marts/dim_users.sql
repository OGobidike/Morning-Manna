

-- One row per reader, with the facts the dashboards and models need about them,
-- including readers who never read at all (they matter most for retention).

with users as (

    select * from {{ ref('stg_users') }}

),

reading as (

    select
        user_key,
        min(local_day) filter (where did_read) as first_read_on,
        max(local_day) filter (where did_read) as last_read_on,
        count(*) filter (where did_read) as mornings_read,
        count(*) as days_since_joining
    from {{ ref('int_daily_reading') }}
    group by user_key

),

streaks as (

    select
        user_key,
        max(length_days) as longest_streak,
        max(length_days) filter (where is_current) as current_streak
    from {{ ref('fct_streaks') }}
    group by user_key

),

last_day as (

    select max(local_day) as day from {{ ref('int_daily_reading') }}

)

select
    u.user_key,
    u.source,
    u.persona,
    u.timezone,
    u.wake_time,
    u.signed_up_on,
    r.first_read_on,
    r.last_read_on,
    coalesce(r.mornings_read, 0) as mornings_read,
    coalesce(s.longest_streak, 0) as longest_streak,
    coalesce(s.current_streak, 0) as current_streak,
    r.first_read_on is null as never_read,
    -- Read at least once in the last 7 days there is data for
    coalesce(r.last_read_on > l.day - 7, false) as active_last_7_days
from users as u
cross join last_day as l
left join reading as r using (user_key)
left join streaks as s using (user_key)
