-- One row per reader in the reminder experiment (docs/analysis/reminder-experiment.md):
-- their group, and the measures the test is decided on. Only readers who joined while the
-- test ran are in it. For the pretend readers it ran the whole simulation; for real app
-- users it began on var('reminder_test_app_start'), when the app started flipping the coin.
-- Everyone stays in the group they were given, reminders on or off (intention to treat).

with users as (

    select
        user_key,
        source,
        coalesce(persona, 'app') as persona,
        reminder_variant,
        signed_up_on,
        timezone
    from {{ ref('stg_users') }}
    where source = 'synthetic'
        or signed_up_on >= '{{ var("reminder_test_app_start") }}'::date

),

returns as (

    select
        user_key,
        bool_or(days_since_signup = 1 and did_read) as read_day_1,
        bool_or(days_since_signup = 7 and did_read) as read_day_7
    from {{ ref('int_daily_reading') }}
    group by user_key

),

first_week as (

    -- The finish-rate guardrail, over each reader's first eight days (day 0 to day 7):
    -- on how many days they opened a reading, and on how many of those they finished one.
    -- Counted in reader-days, like the dashboard, so a reading across midnight counts once.
    select
        e.user_key,
        (e.occurred_at at time zone u.timezone)::date as local_day,
        bool_or(e.event_type = 'reading_opened') as opened_reading,
        bool_or(e.event_type = 'reading_completed') as finished_reading
    from {{ ref('stg_events') }} as e
    join users as u using (user_key)
    where (e.occurred_at at time zone u.timezone)::date
        between u.signed_up_on and u.signed_up_on + 7
    group by e.user_key, local_day

),

first_week_totals as (

    select
        user_key,
        count(*) filter (where opened_reading) as first_week_opened,
        count(*) filter (where opened_reading and finished_reading) as first_week_finished
    from first_week
    group by user_key

)

select
    u.user_key,
    u.source,
    u.persona,
    u.reminder_variant,
    u.signed_up_on,
    -- Measured against the last day of their own source's data (int_last_day)
    coalesce(u.signed_up_on + 1 <= l.last_day, false) as can_have_day_1,
    coalesce(r.read_day_1, false) as read_day_1,
    coalesce(u.signed_up_on + 7 <= l.last_day, false) as can_have_day_7,
    coalesce(r.read_day_7, false) as read_day_7,
    coalesce(w.first_week_opened, 0) as first_week_opened,
    coalesce(w.first_week_finished, 0) as first_week_finished
from users as u
left join {{ ref('int_last_day') }} as l using (source)
left join returns as r using (user_key)
left join first_week_totals as w using (user_key)
