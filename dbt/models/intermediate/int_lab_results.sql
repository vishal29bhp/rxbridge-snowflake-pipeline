-- Lab results from the main reading, matched to the lab test catalogue.
-- The High/Low/Normal flag is calculated here from the printed reference range;
-- it is never taken from the reader.
select
    l.report_id || '-' || l.line_no           as lab_result_id,
    l.report_id,
    r.manifest_nhs_number                     as nhs_number,
    d.document_date                           as test_date,
    d.prescriber_name,
    d.prescriber_clinic,
    l.test_name                               as test_name_read,
    t.test_code,
    t.test_name,
    l.result_value,
    l.unit,
    l.ref_low,
    l.ref_high,
    case
        when l.ref_high is not null and l.result_value > l.ref_high then 'High'
        when l.ref_low  is not null and l.result_value < l.ref_low  then 'Low'
        else 'Normal'
    end                                       as flag,
    l.source_quote
from {{ ref('stg_lab_results') }} l
join {{ ref('stg_documents') }} d on d.report_id = l.report_id
join {{ ref('stg_registry') }}  r on r.report_id = l.report_id
left join {{ ref('lab_tests') }} t on t.alias = lower(l.test_name)
where l.step = 'extract'
