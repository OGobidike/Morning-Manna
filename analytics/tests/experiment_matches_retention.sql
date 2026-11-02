-- Every pretend reader is in the experiment, so its day-1 and day-7 counts, added up over
-- both groups, must equal the retention cohorts' counts for the pretend readers. Two
-- models built separately agreeing is a strong check that both count the same thing.
-- (The totals never show the groups apart, so this check can't peek at the result.)
with experiment as (

    select
        count(*) as readers,
        count(*) filter (where can_have_day_1) as day_1_eligible,
        count(*) filter (where read_day_1) as day_1_returned,
        count(*) filter (where can_have_day_7) as day_7_eligible,
        count(*) filter (where read_day_7) as day_7_returned
    from {{ ref('fct_experiment') }}
    where source = 'synthetic'

),

cohorts as (

    select
        coalesce(sum(readers), 0) as readers,
        coalesce(sum(day_1_eligible), 0) as day_1_eligible,
        coalesce(sum(day_1_returned), 0) as day_1_returned,
        coalesce(sum(day_7_eligible), 0) as day_7_eligible,
        coalesce(sum(day_7_returned), 0) as day_7_returned
    from {{ ref('fct_retention_cohorts') }}
    where persona != 'app'

)

select
    e.readers as experiment_readers,
    c.readers as cohort_readers,
    e.day_7_eligible as experiment_day_7_eligible,
    c.day_7_eligible as cohort_day_7_eligible
from experiment as e
cross join cohorts as c
where e.readers != c.readers
   or e.day_1_eligible != c.day_1_eligible
   or e.day_1_returned != c.day_1_returned
   or e.day_7_eligible != c.day_7_eligible
   or e.day_7_returned != c.day_7_returned
