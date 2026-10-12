-- CHECK 2 - does a second, different model agree?
-- Compares the 'extract' and 'verify' readings medication by medication. A line that one
-- model saw and the other didn't counts as a disagreement too.
with e as (select * from {{ ref('stg_ai_medications') }} where step = 'extract'),
     v as (select * from {{ ref('stg_ai_medications') }} where step = 'verify'),

pairs as (
    select
        coalesce(e.report_id, v.report_id) as report_id,
        (   e.report_id is null
         or v.report_id is null
         or lower(e.drug_name)        <> lower(v.drug_name)
         or e.dose_value              <> v.dose_value
         or coalesce(e.dose_unit, '') <> coalesce(v.dose_unit, '')
         or coalesce(e.frequency, '') <> coalesce(v.frequency, '')
        )                                  as disagrees
    from e
    full outer join v on v.report_id = e.report_id and v.line_no = e.line_no
)

select
    d.report_id,
    count_if(p.disagrees) as med_disagreements
from {{ ref('stg_documents') }} d
left join pairs p on p.report_id = d.report_id
group by d.report_id
