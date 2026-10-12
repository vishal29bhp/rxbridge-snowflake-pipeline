-- The latest decision per report.
select report_id, reviewer, decision, reviewed_at, note
from {{ source('raw', 'review_decisions') }}
qualify row_number() over (partition by report_id order by reviewed_at desc) = 1
