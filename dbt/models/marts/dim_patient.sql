-- SCD type 2 patient dimension.
-- The snapshot records WHEN WE NOTICED a change (load time). Prescriptions need the
-- BUSINESS date the change happened, so each version is valid from its `clinic_since`
-- date (the first version from 1900-01-01) until the next version starts.
-- Name and phone are type 1: always the current value.
with versions as (
    select
        s.nhs_number,
        s.registered_clinic,
        s.clinic_since,
        s.dbt_valid_to is null                                               as is_current,
        row_number() over (partition by s.nhs_number order by s.dbt_valid_from) as version_no
    from {{ ref('snp_patients') }} s
),
dated as (
    select
        v.*,
        iff(v.version_no = 1, '1900-01-01'::date, v.clinic_since)           as valid_from
    from versions v
)
select
    {{ surrogate_key(['d.nhs_number', 'd.version_no']) }}                   as patient_key,
    d.nhs_number,
    p.patient_name,                                                          -- type 1
    p.date_of_birth,
    p.phone,                                                                 -- type 1
    d.registered_clinic,                                                     -- type 2
    d.version_no,
    d.valid_from,
    lead(d.valid_from) over (partition by d.nhs_number order by d.version_no) as valid_to,
    d.is_current
from dated d
left join {{ source('raw', 'patients') }} p on p.nhs_number = d.nhs_number

union all

-- Unknown member: a fact is never dropped because its patient is missing.
select '-1', 'UNKNOWN', 'Unknown patient', null, null, 'Unknown', 0, '1900-01-01'::date, null, true
