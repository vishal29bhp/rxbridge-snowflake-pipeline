{#- Use the schema name exactly as configured (STAGING, GOLD, ...) instead of dbt's default
    "<target schema>_<custom schema>" prefixing. Keeps Snowflake object names easy to read. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim }}{%- endif -%}
{%- endmacro %}
