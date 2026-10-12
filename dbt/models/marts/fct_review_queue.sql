-- THE ROUTING DECISION: one row per document that was read.
--   auto_approve - every check passed on a typed document: goes to GOLD without a person
--   review_fast  - every check passed, but the source was a photo/scan: a quick human glance
--   review_full  - at least one check failed, or it's handwriting: a person checks every field
-- The default is always caution: anything not explicitly safe goes to review.
with s as (select * from {{ ref('int_report_scores') }}),
     d as (select * from {{ ref('stg_review_decisions') }}),

routed as (
    select
        s.*,
        (s.mime_type like 'image/%' or s.read_method = 'ocr') as is_scan,
        case
            when s.has_handwriting or s.doc_type = 'handwritten_note'      then 'review_full'
            when not coalesce(s.patient_match_ok, false)                     then 'review_full'
            when s.validator_flag_count > 0                                  then 'review_full'
            when s.med_disagreements > 0                                     then 'review_full'
            when not s.all_quotes_found                                      then 'review_full'
            when (s.mime_type like 'image/%' or s.read_method = 'ocr')       then 'review_fast'
            else 'auto_approve'
        end as route
    from s
)

select
    r.report_id,
    r.doc_type,
    r.source_file,
    r.mime_type,
    r.extractor,
    r.model,
    r.prompt_version,
    r.route,
    array_to_string(array_construct_compact(
        iff(r.has_handwriting or r.doc_type = 'handwritten_note', 'handwriting', null),
        iff(not coalesce(r.nhs_checksum_ok, false), 'NHS number check digit failed', null),
        iff(coalesce(r.nhs_checksum_ok, false) and not coalesce(r.matches_manifest, false),
            'NHS number differs from manifest', null),
        iff(not coalesce(r.known_patient, false), 'patient not in patient list', null),
        r.validator_flags,
        iff(r.med_disagreements > 0, r.med_disagreements || ' medication(s) differ between models', null),
        iff(not r.all_quotes_found, 'source quote not found in page text', null),
        iff(r.is_scan, 'photo/scan source', null)
    ), '; ')                                        as flag_reasons,
    d.decision,
    d.reviewer,
    d.reviewed_at,
    d.note                                          as review_note,
    case
        when d.decision = 'rejected'   then 'rejected'
        when d.decision = 'approved'   then 'approved_by_reviewer'
        when r.route = 'auto_approve'  then 'approved'
        else 'pending'
    end                                             as review_status,
    coalesce(d.reviewed_at, r.loaded_at)            as decided_at
from routed r
left join d on d.report_id = r.report_id
