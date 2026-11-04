-- The streak-at-risk table's features agree with each other (Card 7.1): one row per reader
-- per night, a streak only on a night they read, and rates that are real rates.

select user_key, night, 'the same night twice' as problem
from {{ ref('fct_reader_nights') }}
group by user_key, night
having count(*) > 1

union all

select user_key, night, 'a streak longer than their time here, or below zero'
from {{ ref('fct_reader_nights') }}
where streak_days < 0 or streak_days > days_since_signup + 1

union all

select user_key, night, 'a streak on a night they did not read, or none on a night they did'
from {{ ref('fct_reader_nights') }}
where (streak_days > 0) <> read_today
    or (days_since_last_read = 0) <> read_today

union all

select user_key, night, 'a rate outside 0 to 1, or an impossible weekday'
from {{ ref('fct_reader_nights') }}
where read_rate_7d not between 0 and 1
    or read_rate_28d not between 0 and 1
    or tomorrow_weekday not between 1 and 7
