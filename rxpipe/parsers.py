"""STAGE 2b - STRUCTURE: turn a document's text into fields.

This is the offline, rule-based "extractor". In production the same job is done by an
LLM (Azure OpenAI or Gemini) with a JSON schema; the output shape below is identical,
so everything downstream (validation, dbt, tests) does not change.

Every extracted line keeps `source_quote`: the exact text it came from. dbt later checks
that each quote really appears in the page text - the hallucination guard for LLMs.
"""

from __future__ import annotations

import re

from .normalise import nhs_digits, normalise_unit, parse_uk_date, squash_ws

PROMPT_VERSION = "rules-v1"

_HEADER = {
    "patient_name": re.compile(r"Patient\s*(?:name)?\s*[:;]\s*(.+)", re.I),
    "nhs_number": re.compile(r"NHS\s*(?:No|Number)?\.?\s*[:;]?\s*([0-9][0-9 ]{8,14}[0-9])", re.I),
    "document_date": re.compile(r"\bDate\s*[:;]\s*([0-9]{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4})", re.I),
    "prescriber_name": re.compile(r"(?:Prescriber|Clinician|Doctor)\s*[:;]\s*(.+)", re.I),
    "clinic": re.compile(r"Clinic\s*[:;]\s*(.+)", re.I),
}

# "1. Amoxicillin 500mg capsules  Dose: 500 mg  Freq: TDS  Days: 7  Qty: 21"
_RX_LINE = re.compile(
    r"(?:^|\s)(?:\d+[.)]\s*)?(?P<drug>[A-Za-z][A-Za-z0-9 ./%-]*?)\s+"
    r"Dose\s*[:;]?\s*(?P<dose>\d+(?:[.,]\d+)?)\s*(?P<unit>[A-Za-zµ]+)\s+"
    r"Freq\s*[:;]?\s*(?P<freq>[A-Za-z ]+?)\s+"
    r"Days\s*[:;]?\s*(?P<days>\d+)\s+"
    r"Qty\s*[:;]?\s*(?P<qty>\d+(?:\.\d+)?)",
    re.I,
)

# Handwritten notes: "Rx: Salbutamol inhaler 200 mcg PRN"
_NOTE_RX = re.compile(
    r"Rx\s*[:;]\s*(?P<drug>[A-Za-z][A-Za-z0-9 ./-]*?)\s+(?P<dose>\d+(?:[.,]\d+)?)\s*(?P<unit>mg|mcg|ug|microgram|g|ml)\b\s*"
    r"(?P<freq>(?:OD|BD|TDS|QDS|PRN|ON|NOCTE)(?:\s+(?:PRN))?)?",
    re.I,
)

# "HbA1c  52  mmol/mol  Ref: 20-41"   |   "Total cholesterol 5.8 mmol/L Ref: <5.0"
_LAB_LINE = re.compile(
    r"^(?P<test>[A-Za-z][A-Za-z0-9 ]*?)\s+(?P<value>\d+(?:\.\d+)?)\s+(?P<unit>\S+)\s+Ref\s*[:;]?\s*"
    r"(?:(?P<low>\d+(?:\.\d+)?)\s*[-–]\s*(?P<high>\d+(?:\.\d+)?)|<\s*(?P<lt>\d+(?:\.\d+)?)|>\s*(?P<gt>\d+(?:\.\d+)?))",
    re.I,
)


def _num(s: str | None) -> float | None:
    return float(s.replace(",", ".")) if s else None


def _header(text: str) -> dict:
    out = {}
    for key, rx in _HEADER.items():
        m = rx.search(text)
        out[key] = squash_ws(m.group(1)) if m else None
    out["nhs_number"] = nhs_digits(out["nhs_number"])
    out["document_date"] = parse_uk_date(out["document_date"])
    return out


def parse_prescription(text: str) -> list[dict]:
    meds = []
    for line in text.splitlines():
        m = _RX_LINE.search(line)
        if not m:
            continue
        meds.append(
            {
                "drug_name": squash_ws(m["drug"]),
                "dose_value": _num(m["dose"]),
                "dose_unit": normalise_unit(m["unit"]),
                "frequency": squash_ws(m["freq"]).lower(),
                "duration_days": int(m["days"]),
                "quantity": _num(m["qty"]),
                "source_quote": squash_ws(line),
            }
        )
    return meds


def parse_note_medications(text: str) -> list[dict]:
    meds = []
    for line in text.splitlines():
        m = _NOTE_RX.search(line)
        if not m:
            continue
        meds.append(
            {
                "drug_name": squash_ws(m["drug"]),
                "dose_value": _num(m["dose"]),
                "dose_unit": normalise_unit(m["unit"]),
                "frequency": squash_ws(m["freq"] or "").lower() or None,
                "duration_days": None,
                "quantity": None,
                "source_quote": squash_ws(line),
            }
        )
    return meds


def parse_lab_report(text: str) -> list[dict]:
    results = []
    for line in text.splitlines():
        m = _LAB_LINE.search(line.strip())
        if not m:
            continue
        results.append(
            {
                "test_name": squash_ws(m["test"]),
                "result_value": _num(m["value"]),
                "unit": m["unit"],
                "ref_low": _num(m["low"]) if m["low"] else _num(m["gt"]),
                "ref_high": _num(m["high"]) if m["high"] else _num(m["lt"]),
                "source_quote": squash_ws(line),
            }
        )
    return results


def _summary(text: str) -> str:
    """For notes: the free-text body, without the header lines."""
    keep = [
        ln for ln in text.splitlines()
        if ln.strip() and not any(rx.search(ln) for rx in _HEADER.values())
    ]
    return squash_ws(" ".join(keep))[:1000]


def structure(text: str, doc_type: str) -> dict:
    """The single entry point. Output shape = what an LLM would be asked to return."""
    head = _header(text)
    doc = {
        "doc_type": doc_type,
        "prompt_version": PROMPT_VERSION,
        "patient": {"nhs_number": head["nhs_number"], "name": head["patient_name"]},
        "document_date": head["document_date"].isoformat() if head["document_date"] else None,
        "prescriber": {"name": head["prescriber_name"], "clinic": head["clinic"]},
        "has_handwriting": doc_type == "handwritten_note",
        "summary": None,
        "medications": [],
        "lab_results": [],
    }
    if doc_type == "prescription":
        doc["medications"] = parse_prescription(text)
    elif doc_type == "lab_report":
        doc["lab_results"] = parse_lab_report(text)
    elif doc_type == "handwritten_note":
        doc["medications"] = parse_note_medications(text)
        doc["summary"] = _summary(text)
    return doc
