-- Reader habits add up (Card 7.6): every read is a weekday or a weekend one, shares and
-- times are possible, and readers who never read have no times at all.

select user_key, 'reads do not add up' as problem
from {{ ref('fct_reader_habits') }}
where reads <> weekday_reads + weekend_reads

union all

select user_key, 'a share outside 0 to 1, or a time outside the day'
from {{ ref('fct_reader_habits') }}
where weekend_share not between 0 and 1
    or weekday_minute not between 0 and 1439
    or weekend_minute not between 0 and 1439

union all

select user_key, 'a time for a reader who never read'
from {{ ref('fct_reader_habits') }}
where reads = 0 and (weekday_minute is not null or weekend_minute is not null)
