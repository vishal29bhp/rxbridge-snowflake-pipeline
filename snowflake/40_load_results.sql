-- =====================================================================================
-- 40_load_results.sql  -  STAGE 6: load the AI's JSON results and move statuses on.
--   python -m rxpipe load-results
--
-- Needs the session variable $max_attempts (the CLI sets it from RX_MAX_ATTEMPTS).
-- =====================================================================================

-- 6a. Load every new results file. COPY remembers what it has loaded, so re-running
--     this never loads the same file twice (that is what makes the step idempotent).
COPY INTO RAW.AI_RESULTS (batch_id, report_id, step, extractor, model, payload, error, _source_file, _loaded_at)
FROM (
    SELECT $1:batch_id::STRING,
           $1:report_id::STRING,
           $1:step::STRING,
           $1:extractor::STRING,
           $1:model::STRING,
           $1,                              -- the whole line, kept as VARIANT
           $1:error::STRING,
           METADATA$FILENAME,
           CURRENT_TIMESTAMP()
    FROM @RAW.RESULTS_STAGE
)
FILE_FORMAT = (FORMAT_NAME = 'RAW.FF_JSON')
ON_ERROR = 'CONTINUE';                      -- one bad line never blocks the rest of the file

-- 6b. Success: the report has an 'extract' result for its current batch -> RETURNED.
UPDATE RAW.FILE_REGISTRY r
   SET status = 'RETURNED', last_error = NULL, updated_at = CURRENT_TIMESTAMP()
  FROM (SELECT DISTINCT report_id, batch_id FROM RAW.AI_RESULTS WHERE step = 'extract') a
 WHERE r.status = 'QUEUED'
   AND a.report_id = r.report_id
   AND a.batch_id = r.batch_id;

-- 6c. Failure: retry once (back to READY), then QUARANTINED for a person to look at.
UPDATE RAW.FILE_REGISTRY r
   SET status = IFF(r.attempts >= $max_attempts, 'QUARANTINED', 'READY'),
       last_error = a.error,
       updated_at = CURRENT_TIMESTAMP()
  FROM (SELECT report_id, batch_id, MAX(error) AS error
          FROM RAW.AI_RESULTS WHERE step = 'error' GROUP BY report_id, batch_id) a
 WHERE r.status = 'QUEUED'
   AND a.report_id = r.report_id
   AND a.batch_id = r.batch_id;

-- 6d. Every medication the AI read becomes an 'I' event (reviewers later add 'U' / 'D').
INSERT INTO RAW.MEDICATION_EVENTS (
    medication_line_id, report_id, batch_id, op, source, drug_name, dose_value, dose_unit,
    frequency, duration_days, quantity, event_ts, event_seq)
SELECT x.report_id || '-' || x.line_no,
       x.report_id,
       x.batch_id,
       'I',
       'ai',
       x.med:drug_name::STRING,
       x.med:dose_value::FLOAT,
       x.med:dose_unit::STRING,
       x.med:frequency::STRING,
       x.med:duration_days::NUMBER,
       x.med:quantity::FLOAT,
       x._loaded_at,
       COALESCE(prev.max_seq, 0) + 1
FROM (
    SELECT a.report_id, a.batch_id, a._loaded_at, m.index AS line_no, m.value AS med
    FROM RAW.AI_RESULTS a,
         LATERAL FLATTEN(input => a.payload:doc:medications) m
    WHERE a.step = 'extract'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY a.report_id, a.batch_id, m.index
                               ORDER BY a._loaded_at DESC, a._source_file DESC) = 1
) x
LEFT JOIN (SELECT report_id, MAX(event_seq) AS max_seq
             FROM RAW.MEDICATION_EVENTS GROUP BY report_id) prev
       ON prev.report_id = x.report_id
WHERE NOT EXISTS (SELECT 1 FROM RAW.MEDICATION_EVENTS e
                   WHERE e.report_id = x.report_id AND e.batch_id = x.batch_id AND e.op = 'I');

-- 6e. What happened
SELECT status, COUNT(*) AS files
FROM RAW.FILE_REGISTRY
GROUP BY status
ORDER BY status;
