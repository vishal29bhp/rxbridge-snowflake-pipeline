-- PUBLISH GATE: every GOLD fact row belongs to an approved document. Belt and braces:
-- this catches a future model change that forgets the approved-only join.
{{ config(severity='error') }}
select 'fct_medication' as model, m.report_id
from {{ ref('fct_medication') }} m
left join {{ ref('fct_review_queue') }} q on q.report_id = m.report_id
where coalesce(q.review_status, 'missing') not in ('approved', 'approved_by_reviewer')
union all
select 'fct_lab_result', l.report_id
from {{ ref('fct_lab_result') }} l
left join {{ ref('fct_review_queue') }} q on q.report_id = l.report_id
where coalesce(q.review_status, 'missing') not in ('approved', 'approved_by_reviewer')
