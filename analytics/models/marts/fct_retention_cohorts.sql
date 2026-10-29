

-- One row per signup week: how many of that week's new readers came back to read
-- 1, 7 and 30 days after joining. A reader only counts once enough days have passed
-- to know: someone who joined yesterday can't have a day 7 yet.

with users as (

    select
        user_key,
        signed_up_on,
        date_trunc('week', signed_up_on)::date as cohort_week
    from {{ ref('stg_users') }}

),

last_day as (

    select max(local_day) as day from {{ ref('int_daily_reading') }}

),

returns as (

    select
        user_key,
        bool_or(days_since_signup = 1 and did_read) as read_day_1,
        bool_or(days_since_signup = 7 and did_read) as read_day_7,
        bool_or(days_since_signup = 30 and did_read) as read_day_30
    from {{ ref('int_daily_reading') }}
    group by user_key

),

per_reader as (

    select
        u.cohort_week,
        u.signed_up_on + 1 <= l.day as can_have_day_1,
        u.signed_up_on + 7 <= l.day as can_have_day_7,
        u.signed_up_on + 30 <= l.day as can_have_day_30,
        coalesce(r.read_day_1, false) as read_day_1,
        coalesce(r.read_day_7, false) as read_day_7,
        coalesce(r.read_day_30, false) as read_day_30
    from users as u
    cross join last_day as l
    left join returns as r using (user_key)

),

counted as (

    select
        cohort_week,
        count(*) as readers,
        count(*) filter (where can_have_day_1) as day_1_eligible,
        count(*) filter (where read_day_1) as day_1_returned,
        count(*) filter (where can_have_day_7) as day_7_eligible,
        count(*) filter (where read_day_7) as day_7_returned,
        count(*) filter (where can_have_day_30) as day_30_eligible,
        count(*) filter (where read_day_30) as day_30_returned
    from per_reader
    group by cohort_week

)

select
    *,
    round(day_1_returned::numeric / nullif(day_1_eligible, 0), 3) as day_1_rate,
    round(day_7_returned::numeric / nullif(day_7_eligible, 0), 3) as day_7_rate,
    round(day_30_returned::numeric / nullif(day_30_eligible, 0), 3) as day_30_rate
from counted
