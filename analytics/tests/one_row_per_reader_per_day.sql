

-- int_daily_reading must hold each reader's day only once. Any row returned is a failure.
select user_key, local_day, count(*) as copies
from {{ ref('int_daily_reading') }}
group by user_key, local_day
having count(*) > 1
