"""Snowflake connection plus a helper to run the numbered SQL scripts in snowflake/.

Authentication: key pair (SNOWFLAKE_PRIVATE_KEY_PATH) is preferred; password works for a trial.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Sequence

from .config import PROJECT_ROOT, Settings

SQL_DIR = PROJECT_ROOT / "snowflake"
PLACEHOLDER = re.compile(r"<<([A-Z_]+)>>")


def render_sql(name: str) -> str:
    """Fill <<AZURE_STORAGE_ACCOUNT>>-style placeholders from the environment (.env)."""
    text = (SQL_DIR / name).read_text()
    missing = sorted({m for m in PLACEHOLDER.findall(text) if not os.getenv(m)})
    if missing:
        raise SystemExit(f"{name} needs these values in .env: {', '.join(missing)}")
    return PLACEHOLDER.sub(lambda m: os.environ[m.group(1)], text)


class Snowflake:
    def __init__(self, settings: Settings):
        import snowflake.connector

        if not (settings.sf_account and settings.sf_user):
            raise SystemExit("Set SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER in .env")
        kwargs: dict[str, Any] = dict(
            account=settings.sf_account,
            user=settings.sf_user,
            role=settings.sf_role,
            warehouse=settings.sf_warehouse,
            database=settings.sf_database,
            schema="RAW",
            session_parameters={"QUERY_TAG": "rxpipe"},
        )
        if settings.sf_private_key_path:
            kwargs["private_key_file"] = settings.sf_private_key_path
        elif settings.sf_password:
            kwargs["password"] = settings.sf_password
        else:
            raise SystemExit("Set SNOWFLAKE_PRIVATE_KEY_PATH or SNOWFLAKE_PASSWORD in .env")
        self.conn = snowflake.connector.connect(**kwargs)

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict]:
        cur = self.conn.cursor()
        cur.execute(sql, params)
        cols = [d[0].lower() for d in cur.description or []]
        return [dict(zip(cols, row)) for row in cur.fetchall()] if cols else []

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self.conn.cursor().execute(sql, params)

    def run_script(self, name: str, variables: dict[str, Any] | None = None) -> list[list[dict]]:
        """Run snowflake/<name>. `variables` become session variables ($name) used inside the script."""
        for key, value in (variables or {}).items():
            self.execute(f"SET {key} = %s", [value])
        sql = render_sql(name)
        results = []
        for cur in self.conn.execute_string(sql, remove_comments=True):
            cols = [d[0].lower() for d in cur.description or []]
            results.append([dict(zip(cols, r)) for r in cur.fetchall()] if cols else [])
        return results

    def close(self) -> None:
        self.conn.close()
