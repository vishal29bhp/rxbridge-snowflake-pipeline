"""Synthetic test documents. Every name, NHS number and clinic here is invented.

Run:  python -m rxpipe samples

Creates data/inbox/ with eleven files that exercise every path through the pipeline,
plus _meta/manifest.csv (the scanning vendor's list), _meta/patients.csv (the clinic's
patient list) and _meta/ground_truth.json (what each document really says).

  file                                   what it tests                         expected route
  prescriptions/rx_typed_001.pdf         clean typed prescription              auto_approve
  prescriptions/rx_typed_001_rescan.pdf  identical rescan                      DUPLICATE (never extracted)
  lab/lab_typed_002.pdf                  typed lab report                      auto_approve
  photos/rx_photo_003.jpg                phone photo, dose printed as 5000 mg  review_full (dose out of range)
  notes/note_hand_004.png                handwritten-style clinical note       review_full (handwriting)
  prescriptions/rx_typed_005.pdf         NHS number mistyped on the paper      review_full (patient check)
  prescriptions/rx_typed_006.pdf         drug not in dm+d                      review_full (unmatched drug)
  prescriptions/rx_corrupt_007.pdf       corrupt file                          QUARANTINED after 2 tries
  scans/rx_scanned_008.pdf               scanned PDF, no text layer -> OCR     review_fast
  prescriptions/rx_orphan_009.pdf        file with no manifest row             PENDING_MANIFEST
  scans/lab_scan_010.tif                 TIFF scan of a lab report -> OCR      review_fast
"""

from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .normalise import make_nhs_number

PATIENTS = {
    "A": {"name": "Asha Patel", "nhs": make_nhs_number("943476591"), "dob": "12/05/1968",
          "clinic": "Riverside Clinic", "since": "10/02/2015", "phone": "07700 900101"},
    "B": {"name": "Rahul Verma", "nhs": make_nhs_number("485777345"), "dob": "03/11/1975",
          "clinic": "Northgate Surgery", "since": "01/09/2018", "phone": "07700 900102"},
    "C": {"name": "Meera Iyer", "nhs": make_nhs_number("401023213"), "dob": "21/07/1959",
          "clinic": "Riverside Clinic", "since": "15/01/2020", "phone": "07700 900103"},
    "D": {"name": "Sanjay Rao", "nhs": make_nhs_number("450557710"), "dob": "30/01/1982",
          "clinic": "Northgate Surgery", "since": "05/05/2019", "phone": "07700 900104"},
}


def _fmt_nhs(n: str) -> str:
    return f"{n[:3]} {n[3:6]} {n[6:]}"


def _mistype(n: str) -> str:
    """Swap digits 8 and 9, the classic transcription error. The check digit then fails."""
    swapped = n[:7] + n[8] + n[7] + n[9:]
    assert swapped != n, "pick an NHS number whose 8th and 9th digits differ"
    return swapped


def _rx(drug, dose, unit, freq, days, qty):
    return {"drug_name": drug, "dose_value": dose, "dose_unit": unit, "frequency": freq,
            "duration_days": days, "quantity": qty}


def _lab(test, value, unit, low, high, ref_text):
    return {"test_name": test, "result_value": value, "unit": unit, "ref_low": low, "ref_high": high,
            "_ref_text": ref_text}


