-- =====================================================================================
-- 01_objects.sql  -  run as RX_ENGINEER:   python -m rxpipe setup
--
-- Creates everything the pipeline needs inside RX_DB.RAW:
--   file formats, three external stages on Azure Blob, the RAW tables,
--   a Python UDF that fingerprints files, and the batch-builder procedure.
-- Safe to re-run: tables use IF NOT EXISTS; functions/procedures are replaced.
-- =====================================================================================

USE ROLE RX_ENGINEER;
USE WAREHOUSE RX_LOAD_WH;
USE DATABASE RX_DB;
CREATE SCHEMA IF NOT EXISTS RAW;
USE SCHEMA RAW;

-- ---------- File formats ----------
CREATE FILE FORMAT IF NOT EXISTS RAW.FF_CSV
  TYPE = CSV SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"' TRIM_SPACE = TRUE EMPTY_FIELD_AS_NULL = TRUE;
CREATE FILE FORMAT IF NOT EXISTS RAW.FF_JSON
  TYPE = JSON;

-- ---------- Stages: Snowflake's view of the three folders in the Azure container ----------
-- The directory table on DOCS_STAGE is Snowflake's live list of documents (path, size, last modified).
CREATE STAGE IF NOT EXISTS RAW.DOCS_STAGE
  URL = 'azure://<<AZURE_STORAGE_ACCOUNT>>.blob.core.windows.net/<<AZURE_CONTAINER>>/inbox/'
  STORAGE_INTEGRATION = RX_AZURE_INT
  DIRECTORY = (ENABLE = TRUE);
CREATE STAGE IF NOT EXISTS RAW.META_STAGE
  URL = 'azure://<<AZURE_STORAGE_ACCOUNT>>.blob.core.windows.net/<<AZURE_CONTAINER>>/_meta/'
  STORAGE_INTEGRATION = RX_AZURE_INT
  FILE_FORMAT = RAW.FF_CSV;
CREATE STAGE IF NOT EXISTS RAW.RESULTS_STAGE
  URL = 'azure://<<AZURE_STORAGE_ACCOUNT>>.blob.core.windows.net/<<AZURE_CONTAINER>>/results/'
  STORAGE_INTEGRATION = RX_AZURE_INT
  FILE_FORMAT = RAW.FF_JSON;
-- Internal stage for the Streamlit review app's code (95_review_app.sql).
CREATE STAGE IF NOT EXISTS RAW.APP_STAGE;

-- ---------- RAW tables: landed as-is; dbt builds everything else from them ----------

-- The scanning vendor's list: which patient and document type each file is.
CREATE TABLE IF NOT EXISTS RAW.SCAN_MANIFEST (
    file_name     STRING,
    nhs_number    STRING,
    doc_type      STRING,
    clinic        STRING,
    scan_date     DATE,
    priority      NUMBER,
    _source_file  STRING,
    _loaded_at    TIMESTAMP_NTZ
);

-- The clinic's current patient list. dbt snapshots it to keep SCD2 history.
CREATE TABLE IF NOT EXISTS RAW.PATIENTS (
    nhs_number        STRING,
    patient_name      STRING,
    date_of_birth     DATE,
    registered_clinic STRING,
    clinic_since      DATE,
    phone             STRING,
    _loaded_at        TIMESTAMP_NTZ
);

-- One row per document. Only `status` (and its bookkeeping columns) ever changes:
--   PENDING_MANIFEST -> READY -> QUEUED -> RETURNED
--   or DUPLICATE / UNSUPPORTED / QUARANTINED
CREATE TABLE IF NOT EXISTS RAW.FILE_REGISTRY (
    report_id      STRING,
    relative_path  STRING,
    file_sha256    STRING,
    mime_type      STRING,
    file_size      NUMBER,
    page_count     NUMBER,
    nhs_number     STRING,
    doc_type       STRING,
    clinic         STRING,
    priority       NUMBER,
    status         STRING,
    batch_id       STRING,
    attempts       NUMBER,
    last_error     STRING,
    registered_at  TIMESTAMP_NTZ,
    queued_at      TIMESTAMP_NTZ,
    updated_at     TIMESTAMP_NTZ
);

-- Every line of every results file, kept whole as VARIANT. Never updated.
CREATE TABLE IF NOT EXISTS RAW.AI_RESULTS (
    batch_id      STRING,
    report_id     STRING,
    step          STRING,      -- extract | verify | error
    extractor     STRING,
    model         STRING,
    payload       VARIANT,
    error         STRING,
    _source_file  STRING,
    _loaded_at    TIMESTAMP_NTZ
);

