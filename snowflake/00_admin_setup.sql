-- =====================================================================================
-- 00_admin_setup.sql  -  run ONCE, as ACCOUNTADMIN, in a Snowsight worksheet.
--
-- Get a copy with your values filled in:   python -m rxpipe render-sql 00_admin_setup.sql
-- (it replaces <<AZURE_TENANT_ID>>, <<AZURE_STORAGE_ACCOUNT>>, <<AZURE_CONTAINER>>, <<SNOWFLAKE_USER>>)
--
-- Creates: role RX_ENGINEER, three warehouses (one per workload), database RX_DB,
-- and the storage integration that lets Snowflake read your Azure Blob container.
-- =====================================================================================

USE ROLE ACCOUNTADMIN;

-- 1. One role for this project. You (and the pipeline) use it for everything after this script.
CREATE ROLE IF NOT EXISTS RX_ENGINEER;
GRANT ROLE RX_ENGINEER TO USER <<SNOWFLAKE_USER>>;
GRANT ROLE RX_ENGINEER TO ROLE SYSADMIN;               -- keep the role hierarchy rooted

-- 2. Separate warehouses so loading, dbt and the review app never slow each other down.
CREATE WAREHOUSE IF NOT EXISTS RX_LOAD_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE WAREHOUSE IF NOT EXISTS RX_TRANSFORM_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE WAREHOUSE IF NOT EXISTS RX_APP_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  STATEMENT_TIMEOUT_IN_SECONDS = 600;
GRANT USAGE, OPERATE ON WAREHOUSE RX_LOAD_WH      TO ROLE RX_ENGINEER;
GRANT USAGE, OPERATE ON WAREHOUSE RX_TRANSFORM_WH TO ROLE RX_ENGINEER;
GRANT USAGE, OPERATE ON WAREHOUSE RX_APP_WH       TO ROLE RX_ENGINEER;

-- Cost guard for a trial account: notify at 80%, stop at 100% of 20 credits a month.
CREATE RESOURCE MONITOR IF NOT EXISTS RX_MONITOR WITH CREDIT_QUOTA = 20 FREQUENCY = MONTHLY
  START_TIMESTAMP = IMMEDIATELY
  TRIGGERS ON 80 PERCENT DO NOTIFY ON 100 PERCENT DO SUSPEND;
ALTER WAREHOUSE RX_LOAD_WH      SET RESOURCE_MONITOR = RX_MONITOR;
ALTER WAREHOUSE RX_TRANSFORM_WH SET RESOURCE_MONITOR = RX_MONITOR;
ALTER WAREHOUSE RX_APP_WH       SET RESOURCE_MONITOR = RX_MONITOR;

-- 3. The project database, owned by the project role (so it can create schemas, stages, apps).
CREATE DATABASE IF NOT EXISTS RX_DB;
GRANT OWNERSHIP ON DATABASE RX_DB TO ROLE RX_ENGINEER COPY CURRENT GRANTS;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE RX_ENGINEER;        -- only needed for 90_automation.sql

-- 4. Storage integration: Snowflake's identity in your Azure tenant.
--    No keys are stored in Snowflake; Azure grants access to Snowflake's app instead.
CREATE STORAGE INTEGRATION IF NOT EXISTS RX_AZURE_INT
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'AZURE'
  ENABLED = TRUE
  AZURE_TENANT_ID = '<<AZURE_TENANT_ID>>'
  STORAGE_ALLOWED_LOCATIONS = ('azure://<<AZURE_STORAGE_ACCOUNT>>.blob.core.windows.net/<<AZURE_CONTAINER>>/');

GRANT USAGE ON INTEGRATION RX_AZURE_INT TO ROLE RX_ENGINEER;

-- 5. Read the two values you need for the Azure side (see README, step 3):
--      AZURE_CONSENT_URL           -> open it in a browser and click Accept
--      AZURE_MULTI_TENANT_APP_NAME -> the app to give "Storage Blob Data Reader" on the storage account
DESC STORAGE INTEGRATION RX_AZURE_INT;
