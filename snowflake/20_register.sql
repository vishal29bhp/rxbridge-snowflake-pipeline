-- =====================================================================================
-- 20_register.sql  -  STAGE 3: register new documents and decide which are READY.
--   python -m rxpipe register
--
-- Nothing is copied: the PDFs and images stay in Azure. Snowflake reads each new file
-- once (through the UDF) to fingerprint it.
-- =====================================================================================

-- 3a. Sync the directory table with what is in the Azure folder right now.
--     (With 90_automation.sql this happens automatically on every upload.)
ALTER STAGE RAW.DOCS_STAGE REFRESH;

-- 3b. Register files we have not seen before.
INSERT INTO RAW.FILE_REGISTRY (
    report_id, relative_path, file_sha256, mime_type, file_size, page_count,
    nhs_number, doc_type, clinic, priority, status, batch_id, attempts, last_error,
    registered_at, queued_at, updated_at)
SELECT
    'rpt_' || LEFT(SHA2(n.relative_path, 256), 10)        AS report_id,   -- stable per path
    n.relative_path,
    n.fp:sha256::STRING,
    n.fp:mime::STRING,
    n.fp:size::NUMBER,
    n.fp:page_count::NUMBER,
    m.nhs_number,
    COALESCE(m.doc_type, 'unclassified'),
    m.clinic,
    COALESCE(m.priority, 0),
    CASE
        WHEN n.fp:mime::STRING IS NULL
          OR n.fp:mime::STRING NOT IN ('application/pdf', 'image/jpeg', 'image/png', 'image/tiff')
                                  THEN 'UNSUPPORTED'
        WHEN m.file_name IS NULL  THEN 'PENDING_MANIFEST'      -- we don't know whose it is yet
        ELSE 'READY'
    END,
    NULL, 0, NULL,
    CURRENT_TIMESTAMP(), NULL, CURRENT_TIMESTAMP()
FROM (
    SELECT d.relative_path,
           RAW.FILE_FINGERPRINT(BUILD_SCOPED_FILE_URL(@RAW.DOCS_STAGE, d.relative_path)) AS fp
    FROM DIRECTORY(@RAW.DOCS_STAGE) d
    WHERE d.relative_path NOT IN (SELECT relative_path FROM RAW.FILE_REGISTRY)
) n
LEFT JOIN RAW.SCAN_MANIFEST m ON m.file_name = n.relative_path;

-- 3c. A manifest row can arrive after its file: PENDING_MANIFEST -> READY.
UPDATE RAW.FILE_REGISTRY r
   SET status = 'READY',
       nhs_number = m.nhs_number,
       doc_type = m.doc_type,
       clinic = m.clinic,
       priority = COALESCE(m.priority, 0),
       updated_at = CURRENT_TIMESTAMP()
  FROM RAW.SCAN_MANIFEST m
 WHERE r.relative_path = m.file_name
   AND r.status = 'PENDING_MANIFEST';

-- 3d. De-duplicate BEFORE any AI spend: same bytes for the same patient as an earlier file.
--     The earliest copy (then the alphabetically first path) is the one we keep.
UPDATE RAW.FILE_REGISTRY r
   SET status = 'DUPLICATE',
       last_error = 'same file as ' || e.report_id,
       updated_at = CURRENT_TIMESTAMP()
  FROM (SELECT report_id, relative_path, file_sha256, nhs_number, registered_at
          FROM RAW.FILE_REGISTRY
         WHERE status NOT IN ('DUPLICATE', 'UNSUPPORTED', 'PENDING_MANIFEST')) e
 WHERE r.status = 'READY'
   AND e.report_id <> r.report_id
   AND e.file_sha256 = r.file_sha256
   AND e.nhs_number = r.nhs_number
   AND (e.registered_at < r.registered_at
        OR (e.registered_at = r.registered_at AND e.relative_path < r.relative_path));

-- 3e. What happened
SELECT status, COUNT(*) AS files
FROM RAW.FILE_REGISTRY
GROUP BY status
ORDER BY status;
