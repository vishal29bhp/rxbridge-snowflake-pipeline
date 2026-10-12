-- One row per report and reading step ('extract' or 'verify'): the latest reading wins.
-- Fields are picked out of the VARIANT payload by name, so a new JSON field never breaks this.
select
    report_id,
    batch_id,
    step,
    extractor,
    model,
    payload:read_method::varchar                     as read_method,
    payload:raw_text::varchar                        as raw_text,
    payload:doc:doc_type::varchar                    as doc_type,
    payload:doc:prompt_version::varchar              as prompt_version,
    payload:doc:patient:nhs_number::varchar          as nhs_number,
    payload:doc:patient:name::varchar                as patient_name,
    try_to_date(payload:doc:document_date::varchar)  as document_date,
    payload:doc:prescriber:name::varchar             as prescriber_name,
    payload:doc:prescriber:clinic::varchar           as prescriber_clinic,
    coalesce(payload:doc:has_handwriting::boolean, false) as has_handwriting,
    payload:doc:summary::varchar                     as summary,
    payload:doc:medications                          as medications,
    payload:doc:lab_results                          as lab_results,
    _loaded_at                                       as loaded_at
from {{ source('raw', 'ai_results') }}
where step in ('extract', 'verify')
qualify row_number() over (partition by report_id, step order by _loaded_at desc, _source_file desc) = 1
