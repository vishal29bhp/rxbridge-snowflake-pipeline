"""STAGE 5 - EXTRACT one batch: Snowflake queue -> Document Intelligence -> JSONL in Blob.

Python does not write to Snowflake tables here. It writes one results file per batch to
results/<batch_id>/results.jsonl, and Snowflake loads it with COPY INTO (stage 6).
That keeps the AI output as an immutable file (replayable, auditable), and COPY's
load history means the same results file is never loaded twice.

Each line of the JSONL is one of:
  {"step": "extract", ...}   the main reading
  {"step": "verify",  ...}   the independent second reading
  {"step": "error",   ...}   the file could not be read (Snowflake retries, then quarantines)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .ocr import UnreadableDocument


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def result_lines(report: dict, data: bytes, reader) -> list[dict]:
    """Read one report twice. Pure function: no I/O, so it is unit-tested with a fake reader."""
    base = {"report_id": report["report_id"], "batch_id": report["batch_id"], "extractor": reader.name}
    try:
        if report.get("_download_error"):
            raise UnreadableDocument(f"download failed: {report['_download_error']}")
        if not data:
            raise UnreadableDocument("empty file (0 bytes)")
        lines = []
        for step in ("extract", "verify"):
            r = reader.read(data, report["mime_type"], report["doc_type"], step)
            lines.append({**base, "step": step, "model": r.model, "read_method": r.method,
                          "raw_text": r.raw_text, "doc": r.doc, "error": None, "read_at": _now()})
        return lines
    except Exception as exc:  # any failure becomes an 'error' line; Snowflake decides retry vs quarantine
        return [{**base, "step": "error", "model": None, "read_method": None, "raw_text": None,
                 "doc": None, "error": f"{type(exc).__name__}: {exc}"[:500], "read_at": _now()}]


def queued_reports(sf, batch_id: str | None = None) -> list[dict]:
    sql = """
        SELECT report_id, batch_id, relative_path, mime_type, doc_type
        FROM raw.file_registry
        WHERE status = 'QUEUED' {filter}
        ORDER BY batch_id, report_id
    """
    if batch_id:
        return sf.query(sql.format(filter="AND batch_id = %s"), [batch_id])
    return sf.query(sql.format(filter=""))


def run_extract(sf, blob, reader, batch_id: str | None = None) -> dict:
    """Process every QUEUED report (optionally one batch) and write one JSONL file per batch."""
    by_batch: dict[str, list[dict]] = {}
    for rep in queued_reports(sf, batch_id):
        try:
            data = blob.download("inbox/" + rep["relative_path"])
        except Exception as exc:
            data, rep = b"", {**rep, "_download_error": str(exc)}
        by_batch.setdefault(rep["batch_id"], []).extend(result_lines(rep, data, reader))

    summary = {}
    for bid, lines in by_batch.items():
        # Unique file name per run: a retried batch never overwrites an earlier results file.
        name = f"results/{bid}/results_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.jsonl"
        blob.upload_bytes("\n".join(json.dumps(x, default=str) for x in lines).encode(), name)
        summary[bid] = {
            "file": name,
            "ok": sum(1 for x in lines if x["step"] == "extract"),
            "errors": sum(1 for x in lines if x["step"] == "error"),
        }
    return summary
