from rxpipe.parsers import parse_lab_report, parse_note_medications, parse_prescription, structure

RX = """RIVERSIDE CLINIC
PRESCRIPTION
Patient: Asha Patel
NHS No: 943 476 5919
Date: 03/04/2019
Prescriber: Dr A Mehta
Clinic: Riverside Clinic
1. Amoxicillin 500mg capsules   Dose: 500 mg   Freq: TDS   Days: 7   Qty: 21
2. Paracetamol 500mg tablets   Dose: 1000 mg   Freq: QDS PRN   Days: 5   Qty: 32
"""


def test_prescription_header_and_lines():
    doc = structure(RX, "prescription")
    assert doc["patient"] == {"nhs_number": "9434765919", "name": "Asha Patel"}
    assert doc["document_date"] == "2019-04-03"
    assert doc["prescriber"] == {"name": "Dr A Mehta", "clinic": "Riverside Clinic"}
    first, second = doc["medications"]
    assert first["drug_name"] == "Amoxicillin 500mg capsules"
    assert (first["dose_value"], first["dose_unit"], first["frequency"]) == (500, "mg", "tds")
    assert (first["duration_days"], first["quantity"]) == (7, 21)
    assert second["frequency"] == "qds prn"


def test_every_line_keeps_its_source_quote():
    for m in parse_prescription(RX):
        assert m["source_quote"] in " ".join(RX.split())


def test_lab_reference_ranges_all_three_forms():
    text = ("HbA1c   52   mmol/mol   Ref: 20-41\n"
            "Total cholesterol   5.8   mmol/L   Ref: <5.0\n"
            "eGFR   78   mL/min   Ref: >60")
    r = {x["test_name"]: x for x in parse_lab_report(text)}
    assert (r["HbA1c"]["ref_low"], r["HbA1c"]["ref_high"]) == (20, 41)
    assert (r["Total cholesterol"]["ref_low"], r["Total cholesterol"]["ref_high"]) == (None, 5.0)
    assert (r["eGFR"]["ref_low"], r["eGFR"]["ref_high"]) == (60, None)


def test_note_medication_mcg_becomes_microgram():
    meds = parse_note_medications("Seen for wheeze.\nRx: Salbutamol inhaler 200 mcg PRN\nReview in 2 weeks.")
    assert meds == [{"drug_name": "Salbutamol inhaler", "dose_value": 200.0, "dose_unit": "microgram",
                     "frequency": "prn", "duration_days": None, "quantity": None,
                     "source_quote": "Rx: Salbutamol inhaler 200 mcg PRN"}]


def test_handwritten_note_always_flagged_as_handwriting():
    doc = structure("Clinical note\nPatient: X\nSeen today.", "handwritten_note")
    assert doc["has_handwriting"] is True
    assert "Seen today." in doc["summary"]


def test_text_with_nothing_recognisable_returns_empty_lists_not_errors():
    doc = structure("completely unrelated text", "prescription")
    assert doc["medications"] == [] and doc["patient"]["nhs_number"] is None