# ---- what each document says (also the regression "golden set") ----------------------
DOCS = [
    dict(file="prescriptions/rx_typed_001.pdf", kind="typed_pdf", doc_type="prescription", patient="A",
         date="03/04/2019", prescriber="Dr A Mehta", clinic="Riverside Clinic",
         meds=[_rx("Amoxicillin 500mg capsules", 500, "mg", "tds", 7, 21),
               _rx("Paracetamol 500mg tablets", 1000, "mg", "qds prn", 5, 32)],
         expect_status="RETURNED", expect_route="auto_approve"),
    dict(file="lab/lab_typed_002.pdf", kind="typed_pdf", doc_type="lab_report", patient="B",
         date="15/01/2024", prescriber="Dr S Khan", clinic="Northgate Surgery",
         labs=[_lab("HbA1c", 52, "mmol/mol", 20, 41, "20-41"),
               _lab("Total cholesterol", 5.8, "mmol/L", None, 5.0, "<5.0"),
               _lab("eGFR", 78, "mL/min", 60, None, ">60")],
         expect_status="RETURNED", expect_route="auto_approve"),
    dict(file="photos/rx_photo_003.jpg", kind="photo", doc_type="prescription", patient="A",
         date="15/08/2022", prescriber="Dr S Khan", clinic="Northgate Surgery",
         meds=[_rx("Metformin 500mg tablets", 5000, "mg", "bd", 28, 56),   # printed wrongly: 5000
               _rx("Atorvastatin 20mg tablets", 20, "mg", "on", 28, 28)],
         expect_status="RETURNED", expect_route="review_full"),
    dict(file="notes/note_hand_004.png", kind="handwritten", doc_type="handwritten_note", patient="B",
         date="22/01/2024", prescriber="Dr S Khan", clinic="Northgate Surgery",
         note=["Seen for wheeze, worse at night.", "Chest clear on examination.",
               "Rx: Salbutamol inhaler 200 mcg PRN", "Review in 2 weeks."],
         meds=[_rx("Salbutamol inhaler", 200, "microgram", "prn", None, None)],
         expect_status="RETURNED", expect_route="review_full"),
    dict(file="prescriptions/rx_typed_005.pdf", kind="typed_pdf", doc_type="prescription", patient="D",
         date="12/09/2023", prescriber="Dr S Khan", clinic="Northgate Surgery", mistype_nhs=True,
         meds=[_rx("Amoxicillin 500mg capsules", 500, "mg", "tds", 5, 15)],
         expect_status="RETURNED", expect_route="review_full"),
    dict(file="prescriptions/rx_typed_006.pdf", kind="typed_pdf", doc_type="prescription", patient="C",
         date="10/03/2023", prescriber="Dr A Mehta", clinic="Riverside Clinic",
         meds=[_rx("Zyntrax 10mg tablets", 10, "mg", "od", 30, 30)],
         expect_status="RETURNED", expect_route="review_full"),
    dict(file="prescriptions/rx_corrupt_007.pdf", kind="corrupt", doc_type="prescription", patient="C",
         expect_status="QUARANTINED", expect_route=None),
    dict(file="scans/rx_scanned_008.pdf", kind="scanned_pdf", doc_type="prescription", patient="C",
         date="05/06/2024", prescriber="Dr A Mehta", clinic="Riverside Clinic",
         meds=[_rx("Atorvastatin 20mg tablets", 20, "mg", "on", 28, 28),
               _rx("Metformin 500mg tablets", 500, "mg", "bd", 28, 56)],
         expect_status="RETURNED", expect_route="review_fast"),
    dict(file="prescriptions/rx_orphan_009.pdf", kind="typed_pdf", doc_type="prescription", patient="C",
         date="01/02/2024", prescriber="Dr A Mehta", clinic="Riverside Clinic", in_manifest=False,
         meds=[_rx("Paracetamol 500mg tablets", 1000, "mg", "qds prn", 3, 24)],
         expect_status="PENDING_MANIFEST", expect_route=None),
    dict(file="scans/lab_scan_010.tif", kind="tiff", doc_type="lab_report", patient="C",
         date="05/06/2024", prescriber="Dr A Mehta", clinic="Riverside Clinic",
         labs=[_lab("HbA1c", 48, "mmol/mol", 20, 41, "20-41"),
               _lab("eGFR", 85, "mL/min", 60, None, ">60")],
         expect_status="RETURNED", expect_route="review_fast"),
]
DUPLICATE = {"file": "prescriptions/rx_typed_001_rescan.pdf", "copy_of": "prescriptions/rx_typed_001.pdf",
             "patient": "A", "doc_type": "prescription", "expect_status": "DUPLICATE"}


def document_lines(d: dict) -> list[str]:
    """The text printed on the page. Same lines for PDF, photo, scan and TIFF."""
    p = PATIENTS[d["patient"]]
    nhs = _mistype(p["nhs"]) if d.get("mistype_nhs") else p["nhs"]
    title = {"prescription": "PRESCRIPTION", "lab_report": "LABORATORY REPORT",
             "handwritten_note": "Clinical note"}[d["doc_type"]]
    lines = [d["clinic"].upper(), title, "",
             f"Patient: {p['name']}", f"NHS No: {_fmt_nhs(nhs)}", f"Date: {d['date']}",
             f"Prescriber: {d['prescriber']}", f"Clinic: {d['clinic']}", ""]
    for i, m in enumerate(d.get("meds", []) if d["doc_type"] == "prescription" else [], 1):
        dose = int(m["dose_value"]) if float(m["dose_value"]).is_integer() else m["dose_value"]
        lines.append(f"{i}. {m['drug_name']}   Dose: {dose} {m['dose_unit']}   Freq: {m['frequency'].upper()}"
                     f"   Days: {m['duration_days']}   Qty: {m['quantity']}")
    for r in d.get("labs", []):
        lines.append(f"{r['test_name']}   {r['result_value']}   {r['unit']}   Ref: {r['_ref_text']}")
    lines.extend(d.get("note", []))
    return lines


def _font(size: int, italic: bool = False):
    candidates = (
        ["/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
         "C:/Windows/Fonts/segoepr.ttf", "/Library/Fonts/Bradley Hand Bold.ttf"]
        if italic else
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial.ttf"]
    )
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default(size=size)