-- Every change to a medication line: I = read by AI, U = corrected by reviewer, D = rejected.
CREATE TABLE IF NOT EXISTS RAW.MEDICATION_EVENTS (
    medication_line_id STRING,
    report_id          STRING,
    batch_id           STRING,
    op                 STRING,
    source             STRING,
    drug_name          STRING,
    dose_value         FLOAT,
    dose_unit          STRING,
    frequency          STRING,
    duration_days      NUMBER,
    quantity           FLOAT,
    event_ts           TIMESTAMP_NTZ,
    event_seq          NUMBER
);

-- One row per reviewer decision on a whole report.
CREATE TABLE IF NOT EXISTS RAW.REVIEW_DECISIONS (
    review_id    STRING,
    report_id    STRING,
    reviewer     STRING,
    decision     STRING,       -- approved | rejected
    reviewed_at  TIMESTAMP_NTZ,
    note         STRING
);

-- ---------- UDF: fingerprint one staged file (read once: SHA-256, real type, size, pages) ----------
-- Needs the Anaconda terms accepted once (Snowsight > Admin > Billing & Terms > Anaconda).
CREATE OR REPLACE FUNCTION RAW.FILE_FINGERPRINT(file_url STRING)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
AS
$$
import hashlib
import re
from snowflake.snowpark.files import SnowflakeFile

PAGE = re.compile(rb"/Type\s*/Page(?!s)")

def sniff(head):
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    return None

def run(file_url):
    h, size, pages, head = hashlib.sha256(), 0, 0, b""
    with SnowflakeFile.open(file_url, "rb") as f:
        while True:
            block = f.read(1024 * 1024)          # 1 MB at a time: large scans don't exhaust memory
            if not block:
                break
            if not head:
                head = block[:16]
            h.update(block)
            size += len(block)
            pages += len(PAGE.findall(block))   # estimate; good enough for the batch page budget
    mime = sniff(head)
    return {
        "sha256": h.hexdigest(),
        "mime": mime,
        "size": size,
        "page_count": (pages or 1) if mime == "application/pdf" else 1,
    }
$$;

-- ---------- Procedure: decide the next batch ----------
-- Starts a batch when MIN_READY reports are waiting, or the oldest has waited MAX_WAIT_HOURS.
-- Picks priority first, then oldest first; caps reports AND pages; never more than MAX_ACTIVE
-- batches in flight. Marks the chosen reports QUEUED in one statement, so none is in two batches.
CREATE OR REPLACE PROCEDURE RAW.BUILD_BATCH(
    BATCH_SIZE INT, PAGE_BUDGET INT, MIN_READY INT, MAX_WAIT_HOURS INT, MAX_ACTIVE INT)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    ready_count    INT DEFAULT 0;
    oldest_hours   INT DEFAULT 0;
    active_batches INT DEFAULT 0;
    queued         INT DEFAULT 0;
    new_batch      STRING;
BEGIN
    SELECT COUNT(*), COALESCE(DATEDIFF('hour', MIN(registered_at), CURRENT_TIMESTAMP()), 0)
      INTO :ready_count, :oldest_hours
      FROM RAW.FILE_REGISTRY
     WHERE status = 'READY';

    SELECT COUNT(DISTINCT batch_id)
      INTO :active_batches
      FROM RAW.FILE_REGISTRY
     WHERE status = 'QUEUED';

    IF (ready_count = 0) THEN
        RETURN 'NONE: nothing is READY';
    END IF;
    IF (active_batches >= MAX_ACTIVE) THEN
        RETURN 'NONE: ' || active_batches || ' batches already in flight';
    END IF;
    IF (ready_count < MIN_READY AND oldest_hours < MAX_WAIT_HOURS) THEN
        RETURN 'NONE: only ' || ready_count || ' READY; waiting for ' || MIN_READY;
    END IF;

    new_batch := 'BATCH_' || TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDD_HH24MISS');

    UPDATE RAW.FILE_REGISTRY
       SET status = 'QUEUED',
           batch_id = :new_batch,
           attempts = attempts + 1,
           queued_at = CURRENT_TIMESTAMP(),
           updated_at = CURRENT_TIMESTAMP()
     WHERE status = 'READY'
       AND report_id IN (
           SELECT report_id
             FROM (SELECT report_id,
                          ROW_NUMBER() OVER (ORDER BY priority DESC, registered_at, report_id) AS rn,
                          SUM(COALESCE(page_count, 1)) OVER (
                              ORDER BY priority DESC, registered_at, report_id
                              ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS pages_so_far
                     FROM RAW.FILE_REGISTRY
                    WHERE status = 'READY')
            WHERE rn <= :BATCH_SIZE
              AND (pages_so_far <= :PAGE_BUDGET OR rn = 1));   -- one huge document still gets a batch

    queued := SQLROWCOUNT;
    RETURN new_batch || ' (' || queued || ' reports)';
END;
$$;

SHOW STAGES IN SCHEMA RAW;
