# Manual test plan

Work through these in order on a fresh pipeline (`python -m rxpipe reset --yes`, then
`python -m rxpipe samples`). Tick each one off. All queries run in Snowsight against `RX_DB`.

| # | Stage | Do this | Expected result | How to check |
|---|---|---|---|---|
| M1 | Upload | `upload` | 11 files in `inbox/`, 2 in `_meta/` | Azure portal → container `rx-archive` |
| M2 | Upload | `upload` again | "0 new documents" — originals are never overwritten | CLI output |
| M3 | Load metadata | `load-meta` | 10 manifest rows, 4 patients | `SELECT COUNT(*) FROM RAW.SCAN_MANIFEST` / `RAW.PATIENTS` |
| M4 | Register | `register` | 8 READY, 1 DUPLICATE, 1 PENDING_MANIFEST, 0 UNSUPPORTED | `python -m rxpipe status` |
| M5 | Register | look at the rescan row | `last_error = 'same file as rpt_…'` and the same `file_sha256` as `rx_typed_001.pdf` | `SELECT relative_path, file_sha256, last_error FROM RAW.FILE_REGISTRY` |
| M6 | Register | `register` again | No new rows: the stable `report_id` and the `NOT IN` check prevent re-registration | row count unchanged |
| M7 | Batch | `batch` | one batch of 8; lab reports first (priority 1) | `SELECT relative_path, status, batch_id, priority FROM RAW.FILE_REGISTRY ORDER BY priority DESC` |
| M8 | Batch | set `RX_BATCH_SIZE=3`, `reset`, rerun to M7 with `batch --all` | three batches (3 + 3 + 2) | distinct `batch_id`s |
| M9 | Extract | `extract` | one JSONL in `results/BATCH_…/`; 7 documents read, 1 error | Azure portal; open the file |
| M10 | Load results | `load-results` | 7 RETURNED; corrupt PDF back to READY with `attempts = 1` | `status` |
| M11 | Load results | `load-results` again | Nothing changes (COPY load history) | row counts in `RAW.AI_RESULTS` unchanged |
| M12 | Retry | `batch`, `extract`, `load-results` | corrupt PDF → QUARANTINED, `attempts = 2`, `last_error` filled | `status` |
| M13 | Transform | `transform` | All tests pass; 4 documents `pending` (photo, note, mistyped NHS, unknown drug) | `SELECT source_file, route, review_status, flag_reasons FROM GOLD.FCT_REVIEW_QUEUE` |
| M14 | GOLD | inspect facts | only approved documents in `FCT_DOCUMENT`; lab flags High/Normal correct; frequency expanded ("three times daily") | queries in README Stage 7 |
| M15 | Gate | approve the photo WITHOUT correcting, `transform` | `assert_gold_doses_within_range` FAILS; `outbox` SKIPPED | dbt output; `SELECT COUNT(*) FROM GOLD.OUTBOX` unchanged |
| M16 | Review | `review correct <photo>-0 --dose 500`, `transform` | all tests pass; `FCT_MEDICATION` shows 500 mg, `last_changed_by = reviewer`; outbox gains the photo | `SELECT * FROM GOLD.FCT_MEDICATION` |
| M17 | Audit | look at the events | both the AI's 5000 (op I) and the reviewer's 500 (op U) are kept | `SELECT * FROM RAW.MEDICATION_EVENTS ORDER BY medication_line_id, event_seq` |
| M18 | Reject line | `review reject-line <unknown-drug>-0`, approve the document, `transform` | the Zyntrax line is absent from `FCT_MEDICATION`; a `D` event exists | queries above |
| M19 | SCD2 | README Stage 9 | two versions for patient A; the 2019 prescription keeps Riverside Clinic | README query |
| M20 | Late manifest | README "The late manifest row" | orphan moves PENDING_MANIFEST → READY | `status` |
| M21 | Streamlit | `deploy-app`, open RX_REVIEW, approve the note | decision row in `RAW.REVIEW_DECISIONS` with your Snowflake user | query the table |
| M22 | Security | open a worksheet as a role WITHOUT `RX_ENGINEER` | cannot see `RX_DB` | `USE ROLE PUBLIC; SELECT * FROM RX_DB.GOLD.FCT_MEDICATION;` errors |
