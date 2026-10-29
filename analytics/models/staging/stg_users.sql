

-- One row per reader: the pretend ones and the real app users, in the same shape

with pretend as (

    select
        user_key,
        persona,
        timezone,
        wake_time::time as wake_time,
        signed_up_on,
        source
    from {{ source('raw', 'readers') }}

),

app as (

    select
        'app:' || id as user_key,
        null::text as persona,
        timezone,
        wake_time,
        -- The day they joined, in their own time zone
        (created_at at time zone timezone)::date as signed_up_on,
        'app' as source
    from {{ source('app', 'users') }}

)

select * from pretend
union all
select * from app
