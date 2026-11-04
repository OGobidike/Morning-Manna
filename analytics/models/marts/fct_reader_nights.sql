-- One row per reader per night, with what was known by the end of that day and whether
-- they missed the next morning: the streak-at-risk model's training data (Card 7.1).
--
-- The features are worked out once, in int_reader_nights, and shared with fct_reader_tonight.
-- A night whose next morning is past the last day of its source's data has no label yet,
-- so it's left out here.

select
    user_key,
    source,
    reminder_variant,
    night,
    days_since_signup,
    read_today,
    streak_days,
    ever_read,
    days_since_last_read,
    read_rate_7d,
    read_rate_28d,
    read_time_spread_14d,
    tomorrow_weekday,
    not reads_tomorrow as missed_tomorrow
from {{ ref('int_reader_nights') }}
where reads_tomorrow is not null
