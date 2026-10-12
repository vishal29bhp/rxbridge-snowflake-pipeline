-- Every distinct prescriber found on a document, plus the unknown member.
select distinct
    {{ surrogate_key(['prescriber_name', 'prescriber_clinic']) }} as prescriber_key,
    prescriber_name,
    prescriber_clinic                                            as clinic
from {{ ref('stg_documents') }}
where prescriber_name is not null

union all

select '-1', 'Unknown prescriber', null
