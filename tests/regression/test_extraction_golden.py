"""REGRESSION: read every sample document and compare with the golden set.

The baseline (golden/baseline_scores.json) records how well the reader did when this test
was written. A change to the parser, OCR settings or sample generator that makes ANY
document worse fails the test. If a change makes things better, update the baseline:

    python -m tests.regression.update_baseline
"""

import json
from pathlib import Path

import pytest

from rxpipe.extractors import OfflineReader
from tests.conftest import HAS_TESSERACT
from tests.regression.scoring import score

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN = json.loads((GOLDEN_DIR / "extraction_golden.json").read_text())
BASELINE = json.loads((GOLDEN_DIR / "baseline_scores.json").read_text())
MIME = {".pdf": "application/pdf", ".jpg": "image/jpeg", ".png": "image/png", ".tif": "image/tiff"}

pytestmark = pytest.mark.skipif(not HAS_TESSERACT, reason="Tesseract not installed (see README)")

CASES = [(f, step) for f in GOLDEN for step in ("extract", "verify")]


@pytest.mark.parametrize("file,step", CASES, ids=[f"{f}::{s}" for f, s in CASES])
def test_no_document_reads_worse_than_baseline(sample_dir, file, step):
    gold = GOLDEN[file]
    res = OfflineReader().read((sample_dir / file).read_bytes(), MIME[Path(file).suffix], gold["doc_type"], step)
    got, misses = score(res.doc, gold)
    assert got >= BASELINE[f"{file}::{step}"] - 0.001, f"accuracy fell to {got:.3f}: {misses}"


def test_typed_pdfs_are_read_perfectly(sample_dir):
    """Text-layer PDFs involve no OCR, so anything below 100% is a parser bug."""
    for file, gold in GOLDEN.items():
        if file.startswith(("prescriptions/", "lab/")):
            res = OfflineReader().read((sample_dir / file).read_bytes(), "application/pdf", gold["doc_type"], "extract")
            got, misses = score(res.doc, gold)
            assert got == 1.0, f"{file}: {misses}"


def test_the_dose_error_is_read_faithfully(sample_dir):
    """The photo really says 5000 mg. The reader must report what's on the page;
    catching the error is dbt's job (dose range check), not the reader's."""
    res = OfflineReader().read((sample_dir / "photos/rx_photo_003.jpg").read_bytes(), "image/jpeg",
                               "prescription", "extract")
    assert res.doc["medications"][0]["dose_value"] == 5000
