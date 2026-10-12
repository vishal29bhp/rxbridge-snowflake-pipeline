-- =====================================================================================
-- 90_automation.sql  -  OPTIONAL. Turn the manual steps into automatic ones.
-- Do the manual walkthrough first (README); come back here when every step makes sense.
--
-- Azure side first (README "Automation"): create a Storage Queue and an Event Grid
-- subscription on the storage account that sends "Blob Created" events to that queue.
-- =====================================================================================

USE ROLE ACCOUNTADMIN;

-- A. Snowflake listens to the Azure Storage Queue that Event Grid writes to.
CREATE NOTIFICATION INTEGRATION IF NOT EXISTS RX_AZURE_EVENTS
  ENABLED = TRUE
  TYPE = QUEUE
  NOTIFICATION_PROVIDER = AZURE_STORAGE_QUEUE
  AZURE_STORAGE_QUEUE_PRIMARY_URI = 'https://<<AZURE_STORAGE_ACCOUNT>>.queue.core.windows.net/<<AZURE_QUEUE>>'
  AZURE_TENANT_ID = '<<AZURE_TENANT_ID>>';
GRANT USAGE ON INTEGRATION RX_AZURE_EVENTS TO ROLE RX_ENGINEER;
DESC NOTIFICATION INTEGRATION RX_AZURE_EVENTS;   -- consent URL + app: grant "Storage Queue Data Contributor"

USE ROLE RX_ENGINEER;
USE DATABASE RX_DB;
USE SCHEMA RAW;

-- B. The directory table refreshes itself on every upload (no more ALTER STAGE ... REFRESH).
ALTER STAGE RAW.DOCS_STAGE SET DIRECTORY = (ENABLE = TRUE AUTO_REFRESH = TRUE);

-- C. Snowpipe: load each results file as soon as Python writes it (replaces step 6a).
CREATE PIPE IF NOT EXISTS RAW.P_AI_RESULTS
  AUTO_INGEST = TRUE
  INTEGRATION = 'RX_AZURE_EVENTS'
AS
COPY INTO RAW.AI_RESULTS (batch_id, report_id, step, extractor, model, payload, error, _source_file, _loaded_at)
FROM (
    SELECT $1:batch_id::STRING, $1:report_id::STRING, $1:step::STRING, $1:extractor::STRING,
           $1:model::STRING, $1, $1:error::STRING, METADATA$FILENAME, CURRENT_TIMESTAMP()
    FROM @RAW.RESULTS_STAGE
)
FILE_FORMAT = (FORMAT_NAME = 'RAW.FF_JSON')
ON_ERROR = 'CONTINUE';

-- D. Task: try to build a batch every 15 minutes.
--    (Registration: run `python -m rxpipe register` on the same schedule, or wrap
--     20_register.sql in a stored procedure and call it from a task before this one.)
--    Production thresholds: 5,000 reports or 6 hours waiting, 15,000 pages, 4 batches in flight.
CREATE OR REPLACE TASK RAW.T_BUILD_BATCH
  WAREHOUSE = RX_LOAD_WH
  SCHEDULE = '15 MINUTE'
AS
  CALL RAW.BUILD_BATCH(5000, 15000, 5000, 6, 4);

ALTER TASK RAW.T_BUILD_BATCH RESUME;

-- The Python extract step runs outside Snowflake (laptop cron, Azure Container Apps job,
-- or an Azure Function on a timer): `python -m rxpipe extract`.
-- dbt runs on a schedule too (dbt Cloud, GitHub Actions, or `EXECUTE DBT PROJECT`).
