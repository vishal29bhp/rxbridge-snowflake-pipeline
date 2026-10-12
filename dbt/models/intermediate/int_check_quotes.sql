-- CHECK 1 - did the reader make it up?
-- Every extracted line carries the exact text it came from (source_quote). Plain SQL,
-- not AI, checks that the quote really appears in the page text.
with quotes as (
    select report_id, source_quote from {{ ref('stg_ai_medications') }} where step = 'extract'
    union all
    select report_id, source_quote from {{ ref('stg_lab_results') }}    where step = 'extract'
)
select
    d.report_id,
    count(q.source_quote)                                               as quotes_checked,
    count_if(q.source_quote is not null
             and position(lower(q.source_quote) in lower(d.raw_text)) = 0) as quotes_missing
from {{ ref('stg_documents') }} d
left join quotes q on q.report_id = d.report_id
group by d.report_id
