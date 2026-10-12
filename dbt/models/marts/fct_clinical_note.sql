-- FACT: one row per APPROVED handwritten clinical note (the free-text summary).
select
    d.report_id,
    {{ date_key('d.document_date') }}                   as note_date_key,
    coalesce(p.patient_key, '-1')                       as patient_key,
    coalesce(pr.prescriber_key, '-1')                   as prescriber_key,
    d.summary,
    q.review_status
from {{ ref('stg_documents') }} d
join {{ ref('stg_registry') }} r on r.report_id = d.report_id
join {{ ref('fct_review_queue') }} q
  on q.report_id = d.report_id and q.review_status in ('approved', 'approved_by_reviewer')
left join {{ ref('dim_patient') }} p
       on p.nhs_number = r.manifest_nhs_number
      and d.document_date >= p.valid_from
      and (p.valid_to is null or d.document_date < p.valid_to)
left join {{ ref('dim_prescriber') }} pr  on pr.prescriber_name = d.prescriber_name
                                          and pr.clinic = d.prescriber_clinic
where d.doc_type = 'handwritten_note'
