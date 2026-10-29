

-- One row per event, tidied: plain names and types, ready for the models above

select
    event_id,
    user_key,
    event_type,
    occurred_at,
    received_at,
    -- The plan day of a reading, lifted out of the event's details
    (properties ->> 'day_number')::int as day_number,
    properties,
    source,
    dt as arrived_on
from {{ source('raw', 'events') }}
