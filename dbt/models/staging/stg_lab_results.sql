-- One row per lab result, per reading step.
select
    r.report_id,
    r.step,
    m.index                                  as line_no,
    m.value:test_name::varchar               as test_name,
    m.value:result_value::float              as result_value,
    m.value:unit::varchar                    as unit,
    m.value:ref_low::float                   as ref_low,
    m.value:ref_high::float                  as ref_high,
    m.value:source_quote::varchar            as source_quote
from {{ ref('stg_reads') }} r,
     lateral flatten(input => r.lab_results) m
