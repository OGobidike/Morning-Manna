-- Tonight's table is the right set of readers (Card 7.5): every reader who read on their
-- source's last day is there, nobody else is, and each one has a streak to protect.

with tonight as (

    select * from {{ ref('fct_reader_tonight') }}

),

should_be as (

    -- Everyone who finished a reading on their source's last day
    select d.user_key
    from {{ ref('int_daily_reading') }} as d
    join {{ ref('stg_users') }} as u using (user_key)
    join {{ ref('int_last_day') }} as l
        on l.source = u.source and l.last_day = d.local_day
    where d.did_read

)

select user_key, 'missing from tonight' as problem
from should_be
where user_key not in (select user_key from tonight)

union all

select user_key, 'tonight, but not a streak night on the last day'
from tonight as t
where user_key not in (select user_key from should_be)
    or t.night <> (select l.last_day from {{ ref('int_last_day') }} as l where l.source = t.source)
    or t.streak_days < 1
    or t.days_since_last_read <> 0
