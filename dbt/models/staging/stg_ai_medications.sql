-- One row per medication, per reading step, exactly as the reader returned it.
select
    r.report_id,
    r.step,
    m.index                                  as line_no,
    r.report_id || '-' || m.index            as medication_line_id,
    m.value:drug_name::varchar               as drug_name,
    m.value:dose_value::float                as dose_value,
    m.value:dose_unit::varchar               as dose_unit,
    m.value:frequency::varchar               as frequency,
    m.value:duration_days::number            as duration_days,
    m.value:quantity::float                  as quantity,
    m.value:source_quote::varchar            as source_quote
from {{ ref('stg_reads') }} r,
     lateral flatten(input => r.medications) m
