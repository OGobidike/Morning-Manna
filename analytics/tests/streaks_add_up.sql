

-- A streak's length must match its dates, and every streak's days add up to the mornings
-- read. Any row returned is a failure.
select streak_id
from {{ ref('fct_streaks') }}
where length_days != ended_on - started_on + 1
   or length_days < 1
union all
select 'total' as streak_id
where (select sum(length_days) from {{ ref('fct_streaks') }})
   != (select count(*) from {{ ref('int_daily_reading') }} where did_read)
