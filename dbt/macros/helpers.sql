{# Surrogate key: MD5 of the parts, NULL-safe and separator-safe. #}
{% macro surrogate_key(columns) -%}
    md5({% for c in columns %}coalesce(cast({{ c }} as varchar), '~null~'){% if not loop.last %} || '|' || {% endif %}{% endfor %})
{%- endmacro %}

{# 2024-01-15 -> 20240115 (the key into dim_date) #}
{% macro date_key(col) -%}
    to_number(to_char({{ col }}, 'YYYYMMDD'))
{%- endmacro %}

{# NHS number modulus 11: weights 10..2 on the first nine digits; 11 -> 0; 10 = invalid. #}
{% macro nhs_number_valid(col) -%}
    coalesce(
        regexp_like({{ col }}, '^[0-9]{10}$')
        and mod(11 - mod(
              {%- for w in range(10, 1, -1) %}
              try_to_number(substr({{ col }}, {{ 11 - w }}, 1)) * {{ w }}{% if not loop.last %} +{% endif %}
              {%- endfor %}
            , 11), 11) <> 10
        and mod(11 - mod(
              {%- for w in range(10, 1, -1) %}
              try_to_number(substr({{ col }}, {{ 11 - w }}, 1)) * {{ w }}{% if not loop.last %} +{% endif %}
              {%- endfor %}
            , 11), 11) = try_to_number(substr({{ col }}, 10, 1)),
        false)
{%- endmacro %}
