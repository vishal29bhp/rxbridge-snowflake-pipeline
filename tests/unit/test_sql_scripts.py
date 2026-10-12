"""The Snowflake scripts: placeholders are all documented, and every script splits into statements."""

import re
from pathlib import Path

import pytest
from snowflake.connector.util_text import split_statements

from rxpipe.snowflake_client import PLACEHOLDER, SQL_DIR, render_sql

SCRIPTS = sorted(p.name for p in SQL_DIR.glob("*.sql"))
ENV_EXAMPLE = (SQL_DIR.parent / ".env.example").read_text()


@pytest.mark.parametrize("name", SCRIPTS)
def test_every_placeholder_is_in_env_example(name):
    for key in set(PLACEHOLDER.findall((SQL_DIR / name).read_text())):
        assert re.search(rf"^{key}=", ENV_EXAMPLE, re.M), f"{key} used in {name} but missing from .env.example"


def test_render_fails_clearly_when_a_value_is_missing(monkeypatch):
    monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
    with pytest.raises(SystemExit, match="AZURE_TENANT_ID"):
        render_sql("00_admin_setup.sql")


def test_render_fills_values(monkeypatch):
    for k, v in {"AZURE_TENANT_ID": "t-1", "AZURE_STORAGE_ACCOUNT": "acct", "AZURE_CONTAINER": "rx-archive",
                 "SNOWFLAKE_USER": "VISHAL"}.items():
        monkeypatch.setenv(k, v)
    sql = render_sql("00_admin_setup.sql")
    assert "<<" not in sql and "azure://acct.blob.core.windows.net/rx-archive/" in sql


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_split_into_statements(name):
    """The connector splits scripts on ';' - procedure/UDF bodies in $$...$$ must stay whole."""
    text = (SQL_DIR / name).read_text()
    statements = [s for s, _ in split_statements(__import__("io").StringIO(text), remove_comments=True) if s.strip()]
    assert statements, name
    for s in statements:
        if "$$" in s:
            assert s.count("$$") == 2, f"a $$ block was split in {name}"


def test_build_batch_procedure_is_one_statement():
    text = (SQL_DIR / "01_objects.sql").read_text()
    stmts = [s for s, _ in split_statements(__import__("io").StringIO(text), remove_comments=True)]
    proc = [s for s in stmts if "PROCEDURE RAW.BUILD_BATCH" in s]
    assert len(proc) == 1 and "RETURN new_batch" in proc[0]
