import csv

from rxpipe.normalise import nhs_checksum_ok
from rxpipe.samples import DOCS


def test_eleven_documents_are_generated(sample_dir, truth):
    assert len(truth) == 11
    for f in truth:
        assert (sample_dir / f).exists(), f


def test_rescan_is_byte_identical(sample_dir):
    a = (sample_dir / "prescriptions/rx_typed_001.pdf").read_bytes()
    b = (sample_dir / "prescriptions/rx_typed_001_rescan.pdf").read_bytes()
    assert a == b


def test_orphan_is_not_in_manifest(sample_dir):
    rows = list(csv.DictReader(open(sample_dir / "_meta" / "manifest.csv")))
    names = {r["file_name"] for r in rows}
    assert "prescriptions/rx_orphan_009.pdf" not in names
    assert len(rows) == 10


def test_mistyped_nhs_document_has_an_invalid_number(truth):
    assert not nhs_checksum_ok(truth["prescriptions/rx_typed_005.pdf"]["nhs_number"])


def test_patient_list_numbers_are_valid(sample_dir):
    for r in csv.DictReader(open(sample_dir / "_meta" / "patients.csv")):
        assert nhs_checksum_ok(r["nhs_number"]), r


def test_generation_is_deterministic(tmp_path, sample_dir):
    from rxpipe.samples import generate

    generate(tmp_path)
    for d in DOCS:
        if d["kind"] in ("typed_pdf", "corrupt"):
            assert (tmp_path / d["file"]).read_bytes() == (sample_dir / d["file"]).read_bytes(), d["file"]
