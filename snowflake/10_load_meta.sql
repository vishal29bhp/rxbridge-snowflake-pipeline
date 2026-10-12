-- =====================================================================================
-- 10_load_meta.sql  -  STAGE 2: load the vendor manifest and the patient list.
--   python -m rxpipe load-meta
--
-- Both are full snapshots ("this is the whole list today"), so we truncate and reload.
-- FORCE = TRUE: COPY normally skips files it has loaded before; here we always want the
-- latest copy, even if the file name is the same.
-- =====================================================================================

TRUNCATE TABLE RAW.SCAN_MANIFEST;

COPY INTO RAW.SCAN_MANIFEST (file_name, nhs_number, doc_type, clinic, scan_date, priority, _source_file, _loaded_at)
FROM (
    SELECT $1,
           REGEXP_REPLACE($2, '[^0-9]', ''),          -- '943 476 5919' -> '9434765919'
           LOWER($3),
           $4,
           TRY_TO_DATE($5, 'DD/MM/YYYY'),             -- UK dates are day-first
           TRY_TO_NUMBER($6),
           METADATA$FILENAME,
           CURRENT_TIMESTAMP()
    FROM @RAW.META_STAGE/manifest.csv
)
FILE_FORMAT = (FORMAT_NAME = 'RAW.FF_CSV')
FORCE = TRUE;

TRUNCATE TABLE RAW.PATIENTS;

COPY INTO RAW.PATIENTS (nhs_number, patient_name, date_of_birth, registered_clinic, clinic_since, phone, _loaded_at)
FROM (
    SELECT REGEXP_REPLACE($1, '[^0-9]', ''),
           $2,
           TRY_TO_DATE($3, 'DD/MM/YYYY'),
           $4,
           TRY_TO_DATE($5, 'DD/MM/YYYY'),
           $6,
           CURRENT_TIMESTAMP()
    FROM @RAW.META_STAGE/patients.csv
)
FILE_FORMAT = (FORMAT_NAME = 'RAW.FF_CSV')
FORCE = TRUE;

SELECT 'manifest rows' AS what, COUNT(*) AS n FROM RAW.SCAN_MANIFEST
UNION ALL
SELECT 'patients', COUNT(*) FROM RAW.PATIENTS;
