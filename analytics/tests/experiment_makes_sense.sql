-- Nobody returns on a day they haven't had yet, nobody finishes more readings than they
-- opened, and a first week holds at most eight reading days. Any row returned is a failure.
select user_key
from {{ ref('fct_experiment') }}
where (read_day_1 and not can_have_day_1)
   or (read_day_7 and not can_have_day_7)
   or first_week_finished > first_week_opened
   or first_week_opened > 8
