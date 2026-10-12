-- The latest event per medication line: a reviewer's correction (U) or rejection (D)
-- always beats the AI's original reading (I), because it has a higher event_seq.
select *
from {{ source('raw', 'medication_events') }}
qualify row_number() over (partition by medication_line_id order by event_seq desc, event_ts desc) = 1
