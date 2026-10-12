-- =====================================================================================
-- 95_review_app.sql  -  deploy the review queue as a Streamlit in Snowflake app.
--   python -m rxpipe deploy-app        (uploads review_app.py, then runs this)
-- =====================================================================================
USE ROLE RX_ENGINEER;
USE DATABASE RX_DB;

CREATE OR REPLACE STREAMLIT RX_DB.RAW.RX_REVIEW
  ROOT_LOCATION = '@RX_DB.RAW.APP_STAGE/review'
  MAIN_FILE = 'review_app.py'
  QUERY_WAREHOUSE = RX_APP_WH
  TITLE = 'RxBridge review queue';
