-- The medication lines as they stand now: the latest event per line (so a reviewer's
-- correction wins), minus lines a reviewer rejected. The patient link comes from the
-- vendor manifest (trusted), not from what the reader saw on the page.
select
    e.medication_line_id,
    e.report_id,
    r.manifest_nhs_number                     as nhs_number,
    d.document_date                           as prescribed_date,
    d.prescriber_name,
    d.prescriber_clinic,
    e.drug_name,
    lower(split_part(e.drug_name, ' ', 1))    as drug_match_key,   -- 'Amoxicillin 500mg capsules' -> 'amoxicillin'
    e.dose_value,
    e.dose_unit,
    lower(e.frequency)                        as frequency,
    e.duration_days,
    e.quantity,
    q.source_quote,
    e.source                                  as last_changed_by,  -- 'ai' or 'reviewer'
    e.event_ts                                as updated_at
from {{ ref('stg_medication_events_latest') }} e
join {{ ref('stg_documents') }} d  on d.report_id = e.report_id
join {{ ref('stg_registry') }}  r  on r.report_id = e.report_id
left join {{ ref('stg_ai_medications') }} q
       on q.step = 'extract' and q.medication_line_id = e.medication_line_id
where e.op <> 'D'
