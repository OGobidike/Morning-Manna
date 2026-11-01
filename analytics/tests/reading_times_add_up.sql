
-- Every finished reading lands in exactly one half hour, and the half hours run from
-- 0 to 47. Any row returned is a failure.
with clock as (

    select sum(readings) as readings, min(half_hour) as first_slot, max(half_hour) as last_slot
    from {{ ref('fct_reading_times') }}

),

events as (

    select count(*) as readings
    from {{ ref('stg_events') }}
    where event_type = 'reading_completed'

)

select clock.readings, events.readings
from clock
cross join events
where clock.readings != events.readings
   or clock.first_slot < 0
   or clock.last_slot > 47
