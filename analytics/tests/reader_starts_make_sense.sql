-- Reader starts make sense (Card 7.7): one row per reader per day, every time is inside the
-- day, and the gap after waking is the start time minus the wake time.

select user_key, 'more than one row for a day' as problem
from {{ ref('fct_reader_starts') }}
group by user_key, local_day
having count(*) > 1

union all

select user_key, 'a time outside the day'
from {{ ref('fct_reader_starts') }}
where started_minute not between 0 and 1440
    or wake_minute not between 0 and 1439

union all

select user_key, 'the gap is not the start time minus the wake time'
from {{ ref('fct_reader_starts') }}
where abs(minutes_after_wake - (started_minute - wake_minute)) > 0.02
