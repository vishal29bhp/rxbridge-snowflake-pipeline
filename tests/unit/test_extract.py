"""The extract step with a fake reader: no Azure, no Snowflake."""

from rxpipe.extract import result_lines
from rxpipe.extractors import ReadResult
from rxpipe.ocr import UnreadableDocument

REPORT = {"report_id": "rpt_1", "batch_id": "BATCH_1", "mime_type": "application/pdf", "doc_type": "prescription"}


class FakeReader:
    name = "fake"

    def __init__(self, fail=False):
        self.fail, self.calls = fail, []

    def read(self, data, mime, doc_type, step):
        self.calls.append(step)
        if self.fail:
            raise UnreadableDocument("cannot open PDF")
        return ReadResult({"doc_type": doc_type, "medications": []}, "page text", "test", f"model-{step}")


def test_success_writes_extract_and_verify_lines():
    reader = FakeReader()
    lines = result_lines(REPORT, b"%PDF-1.4 ...", reader)
    assert [x["step"] for x in lines] == ["extract", "verify"]
    assert reader.calls == ["extract", "verify"]
    assert {x["model"] for x in lines} == {"model-extract", "model-verify"}   # two different models
    assert all(x["report_id"] == "rpt_1" and x["batch_id"] == "BATCH_1" for x in lines)


def test_failure_becomes_one_error_line_not_an_exception():
    lines = result_lines(REPORT, b"%PDF", FakeReader(fail=True))
    assert len(lines) == 1 and lines[0]["step"] == "error"
    assert "cannot open PDF" in lines[0]["error"]


def test_empty_file_is_an_error():
    lines = result_lines(REPORT, b"", FakeReader())
    assert lines[0]["step"] == "error" and "empty file" in lines[0]["error"]


def test_download_error_is_reported():
    lines = result_lines({**REPORT, "_download_error": "BlobNotFound"}, b"", FakeReader())
    assert "BlobNotFound" in lines[0]["error"]
