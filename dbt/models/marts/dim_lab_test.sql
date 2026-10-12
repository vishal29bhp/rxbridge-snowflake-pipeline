select distinct
    {{ surrogate_key(['test_code']) }} as lab_test_key,
    test_code,
    test_name,
    unit
from {{ ref('lab_tests') }}

union all

select '-1', 'UNMATCHED', 'Not recognised', null
