-- CHECK 4 - is this document linked to the right patient?
-- A perfect extraction for the wrong patient is the worst possible error, so all three must hold:
-- the NHS number on the page is valid, it matches the vendor manifest, and the patient exists.
select
    d.report_id,
    d.nhs_number                                          as nhs_number_read,
    r.manifest_nhs_number,
    {{ nhs_number_valid('d.nhs_number') }}                as nhs_checksum_ok,
    coalesce(d.nhs_number = r.manifest_nhs_number, false) as matches_manifest,
    p.nhs_number is not null                              as known_patient,
    jarowinkler_similarity(lower(d.patient_name), lower(p.patient_name)) as name_similarity  -- info only
from {{ ref('stg_documents') }} d
join {{ ref('stg_registry') }} r on r.report_id = d.report_id
left join {{ source('raw', 'patients') }} p on p.nhs_number = r.manifest_nhs_number
