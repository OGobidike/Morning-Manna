

-- Returned readers can't outnumber the eligible ones, and rates stay between 0 and 1.
-- Any row returned is a failure.
select cohort_week
from {{ ref('fct_retention_cohorts') }}
where day_1_returned > day_1_eligible
   or day_7_returned > day_7_eligible
   or day_30_returned > day_30_eligible
   or day_1_eligible > readers
   or day_1_rate not between 0 and 1
   or day_7_rate not between 0 and 1
   or day_30_rate not between 0 and 1
