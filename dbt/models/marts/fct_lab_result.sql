-- FACT: one row per test result on an APPROVED lab report.
with approved as (
    select report_id, review_status
    from {{ ref('fct_review_queue') }}
    where review_status in ('approved', 'approved_by_reviewer')
)
select
    l.lab_result_id,
    l.report_id,
    {{ date_key('l.test_date') }}                       as test_date_key,
    coalesce(p.patient_key, '-1')                       as patient_key,
    coalesce(t.lab_test_key, '-1')                      as lab_test_key,
    coalesce(pr.prescriber_key, '-1')                   as prescriber_key,
    l.test_name_read,
    l.result_value,
    l.unit,
    l.ref_low,
    l.ref_high,
    l.flag,
    l.source_quote,
    a.review_status
from {{ ref('int_lab_results') }} l
join approved a on a.report_id = l.report_id
left join {{ ref('dim_patient') }} p
       on p.nhs_number = l.nhs_number
      and l.test_date >= p.valid_from
      and (p.valid_to is null or l.test_date < p.valid_to)
left join {{ ref('dim_lab_test') }} t     on t.test_code = l.test_code
left join {{ ref('dim_prescriber') }} pr  on pr.prescriber_name = l.prescriber_name
                                          and pr.clinic = l.prescriber_clinic
