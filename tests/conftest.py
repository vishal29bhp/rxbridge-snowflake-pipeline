import shutil
from pathlib import Path

import pytest

from rxpipe.samples import generate

HAS_TESSERACT = shutil.which("tesseract") is not None


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory) -> Path:
    """The 11 synthetic documents, generated once per test session."""
    out = tmp_path_factory.mktemp("samples")
    generate(out)
    return out


@pytest.fixture(scope="session")
def truth(sample_dir) -> dict:
    import json

    return json.loads((sample_dir / "_meta" / "ground_truth.json").read_text())
