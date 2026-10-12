-- Provenance: every medication in GOLD can be traced to the words on the page.
{{ config(severity='warn') }}
select medication_line_id from {{ ref('fct_medication') }} where source_quote is null
