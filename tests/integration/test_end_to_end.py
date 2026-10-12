"""INTEGRATION: the whole pipeline against YOUR Azure + Snowflake accounts.

    pytest -m integration -s

Needs a filled-in .env and the one-off setup done (README steps 1-4). It uses the
synthetic documents only. Run it on a fresh RX_DB (or after the reset in README) so the
expected statuses hold.

What it proves, end to end:
  * duplicate, orphan and corrupt files never reach the AI
  * the four risky documents are held for review; nothing unreviewed reaches GOLD
  * a reviewer correction (5000 mg -> 500 mg) + approval flows into fct_medication
  * a patient's clinic change creates a second SCD2 version and the old prescription
    keeps the old clinic
"""

import subprocess
import sys

import pytest

from rxpipe import cli, review
from rxpipe.config import get_settings

pytestmark = pytest.mark.integration


def rxpipe(*args):
    cli.main(list(args))


def dbt_build(regression=False):
    cmd = [sys.executable, "-m", "rxpipe", "transform"] + (["--regression"] if regression else [])
    return subprocess.call(cmd)


@pytest.fixture(scope="module")
def sf():
    from rxpipe.snowflake_client import Snowflake

    conn = Snowflake(get_settings())
    yield conn
    conn.close()


def test_1_pipeline_runs_and_statuses_match(sf):
    rxpipe("samples")
    rxpipe("upload")
    rxpipe("load-meta")
    rxpipe("register")
    for _ in range(2):            # second round retries the corrupt file, then quarantines it
        rxpipe("batch", "--all")
        rxpipe("extract")
        rxpipe("load-results")
    status = {r["relative_path"]: r["status"] for r in sf.query("SELECT relative_path, status FROM raw.file_registry")}
    assert status["prescriptions/rx_typed_001_rescan.pdf"] == "DUPLICATE"
    assert status["prescriptions/rx_orphan_009.pdf"] == "PENDING_MANIFEST"
    assert status["prescriptions/rx_corrupt_007.pdf"] == "QUARANTINED"
    assert status["prescriptions/rx_typed_001.pdf"] == "RETURNED"


def test_2_dbt_build_passes_with_regression_checks():
    assert dbt_build(regression=True) == 0


def test_3_risky_documents_are_held(sf):
    pending = {r["source_file"] for r in review.pending(sf)}
    for f in ("photos/rx_photo_003.jpg", "notes/note_hand_004.png",
              "prescriptions/rx_typed_005.pdf", "prescriptions/rx_typed_006.pdf"):
        assert f in pending, f
    in_gold = {r["source_file"] for r in sf.query("SELECT source_file FROM gold.fct_document")}
    assert not pending & in_gold


def test_4_reviewer_correction_reaches_gold(sf):
    rid = sf.query("SELECT report_id FROM raw.file_registry WHERE relative_path = 'photos/rx_photo_003.jpg'")[0]["report_id"]
    line = f"{rid}-0"
    review.correct_line(sf, line, dose_value=500.0)
    review.decide(sf, rid, "approved", "dose corrected against photo")
    assert dbt_build() == 0
    row = sf.query("SELECT dose_value, last_changed_by FROM gold.fct_medication WHERE medication_line_id = %s", [line])
    assert row and row[0]["dose_value"] == 500 and row[0]["last_changed_by"] == "reviewer"


def test_5_scd2_clinic_move(sf):
    rxpipe("samples", "--move-patient", "A", "Northgate Surgery", "01/07/2021")
    rxpipe("upload")
    rxpipe("load-meta")
    assert dbt_build() == 0
    versions = sf.query("SELECT registered_clinic, valid_from FROM gold.dim_patient "
                        "WHERE nhs_number = '9434765919' ORDER BY version_no")
    assert [v["registered_clinic"] for v in versions] == ["Riverside Clinic", "Northgate Surgery"]
    clinic_2019 = sf.query("""
        SELECT p.registered_clinic FROM gold.fct_medication m JOIN gold.dim_patient p ON p.patient_key = m.patient_key
        JOIN gold.fct_document d ON d.report_id = m.report_id
        WHERE d.source_file = 'prescriptions/rx_typed_001.pdf' LIMIT 1""")
    assert clinic_2019[0]["registered_clinic"] == "Riverside Clinic"   # history keeps the old clinic
