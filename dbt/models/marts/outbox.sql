-- PUBLISH: append-only list of approved documents for RxBridge (Firestore via Pub/Sub, or
-- any consumer). Each document is added once, keyed by idempotency_key, so a consumer that
-- sees the same key twice simply updates instead of duplicating.
-- Because fct_document is upstream, a failing test on it SKIPS this model: nothing
-- unverified is ever published.
{{ config(materialized='incremental', unique_key='idempotency_key', incremental_strategy='append') }}

with meds as (
    select report_id,
           array_agg(object_construct(
               'drug', drug_name_read, 'dose', dose_value, 'unit', dose_unit,
               'frequency', frequency, 'days', days_supply, 'quantity', quantity_supplied
           )) within group (order by medication_line_id) as medications
    from {{ ref('fct_medication') }}
    group by report_id
),
labs as (
    select report_id,
           array_agg(object_construct(
               'test', test_name_read, 'value', result_value, 'unit', unit, 'flag', flag
           )) within group (order by lab_result_id) as lab_results
    from {{ ref('fct_lab_result') }}
    group by report_id
)
select
    d.idempotency_key,
    d.report_id,
    d.patient_key,
    'rx.document.v1'                                     as record_type,
    object_construct(
        'report_id', d.report_id,
        'doc_type', d.doc_type,
        'document_date_key', d.document_date_key,
        'source_file', d.source_file,
        'review_status', d.review_status,
        'medications', coalesce(m.medications, array_construct()),
        'lab_results', coalesce(l.lab_results, array_construct())
    )                                                    as payload,
    current_timestamp()::timestamp_ntz                   as published_at,
    'pending_delivery'                                   as delivery_status
from {{ ref('fct_document') }} d
left join meds m on m.report_id = d.report_id
left join labs l on l.report_id = d.report_id
{% if is_incremental() %}
where d.idempotency_key not in (select idempotency_key from {{ this }})
{% endif %}
