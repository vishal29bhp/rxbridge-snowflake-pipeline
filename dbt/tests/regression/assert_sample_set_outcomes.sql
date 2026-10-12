-- REGRESSION (sample data only): run with  dbt build --vars '{run_regression: true}'
-- For the 11 synthetic documents, the registry status must match, and the documents that
-- must be reviewed must never be auto-approved (and vice versa).
{{ config(enabled=var('run_regression', false), severity='error', tags=['regression']) }}
select e.source_file, e.expected_status, r.status, e.must_be_reviewed, q.route
from {{ ref('expected_outcomes') }} e
left join {{ ref('stg_registry') }} r      on r.source_file = e.source_file
left join {{ ref('fct_review_queue') }} q  on q.source_file = e.source_file
where coalesce(r.status, 'missing') <> e.expected_status
   or (e.must_be_reviewed = true  and coalesce(q.route, 'missing') <> 'review_full')
   or (e.must_be_reviewed = false and coalesce(q.route, 'missing') = 'review_full')
