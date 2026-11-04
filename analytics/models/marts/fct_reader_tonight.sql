-- One row per reader on a streak tonight: everyone who read on the last day of their
-- source's data, with the same features the model learned from (Card 7.5). Their next
-- morning hasn't happened yet, so there's no label: this is what the model is asked about.
--
-- The features come from int_reader_nights, the same recipe as fct_reader_nights, so
-- tonight's numbers are worked out exactly the way the training data's were.

select
    n.user_key,
    n.source,
    n.reminder_variant,
    n.night,
    n.days_since_signup,
    n.streak_days,
    n.days_since_last_read,
    n.read_rate_7d,
    n.read_rate_28d,
    n.read_time_spread_14d,
    n.tomorrow_weekday
from {{ ref('int_reader_nights') }} as n
join {{ ref('int_last_day') }} as l
    on l.source = n.source and l.last_day = n.night
-- Only readers with a streak to protect: they read today
where n.read_today