def _typed_pdf(path: Path, lines: list[str]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)  # invariant: identical bytes every run
    y = 800
    for i, ln in enumerate(lines):
        c.setFont("Helvetica-Bold" if i < 2 else "Helvetica", 14 if i < 2 else 10)
        c.drawString(50, y, ln)
        y -= 22 if i < 2 else 18
    c.save()


def _page_image(lines: list[str], handwritten: bool = False) -> Image.Image:
    rnd = random.Random(42)
    img = Image.new("L", (1700, 2200), 255)
    draw = ImageDraw.Draw(img)
    y = 120
    for i, ln in enumerate(lines):
        if handwritten:
            draw.line([(80, y + 52), (1620, y + 52)], fill=200, width=2)  # ruled paper
            x = 110
            for word in ln.split(" "):  # wobble each word so it looks hand-placed
                f = _font(44 + rnd.randint(-3, 3), italic=True)
                draw.text((x, y + rnd.randint(-4, 4)), word, font=f, fill=rnd.randint(20, 60))
                x += int(draw.textlength(word + " ", font=f)) + rnd.randint(0, 6)
            y += 78
        else:
            f = _font(40 if i < 2 else 30)
            draw.text((100, y), ln, font=f, fill=0)
            y += 62 if i < 2 else 50
    return img


def _photo(img: Image.Image) -> Image.Image:
    """Make a clean page look like a phone photo: slight tilt, blur, grain, grey edges."""
    rnd = random.Random(7)
    img = img.rotate(1.2, expand=True, fillcolor=190).filter(ImageFilter.GaussianBlur(0.8))
    noise = Image.effect_noise(img.size, 18)
    return Image.blend(img, noise, 0.08).point(lambda p: max(0, p - rnd.randint(0, 3)))


def _image_pdf(path: Path, img: Image.Image) -> None:
    img.convert("RGB").save(path, "PDF", resolution=200)  # image only: no text layer


def generate(out_dir: Path) -> dict:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "_meta").mkdir(parents=True)
    truth = {}
    for d in DOCS:
        path = out_dir / d["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        if d["kind"] == "corrupt":
            path.write_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj << /Type /Catal")  # truncated
        else:
            lines = document_lines(d)
            if d["kind"] == "typed_pdf":
                _typed_pdf(path, lines)
            elif d["kind"] == "photo":
                _photo(_page_image(lines)).convert("RGB").save(path, "JPEG", quality=72)
            elif d["kind"] == "handwritten":
                _page_image(lines, handwritten=True).save(path, "PNG")
            elif d["kind"] == "scanned_pdf":
                _image_pdf(path, _photo(_page_image(lines)))
            elif d["kind"] == "tiff":
                _page_image(lines).save(path, "TIFF", compression="tiff_lzw")
        p = PATIENTS[d["patient"]]
        truth[d["file"]] = {
            "doc_type": d["doc_type"],
            "nhs_number": _mistype(p["nhs"]) if d.get("mistype_nhs") else p["nhs"],
            "document_date": None if "date" not in d else
            "-".join(reversed(d["date"].split("/"))),
            "medications": d.get("meds", []),
            "lab_results": [{k: v for k, v in r.items() if not k.startswith("_")} for r in d.get("labs", [])],
            "expect_status": d["expect_status"],
            "expect_route": d["expect_route"],
        }

    dup = out_dir / DUPLICATE["file"]
    shutil.copyfile(out_dir / DUPLICATE["copy_of"], dup)
    truth[DUPLICATE["file"]] = {"doc_type": "prescription", "expect_status": "DUPLICATE", "expect_route": None}

    with open(out_dir / "_meta" / "manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file_name", "nhs_number", "doc_type", "clinic", "scan_date", "priority"])
        for d in DOCS + [DUPLICATE]:
            if d.get("in_manifest", True):
                p = PATIENTS[d["patient"]]
                w.writerow([d["file"], p["nhs"], d["doc_type"], p["clinic"], "28/09/2026",
                            1 if d["doc_type"] == "lab_report" else 0])
    write_patients(out_dir)
    (out_dir / "_meta" / "ground_truth.json").write_text(json.dumps(truth, indent=2))
    return truth


def write_patients(out_dir: Path, moves: dict | None = None) -> None:
    """moves = {"A": ("Northgate Surgery", "01/07/2021")} simulates a patient changing clinic."""
    with open(out_dir / "_meta" / "patients.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nhs_number", "patient_name", "date_of_birth", "registered_clinic", "clinic_since", "phone"])
        for key, p in PATIENTS.items():
            clinic, since = (moves or {}).get(key, (p["clinic"], p["since"]))
            w.writerow([p["nhs"], p["name"], p["dob"], clinic, since, p["phone"]])
