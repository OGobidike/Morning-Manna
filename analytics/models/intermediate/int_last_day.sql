-- The last day with any data, for each source of readers ('synthetic' or 'app'), in the
-- readers' own time. The pretend readers' world ends where the simulation ends, while real
-- readers' goes on, so each source is measured against its own last day: a real reading
-- must never stretch the pretend readers' calendar (Card 6.5.3a).

select
    u.source,
    max((e.occurred_at at time zone u.timezone)::date) as last_day
from {{ ref('stg_events') }} as e
join {{ ref('stg_users') }} as u using (user_key)
group by u.source
