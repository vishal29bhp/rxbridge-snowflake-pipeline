"""STAGE 5 - READ each document twice, independently.

  extract  - Azure Document Intelligence model RX_EXTRACT_MODEL (default 'prebuilt-read')
  verify   - a DIFFERENT model, RX_VERIFY_MODEL (default 'prebuilt-layout')

Two different models reading the same page is the "cross-model check": dbt later
compares their medications field by field, and any disagreement sends the report to
a human. Using the same model twice would repeat the same mistakes.

The text from each read is turned into fields by parsers.structure(), so both reads
produce the same JSON shape. RX_READER=offline swaps Azure for Tesseract on your
laptop (free; used by the unit and regression tests).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from . import ocr
from .normalise import squash_ws
from .parsers import structure


@dataclass
class ReadResult:
    doc: dict          # structured fields (parsers.structure)
    raw_text: str      # full page text; dbt checks every source_quote against it
    method: str        # e.g. 'azure:prebuilt-read', 'text_layer', 'ocr'
    model: str


class OfflineReader:
    """Tesseract + PDF text layer. Primary and secondary reads use different paths/settings."""

    name = "offline"

    def read(self, data: bytes, mime: str, doc_type: str, step: str) -> ReadResult:
        if step == "extract":
            text, method = ocr.read_primary(data, mime)
            model = "tesseract-psm6" if method == "ocr" else "pdf-text-layer"
        else:
            text, method, model = ocr.read_secondary(data, mime), "ocr", "tesseract-psm4"
        return ReadResult(structure(text, doc_type), squash_ws(text), method, model)


class AzureReader:
    """Azure AI Document Intelligence. Handles typed text, scans, photos and handwriting."""

    name = "azure-document-intelligence"

    def __init__(self, endpoint: str, key: str, extract_model: str, verify_model: str):
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        self.client = DocumentIntelligenceClient(endpoint, AzureKeyCredential(key))
        self.models = {"extract": extract_model, "verify": verify_model}

    def read(self, data: bytes, mime: str, doc_type: str, step: str) -> ReadResult:
        model = self.models[step]
        result = self.client.begin_analyze_document(model, body=io.BytesIO(data)).result()
        text = result.content or ""
        if not text.strip():
            raise ocr.UnreadableDocument(f"{model} returned no text")
        doc = structure(text, doc_type)
        # Document Intelligence marks handwritten spans. Any handwriting forces full review.
        if any(getattr(s, "is_handwritten", False) for s in (result.styles or [])):
            doc["has_handwriting"] = True
        return ReadResult(doc, squash_ws(text), f"azure:{model}", model)


def get_reader(settings):
    if settings.reader == "offline":
        return OfflineReader()
    if not (settings.azure_di_endpoint and settings.azure_di_key):
        raise SystemExit("Set AZURE_DI_ENDPOINT and RX_KEY_VAULT_URL in .env (key: azure-di-key in Key Vault), or use RX_READER=offline.")
    return AzureReader(settings.azure_di_endpoint, settings.azure_di_key,
                       settings.extract_model, settings.verify_model)
