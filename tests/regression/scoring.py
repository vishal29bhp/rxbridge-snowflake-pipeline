"""Field-level accuracy of one extraction against the golden (true) values."""

from __future__ import annotations

MED_FIELDS = ("drug_name", "dose_value", "dose_unit", "frequency", "duration_days", "quantity")
LAB_FIELDS = ("test_name", "result_value", "unit", "ref_low", "ref_high")


def _same(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return (str(a).strip().lower() if a is not None else None) == (str(b).strip().lower() if b is not None else None)


def score(doc: dict, gold: dict) -> tuple[float, list[str]]:
    """Returns (share of golden fields read correctly, list of mismatches)."""
    checks, misses = [], []

    def check(name, got, want):
        ok = _same(got, want)
        checks.append(ok)
        if not ok:
            misses.append(f"{name}: got {got!r}, want {want!r}")

    check("nhs_number", doc["patient"]["nhs_number"], gold["nhs_number"])
    check("document_date", doc["document_date"], gold["document_date"])
    for kind, fields in (("medications", MED_FIELDS), ("lab_results", LAB_FIELDS)):
        want, got = gold.get(kind, []), doc.get(kind, [])
        for i, w in enumerate(want):
            g = got[i] if i < len(got) else {}
            for f in fields:
                check(f"{kind}[{i}].{f}", g.get(f), w.get(f))
        if len(got) > len(want):
            checks.append(False)
            misses.append(f"{kind}: {len(got) - len(want)} extra line(s) read")
    return sum(checks) / len(checks), misses
