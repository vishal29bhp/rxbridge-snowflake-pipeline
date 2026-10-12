"""AzureReader with the Document Intelligence client replaced by a fake."""

from types import SimpleNamespace

import pytest

from rxpipe import extractors
from rxpipe.ocr import UnreadableDocument

PAGE = "Patient: Rahul Verma\nNHS No: 485 777 3457\nDate: 22/01/2024\nRx: Salbutamol inhaler 200 mcg PRN"


class FakePoller:
    def __init__(self, result):
        self._result = result

    def result(self):
        return self._result


def make_reader(monkeypatch, content, styles=None):
    calls = []

    class FakeClient:
        def __init__(self, endpoint, credential):
            pass

        def begin_analyze_document(self, model_id, body):
            calls.append(model_id)
            return FakePoller(SimpleNamespace(content=content, styles=styles or []))

    import azure.ai.documentintelligence as di

    monkeypatch.setattr(di, "DocumentIntelligenceClient", FakeClient)
    return extractors.AzureReader("https://x", "key", "prebuilt-read", "prebuilt-layout"), calls


def test_extract_and_verify_use_different_models(monkeypatch):
    reader, calls = make_reader(monkeypatch, PAGE)
    reader.read(b"x", "image/png", "handwritten_note", "extract")
    reader.read(b"x", "image/png", "handwritten_note", "verify")
    assert calls == ["prebuilt-read", "prebuilt-layout"]


def test_handwriting_style_forces_handwriting_flag(monkeypatch):
    reader, _ = make_reader(monkeypatch, PAGE, styles=[SimpleNamespace(is_handwritten=True)])
    res = reader.read(b"x", "application/pdf", "prescription", "extract")
    assert res.doc["has_handwriting"] is True
    assert res.method == "azure:prebuilt-read"


def test_no_text_is_unreadable(monkeypatch):
    reader, _ = make_reader(monkeypatch, "   ")
    with pytest.raises(UnreadableDocument):
        reader.read(b"x", "application/pdf", "prescription", "extract")
