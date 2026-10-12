"""Settings come from environment variables (or a local .env file). No secrets in code.

Copy .env.example to .env and fill it in. .env is git-ignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ('"', "'"):
            value = value[1:].split(value[0], 1)[0]   # quoted: keep everything inside the quotes
        else:
            value = value.split(" #", 1)[0].strip()   # unquoted: drop an inline "# comment"
        os.environ.setdefault(key.strip(), value)


_load_dotenv()
os.environ.setdefault("AZURE_CONTAINER", "rx-archive")


def _env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


@dataclass
class Settings:
    # --- Azure Blob Storage: where the original files, metadata and AI results live ---
    azure_storage_conn: str | None = field(default_factory=lambda: _env("AZURE_STORAGE_CONNECTION_STRING"))
    azure_container: str = field(default_factory=lambda: _env("AZURE_CONTAINER", "rx-archive"))

    # --- Azure AI Document Intelligence: who reads the documents ---
    # RX_READER=azure (default) or offline (Tesseract on your laptop; free, for practice and tests)
    reader: str = field(default_factory=lambda: _env("RX_READER", "azure"))
    azure_di_endpoint: str | None = field(default_factory=lambda: _env("AZURE_DI_ENDPOINT"))
    azure_di_key: str | None = field(default_factory=lambda: _env("AZURE_DI_KEY"))
    extract_model: str = field(default_factory=lambda: _env("RX_EXTRACT_MODEL", "prebuilt-read"))
    verify_model: str = field(default_factory=lambda: _env("RX_VERIFY_MODEL", "prebuilt-layout"))

    # --- Snowflake ---
    sf_account: str | None = field(default_factory=lambda: _env("SNOWFLAKE_ACCOUNT"))
    sf_user: str | None = field(default_factory=lambda: _env("SNOWFLAKE_USER"))
    sf_password: str | None = field(default_factory=lambda: _env("SNOWFLAKE_PASSWORD"))
    sf_private_key_path: str | None = field(default_factory=lambda: _env("SNOWFLAKE_PRIVATE_KEY_PATH"))
    sf_role: str = field(default_factory=lambda: _env("SNOWFLAKE_ROLE", "RX_ENGINEER"))
    sf_warehouse: str = field(default_factory=lambda: _env("SNOWFLAKE_WAREHOUSE", "RX_LOAD_WH"))
    sf_database: str = field(default_factory=lambda: _env("SNOWFLAKE_DATABASE", "RX_DB"))

    # --- Batch rules (passed to the RAW.BUILD_BATCH procedure) ---
    batch_size: int = field(default_factory=lambda: int(_env("RX_BATCH_SIZE", "5000")))
    page_budget: int = field(default_factory=lambda: int(_env("RX_PAGE_BUDGET", "15000")))
    min_ready: int = field(default_factory=lambda: int(_env("RX_MIN_READY", "1")))  # production: 5000
    max_wait_hours: int = field(default_factory=lambda: int(_env("RX_MAX_WAIT_HOURS", "6")))
    max_active_batches: int = field(default_factory=lambda: int(_env("RX_MAX_ACTIVE_BATCHES", "4")))
    max_attempts: int = field(default_factory=lambda: int(_env("RX_MAX_ATTEMPTS", "2")))

    sample_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "samples")


def get_settings() -> Settings:
    return Settings()
