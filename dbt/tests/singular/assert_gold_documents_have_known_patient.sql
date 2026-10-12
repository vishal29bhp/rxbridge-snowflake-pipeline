-- PUBLISH GATE: an approved document must be linked to a real patient, never the unknown member.
{{ config(severity='error') }}
select report_id, source_file
from {{ ref('fct_document') }}
where patient_key = '-1'
