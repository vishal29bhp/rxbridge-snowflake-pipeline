-- CHECK 3 - is it a real drug, at a sensible dose, in a known unit? Is it a known lab test?
-- Runs on the CURRENT medication values, so once a reviewer corrects a dose the flag clears.
with meds as (
    select
        m.report_id,
        dd.dmd_code,
        m.dose_value,
        m.dose_unit,
        dr.unit     as range_unit,
        dr.min_dose,
        dr.max_dose
    from {{ ref('int_medication_lines') }} m
    left join {{ ref('dmd_drugs') }}   dd on dd.match_key = m.drug_match_key
    left join {{ ref('dose_ranges') }} dr on dr.match_key = m.drug_match_key
),
med_flags as (
    select
        report_id,
        count(*)                                                    as n_meds,
        count_if(dmd_code is null)                                  as dmd_unmatched,
        count_if(min_dose is not null and (
                     dose_value is null
                  or dose_unit <> range_unit
                  or dose_value < min_dose
                  or dose_value > max_dose))                        as dose_out_of_range,
        count_if(dose_unit is null
                 or dose_unit not in ('mg', 'microgram', 'g', 'ml', 'unit', 'tablet')) as unknown_units
    from meds
    group by report_id
),
lab_flags as (
    select report_id, count(*) as n_labs, count_if(test_code is null) as lab_unmatched
    from {{ ref('int_lab_results') }}
    group by report_id
),
flags as (
    select
        d.report_id,
        d.doc_type,
        coalesce(m.n_meds, 0)            as n_meds,
        coalesce(l.n_labs, 0)            as n_labs,
        array_construct_compact(
            iff(m.dmd_unmatched     > 0, 'drug not in dm+d',           null),
            iff(m.dose_out_of_range > 0, 'dose outside expected range', null),
            iff(m.unknown_units     > 0, 'unknown dose unit',          null),
            iff(l.lab_unmatched     > 0, 'lab test not recognised',    null),
            iff(d.doc_type in ('prescription', 'lab_report')
                and coalesce(m.n_meds, 0) + coalesce(l.n_labs, 0) = 0, 'nothing extracted', null)
        )                                as flag_array
    from {{ ref('stg_documents') }} d
    left join med_flags m on m.report_id = d.report_id
    left join lab_flags l on l.report_id = d.report_id
)
select
    report_id,
    doc_type,
    n_meds,
    n_labs,
    array_size(flag_array)               as validator_flag_count,
    array_to_string(flag_array, '; ')    as validator_flags
from flags
