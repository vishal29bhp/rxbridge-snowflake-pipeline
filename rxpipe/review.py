"""STAGE 8 - HUMAN REVIEW from the command line (same actions as the Streamlit app in snowflake/).

Reviewers never edit GOLD. Every decision is APPENDED to RAW:
  approve / reject a whole document   -> RAW.REVIEW_DECISIONS
  correct / reject one medication     -> RAW.MEDICATION_EVENTS ('U' or 'D')
Then `python -m rxpipe transform` rebuilds GOLD and dbt's tests check the result.
"""

from __future__ import annotations

import getpass
import uuid


def reviewer() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "reviewer"


def pending(sf) -> list[dict]:
    return sf.query(
        """
        SELECT report_id, doc_type, route, flag_reasons, source_file
        FROM gold.fct_review_queue
        WHERE review_status = 'pending'
        ORDER BY route DESC, report_id
        """
    )


def show(sf, report_id: str) -> dict:
    one = lambda sql: (sf.query(sql, [report_id]) or [None])[0]  # noqa: E731
    return {
        "queue": one("SELECT route, flag_reasons, review_status FROM gold.fct_review_queue WHERE report_id = %s"),
        "document": one(
            "SELECT doc_type, nhs_number, patient_name, document_date, prescriber_name, prescriber_clinic, "
            "read_method, model, summary, LEFT(raw_text, 1500) AS raw_text "
            "FROM staging.stg_documents WHERE report_id = %s"
        ),
        "medications": sf.query(
            "SELECT medication_line_id, drug_name, dose_value, dose_unit, frequency, duration_days, quantity, "
            "last_changed_by FROM intermediate.int_medication_lines WHERE report_id = %s "
            "ORDER BY medication_line_id",
            [report_id],
        ),
        "lab_results": sf.query(
            "SELECT lab_result_id, test_name_read, result_value, unit, ref_low, ref_high, flag "
            "FROM intermediate.int_lab_results WHERE report_id = %s ORDER BY lab_result_id",
            [report_id],
        ),
    }


def decide(sf, report_id: str, decision: str, note: str | None = None) -> None:
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'")
    sf.execute(
        "INSERT INTO raw.review_decisions (review_id, report_id, reviewer, decision, reviewed_at, note) "
        "SELECT %s, %s, %s, %s, CURRENT_TIMESTAMP(), %s",
        [str(uuid.uuid4()), report_id, reviewer(), decision, note],
    )


def _latest_event(sf, line_id: str) -> dict:
    rows = sf.query(
        "SELECT * FROM raw.medication_events WHERE medication_line_id = %s "
        "ORDER BY event_seq DESC, event_ts DESC LIMIT 1",
        [line_id],
    )
    if not rows:
        raise SystemExit(f"No medication line {line_id}")
    return rows[0]


def correct_line(sf, line_id: str, **changes) -> None:
    """Append a 'U' event: the line's latest values with the reviewer's changes applied."""
    last = _latest_event(sf, line_id)
    last.update({k: v for k, v in changes.items() if v is not None})
    sf.execute(
        "INSERT INTO raw.medication_events (medication_line_id, report_id, batch_id, op, source, drug_name, "
        "dose_value, dose_unit, frequency, duration_days, quantity, event_ts, event_seq) "
        "SELECT %s, %s, %s, 'U', 'reviewer', %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP(), %s",
        [line_id, last["report_id"], last["batch_id"], last["drug_name"], last["dose_value"],
         last["dose_unit"], last["frequency"], last["duration_days"], last["quantity"],
         int(last["event_seq"]) + 1],
    )


def reject_line(sf, line_id: str) -> None:
    """Append a 'D' event: this line was misread and must not reach a patient's history."""
    last = _latest_event(sf, line_id)
    sf.execute(
        "INSERT INTO raw.medication_events (medication_line_id, report_id, batch_id, op, source, event_ts, event_seq) "
        "SELECT %s, %s, %s, 'D', 'reviewer', CURRENT_TIMESTAMP(), %s",
        [line_id, last["report_id"], last["batch_id"], int(last["event_seq"]) + 1],
    )
