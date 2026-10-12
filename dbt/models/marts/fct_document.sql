-- FACT: one row per APPROVED source document - the audit trail. From any medication or
-- lab result you can get back to the exact file, the model that read it, and who approved it.
-- Carries the enforced `rx.document.v1` contract (see _marts.yml): a change to these
-- columns or types fails the build before anything is published.
select
    sha2(r.file_sha256 || '|' || r.manifest_nhs_number, 256)::varchar  as idempotency_key,
    q.report_id::varchar                                              as report_id,
    q.doc_type::varchar                                               as doc_type,
    coalesce(p.patient_key, '-1')::varchar                            as patient_key,
    {{ date_key('d.document_date') }}::number                         as document_date_key,
    q.source_file::varchar                                            as source_file,
    q.mime_type::varchar                                              as mime_type,
    q.extractor::varchar                                              as extractor,
    q.model::varchar                                                  as extract_model,
    q.prompt_version::varchar                                         as prompt_version,
    q.route::varchar                                                  as route,
    q.review_status::varchar                                          as review_status,
    q.decided_at::timestamp_ntz                                       as approved_at
from {{ ref('fct_review_queue') }} q
join {{ ref('stg_registry') }}  r on r.report_id = q.report_id
join {{ ref('stg_documents') }} d on d.report_id = q.report_id
left join {{ ref('dim_patient') }} p
       on p.nhs_number = r.manifest_nhs_number
      and d.document_date >= p.valid_from
      and (p.valid_to is null or d.document_date < p.valid_to)
where q.review_status in ('approved', 'approved_by_reviewer')
