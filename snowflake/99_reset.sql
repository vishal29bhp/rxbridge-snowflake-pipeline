-- =====================================================================================
-- 99_reset.sql  -  start the walkthrough again from an empty pipeline.
--   python -m rxpipe reset --yes     (also deletes the results/ files in Azure)
-- Keeps: the stages, UDF, procedure, review app, and your original documents in Azure.
-- =====================================================================================
USE ROLE RX_ENGINEER;
USE DATABASE RX_DB;

TRUNCATE TABLE IF EXISTS RAW.FILE_REGISTRY;
TRUNCATE TABLE IF EXISTS RAW.AI_RESULTS;
TRUNCATE TABLE IF EXISTS RAW.MEDICATION_EVENTS;
TRUNCATE TABLE IF EXISTS RAW.REVIEW_DECISIONS;
TRUNCATE TABLE IF EXISTS RAW.SCAN_MANIFEST;
TRUNCATE TABLE IF EXISTS RAW.PATIENTS;

DROP SCHEMA IF EXISTS RX_DB.STAGING;
DROP SCHEMA IF EXISTS RX_DB.INTERMEDIATE;
DROP SCHEMA IF EXISTS RX_DB.GOLD;
DROP SCHEMA IF EXISTS RX_DB.SNAPSHOTS;
DROP SCHEMA IF EXISTS RX_DB.REFERENCE;

SELECT 'reset done' AS status;
