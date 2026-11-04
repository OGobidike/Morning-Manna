-- The streak-at-risk table must never peek at the future (Card 7.1). This works out the
-- features a second way, by calendar date instead of window frames, joining each night only
-- to the days up to it, and the label only to the very next day. Any disagreement is a row.

with days as (

    select user_key, local_day, did_read from {{ ref('int_daily_reading') }}

),

nights as (

    select user_key, night, read_rate_7d, streak_days, missed_tomorrow
    from {{ ref('fct_reader_nights') }}

),

last_week as (

    -- Reads in the 7 days ending tonight, over the days the reader had in that window
    select n.user_key, n.night, avg(d.did_read::int) as read_rate_7d
    from nights as n
    join days as d
        on d.user_key = n.user_key and d.local_day between n.night - 6 and n.night
    group by n.user_key, n.night

),

last_miss as (

    -- The last missed morning up to tonight (none yet: the day before they joined)
    select n.user_key, n.night, max(d.local_day) filter (where not d.did_read) as last_miss
    from nights as n
    join days as d on d.user_key = n.user_key and d.local_day <= n.night
    group by n.user_key, n.night

),

joined as (

    select user_key, min(local_day) as joined_on from days group by user_key

)

select n.user_key, n.night
from nights as n
join last_week as w using (user_key, night)
join last_miss as m using (user_key, night)
join joined as j using (user_key)
left join days as tomorrow
    on tomorrow.user_key = n.user_key and tomorrow.local_day = n.night + 1
where round(w.read_rate_7d, 4) <> n.read_rate_7d
    or n.streak_days <> n.night - coalesce(m.last_miss, j.joined_on - 1)
    or (not tomorrow.did_read) is distinct from n.missed_tomorrow
