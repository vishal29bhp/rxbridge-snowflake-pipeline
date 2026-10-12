"""Re-record baseline_scores.json after an intentional improvement. Review the diff before committing."""

import json
from pathlib import Path

from rxpipe.extractors import OfflineReader
from rxpipe.samples import generate
from tests.regression.scoring import score
from tests.regression.test_extraction_golden import BASELINE, GOLDEN, GOLDEN_DIR, MIME

if __name__ == "__main__":
    import tempfile

    out = Path(tempfile.mkdtemp())
    generate(out)
    new = {}
    for f, gold in GOLDEN.items():
        for step in ("extract", "verify"):
            res = OfflineReader().read((out / f).read_bytes(), MIME[Path(f).suffix], gold["doc_type"], step)
            new[f"{f}::{step}"] = round(score(res.doc, gold)[0], 4)
            if new[f"{f}::{step}"] != BASELINE.get(f"{f}::{step}"):
                print(f"{f}::{step}: {BASELINE.get(f'{f}::{step}')} -> {new[f'{f}::{step}']}")
    (GOLDEN_DIR / "baseline_scores.json").write_text(json.dumps(new, indent=2))
    print("baseline_scores.json updated")
