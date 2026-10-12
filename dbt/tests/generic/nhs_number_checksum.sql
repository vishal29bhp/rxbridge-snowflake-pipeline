{#- Generic test: every value is a valid 10-digit NHS number (modulus 11). Returns failing rows. -#}
{% test nhs_number_checksum(model, column_name) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} is not null
  and not {{ nhs_number_valid(column_name) }}
{% endtest %}
