-- Each source's calendar ends on that source's own last day with data. Before Card 6.5.3a,
-- one shared last day meant a real app reading could stretch every pretend reader's
-- calendar past the end of the simulation, counting days they could never have read on.
-- Worked out here without int_last_day, so this test still catches a return to one shared
-- day. Returns a row for each source whose calendar ends on the wrong day.

with calendar as (

    select u.source, max(d.local_day) as calendar_ends
    from {{ ref('int_daily_reading') }} as d
    join {{ ref('stg_users') }} as u using (user_key)
    group by u.source

),

data as (

    select u.source, max((e.occurred_at at time zone u.timezone)::date) as data_ends
    from {{ ref('stg_events') }} as e
    join {{ ref('stg_users') }} as u using (user_key)
    group by u.source

)

select *
from calendar
join data using (source)
where calendar_ends <> data_ends
