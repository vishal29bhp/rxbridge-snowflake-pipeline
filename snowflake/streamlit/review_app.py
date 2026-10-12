"""RxBridge review queue - Streamlit in Snowflake.

Reviewers see each document that needs a person, with what the AI read next to the
page text and the reasons it was flagged. Every action APPENDS a row to RAW
(review_decisions / medication_events); GOLD is rebuilt by dbt and re-tested.
All SQL uses bind parameters: nothing a user types is pasted into SQL.
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
st.title("RxBridge review queue")


def rows(sql, params=None):
    return [r.as_dict() for r in session.sql(sql, params=params or []).collect()]


queue = rows(
    """SELECT report_id, doc_type, route, flag_reasons, source_file
       FROM RX_DB.GOLD.FCT_REVIEW_QUEUE
       WHERE review_status = 'pending'
       ORDER BY route DESC, report_id"""
)
st.caption(f"{len(queue)} document(s) waiting. Rebuild with `python -m rxpipe transform` after reviewing.")
if not queue:
    st.success("Nothing to review.")
    st.stop()

labels = {f"{q['REPORT_ID']} - {q['DOC_TYPE']} - {q['ROUTE']}": q for q in queue}
choice = labels[st.selectbox("Document", list(labels))]
rid = choice["REPORT_ID"]

st.warning(f"Why it's here: {choice['FLAG_REASONS']}")
doc = rows(
    """SELECT nhs_number, patient_name, document_date, prescriber_name, read_method, model, summary, raw_text
       FROM RX_DB.STAGING.STG_DOCUMENTS WHERE report_id = ?""", [rid])[0]

left, right = st.columns(2)
with left:
    st.subheader("What the AI read")
    st.write({k: doc[k] for k in ("NHS_NUMBER", "PATIENT_NAME", "DOCUMENT_DATE", "PRESCRIBER_NAME", "MODEL")})
    if doc["SUMMARY"]:
        st.write(doc["SUMMARY"])
with right:
    st.subheader("Page text")
    st.text_area("raw", doc["RAW_TEXT"], height=260, label_visibility="collapsed")
    st.caption(f"Original file: {choice['SOURCE_FILE']} (in Azure Blob, inbox/)")

meds = rows(
    """SELECT medication_line_id, drug_name, dose_value, dose_unit, frequency, last_changed_by
       FROM RX_DB.INTERMEDIATE.INT_MEDICATION_LINES WHERE report_id = ? ORDER BY medication_line_id""", [rid])
if meds:
    st.subheader("Medications")
    for m in meds:
        c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
        c1.write(f"**{m['DRUG_NAME']}** - {m['FREQUENCY']}  \n_{m['MEDICATION_LINE_ID']}, last change: {m['LAST_CHANGED_BY']}_")
        new_dose = c2.number_input("dose", value=float(m["DOSE_VALUE"] or 0), key=f"d{m['MEDICATION_LINE_ID']}")
        new_unit = c3.text_input("unit", value=m["DOSE_UNIT"] or "", key=f"u{m['MEDICATION_LINE_ID']}")
        if c4.button("Save correction", key=f"s{m['MEDICATION_LINE_ID']}"):
            session.sql(
                """INSERT INTO RX_DB.RAW.MEDICATION_EVENTS
                     (medication_line_id, report_id, batch_id, op, source, drug_name, dose_value, dose_unit,
                      frequency, duration_days, quantity, event_ts, event_seq)
                   SELECT medication_line_id, report_id, batch_id, 'U', 'reviewer', drug_name, ?, ?,
                          frequency, duration_days, quantity, CURRENT_TIMESTAMP(), event_seq + 1
                   FROM RX_DB.RAW.MEDICATION_EVENTS
                   WHERE medication_line_id = ?
                   QUALIFY ROW_NUMBER() OVER (ORDER BY event_seq DESC) = 1""",
                params=[new_dose, new_unit, m["MEDICATION_LINE_ID"]],
            ).collect()
            st.toast("Correction saved")

note = st.text_input("Note (optional)")
a, r = st.columns(2)
for col, decision in ((a, "approved"), (r, "rejected")):
    if col.button(decision.capitalize(), type="primary" if decision == "approved" else "secondary"):
        session.sql(
            """INSERT INTO RX_DB.RAW.REVIEW_DECISIONS (review_id, report_id, reviewer, decision, reviewed_at, note)
               SELECT UUID_STRING(), ?, CURRENT_USER(), ?, CURRENT_TIMESTAMP(), ?""",
            params=[rid, decision, note],
        ).collect()
        st.success(f"{rid} {decision}. Run `python -m rxpipe transform` to rebuild GOLD.")
