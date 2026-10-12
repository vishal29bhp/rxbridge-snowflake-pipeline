-- One row per day, 1990-01-01 to 2039-12-31, generated in Snowflake.
with days as (
    select dateadd(day, row_number() over (order by seq4()) - 1, '1990-01-01'::date) as d
    from table(generator(rowcount => 18262))
)
select
    {{ date_key('d') }}         as date_key,
    d                           as calendar_date,
    year(d)                     as year,
    month(d)                    as month,
    to_char(d, 'YYYY-MM')       as year_month,
    dayname(d)                  as day_name
from days
