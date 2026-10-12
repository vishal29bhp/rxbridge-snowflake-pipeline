-- The main reading of each document (step = 'extract').
select * exclude (step)
from {{ ref('stg_reads') }}
where step = 'extract'
