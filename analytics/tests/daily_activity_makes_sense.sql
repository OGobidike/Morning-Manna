
-- No more readers active than had joined, no more finishing a reading than opened one,
-- and every completion rate between 0 and 1. Any row returned is a failure.
select activity_id
from {{ ref('fct_daily_activity') }}
where active_readers > readers_so_far
   or opened_app > readers_so_far
   or finished_reading > opened_reading
   or opened_reading > readers_so_far
   or completion_rate not between 0 and 1
