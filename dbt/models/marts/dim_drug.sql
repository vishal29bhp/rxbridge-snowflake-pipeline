-- One row per drug in the dm+d reference list, plus an 'unmatched' member.
select
    {{ surrogate_key(['dmd_code']) }}  as drug_key,
    match_key,
    dmd_code,
    drug_name,
    drug_class,
    form,
    strength
from {{ ref('dmd_drugs') }}

union all

select '-1', null, 'UNMATCHED', 'Not matched to dm+d', null, null, null
