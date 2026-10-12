-- All checks side by side, one row per document. fct_review_queue turns this into a route.
select
    d.report_id,
    d.doc_type,
    r.source_file,
    r.mime_type,
    d.read_method,
    d.extractor,
    d.model,
    d.prompt_version,
    d.has_handwriting,
    d.loaded_at,
    coalesce(q.quotes_missing, 0) = 0                       as all_quotes_found,
    coalesce(a.med_disagreements, 0)                        as med_disagreements,
    coalesce(v.validator_flag_count, 0)                     as validator_flag_count,
    nullif(v.validator_flags, '')                           as validator_flags,
    p.nhs_checksum_ok,
    p.matches_manifest,
    p.known_patient,
    (p.nhs_checksum_ok and p.matches_manifest and p.known_patient) as patient_match_ok,
    p.name_similarity
from {{ ref('stg_documents') }} d
join {{ ref('stg_registry') }}            r on r.report_id = d.report_id
left join {{ ref('int_check_quotes') }}     q on q.report_id = d.report_id
left join {{ ref('int_check_agreement') }}  a on a.report_id = d.report_id
left join {{ ref('int_check_validators') }} v on v.report_id = d.report_id
left join {{ ref('int_check_patient') }}    p on p.report_id = d.report_id
