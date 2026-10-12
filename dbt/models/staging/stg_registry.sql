-- One row per document file, renamed for downstream use.
select
    report_id,
    relative_path        as source_file,
    file_sha256,
    mime_type,
    page_count,
    nhs_number           as manifest_nhs_number,   -- the vendor's link to the patient (trusted)
    doc_type,
    clinic               as manifest_clinic,
    status,
    batch_id,
    attempts,
    last_error,
    registered_at,
    updated_at
from {{ source('raw', 'file_registry') }}
