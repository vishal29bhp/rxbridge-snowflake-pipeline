-- FACT: one row per medication line on an APPROVED document (prescription or clinical note).
-- Grain: medication_line_id. Additive measures: quantity_supplied, days_supply. Dose is NOT additive.
with approved as (
    select report_id, review_status, decided_at
    from {{ ref('fct_review_queue') }}
    where review_status in ('approved', 'approved_by_reviewer')
)
select
    m.medication_line_id,
    m.report_id,
    {{ date_key('m.prescribed_date') }}                 as prescribed_date_key,
    coalesce(p.patient_key, '-1')                       as patient_key,
    coalesce(dr.drug_key, '-1')                         as drug_key,
    coalesce(pr.prescriber_key, '-1')                   as prescriber_key,
    m.drug_name                                         as drug_name_read,
    m.dose_value,
    m.dose_unit,
    coalesce(f.expanded_text, m.frequency)              as frequency,       -- 'tds' -> 'three times daily'
    m.quantity                                          as quantity_supplied,
    m.duration_days                                     as days_supply,
    m.source_quote,
    m.last_changed_by,
    a.review_status,
    greatest(m.updated_at, a.decided_at)                as updated_at
from {{ ref('int_medication_lines') }} m
join approved a on a.report_id = m.report_id
left join {{ ref('dim_patient') }} p
       on p.nhs_number = m.nhs_number
      and m.prescribed_date >= p.valid_from
      and (p.valid_to is null or m.prescribed_date < p.valid_to)    -- the version true on that date
left join {{ ref('dim_drug') }} dr        on dr.match_key = m.drug_match_key
left join {{ ref('dim_prescriber') }} pr  on pr.prescriber_name = m.prescriber_name
                                          and pr.clinic = m.prescriber_clinic
left join {{ ref('rx_abbreviations') }} f on f.abbreviation = m.frequency
