

-- One row per streak: mornings read in a row, found with "gaps and islands".
-- In a run of consecutive days, day minus its position in the run is the same date
-- for every day of that run, so grouping by it finds each streak.

with reads as (

    select user_key, local_day
    from {{ ref('int_daily_reading') }}
    where did_read

),

islands as (

    select
        user_key,
        local_day,
        local_day - (row_number() over (partition by user_key order by local_day))::int as island
    from reads

),

last_day as (

    select max(local_day) as day from {{ ref('int_daily_reading') }}

)

select
    user_key || '/' || min(local_day) as streak_id,
    user_key,
    min(local_day) as started_on,
    max(local_day) as ended_on,
    count(*) as length_days,
    -- Still going: read on the last day there is data for
    max(local_day) = (select day from last_day) as is_current
from islands
group by user_key, island
