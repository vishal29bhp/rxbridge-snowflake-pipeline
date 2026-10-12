-- PUBLISH GATE: no approved medication in GOLD may have a dose outside its sanity range.
-- If a reviewer approves the 5000 mg metformin photo without correcting it, this fails,
-- `dbt build` skips the outbox, and nothing reaches a doctor.
{{ config(severity='error') }}
select m.medication_line_id, m.drug_name_read, m.dose_value, m.dose_unit, r.min_dose, r.max_dose
from {{ ref('fct_medication') }} m
join {{ ref('dim_drug') }} d    on d.drug_key = m.drug_key
join {{ ref('dose_ranges') }} r on r.match_key = d.match_key
where m.dose_unit <> r.unit
   or m.dose_value < r.min_dose
   or m.dose_value > r.max_dose
