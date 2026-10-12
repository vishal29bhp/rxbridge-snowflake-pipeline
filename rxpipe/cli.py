"""Command line for the whole pipeline. Each command is ONE stage, so you can walk through
the flow by hand and look at Snowflake between steps (see README "Walkthrough").

  python -m rxpipe <command> --help
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from .config import PROJECT_ROOT, get_settings

DBT_DIR = PROJECT_ROOT / "dbt"


# ---------------------------------------------------------------- helpers
def _print_rows(rows: list[dict], title: str | None = None) -> None:
    if title:
        print(f"\n{title}")
    if not rows:
        print("  (no rows)")
        return
    cols = list(rows[0].keys())
    widths = {c: min(60, max(len(c), *(len(str(r[c])) for r in rows))) for c in cols}
    print("  " + "  ".join(c.ljust(widths[c]) for c in cols))
    print("  " + "  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  " + "  ".join(str(r[c])[: widths[c]].ljust(widths[c]) for c in cols))


def _sf():
    from .snowflake_client import Snowflake

    return Snowflake(get_settings())


def _run_script(name: str, variables: dict | None = None) -> None:
    sf = _sf()
    try:
        results = sf.run_script(name, variables)
        _print_rows(results[-1] if results else [], f"{name}: result")
    finally:
        sf.close()


# ---------------------------------------------------------------- commands
def cmd_render_sql(a):
    from .snowflake_client import render_sql

    print(render_sql(a.file))


def cmd_setup(a):
    _run_script("01_objects.sql")


def cmd_samples(a):
    from .samples import generate, write_patients

    s = get_settings()
    if a.move_patient:
        key, clinic, since = a.move_patient
        write_patients(s.sample_dir, {key: (clinic, since)})
        print(f"patients.csv rewritten: patient {key} -> {clinic} since {since}. Now run: upload, load-meta, transform")
        return
    truth = generate(s.sample_dir)
    print(f"Wrote {len(truth)} documents to {s.sample_dir}")
    for f, t in truth.items():
        print(f"  {f:42s} expect {t['expect_status']:17s} {t.get('expect_route') or ''}")


def cmd_upload(a):
    from .blob import get_blob_store

    s = get_settings()
    blob = get_blob_store(s)
    root = s.sample_dir if not a.path else a.path
    from pathlib import Path

    root = Path(root)
    new = skipped = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith("_meta/"):
            if rel.endswith(".csv"):            # metadata lists are replaced every time
                blob.upload_file(p, rel, overwrite=True)
                print(f"  meta  {rel}")
            continue
        if blob.upload_file(p, "inbox/" + rel):  # originals are never overwritten
            new += 1
            print(f"  new   inbox/{rel}")
        else:
            skipped += 1
    print(f"Uploaded {new} new documents ({skipped} already there) to container '{s.azure_container}'")


def cmd_load_meta(a):
    _run_script("10_load_meta.sql")


def cmd_register(a):
    _run_script("20_register.sql")


def cmd_batch(a):
    s = get_settings()
    sf = _sf()
    try:
        made = []
        while True:
            msg = sf.query(
                "CALL raw.build_batch(%s, %s, %s, %s, %s)",
                [s.batch_size, s.page_budget, s.min_ready, s.max_wait_hours, s.max_active_batches],
            )[0]
            msg = list(msg.values())[0]
            print(" ", msg)
            if msg.startswith("NONE") or not a.all:
                break
            made.append(msg)
    finally:
        sf.close()


def cmd_extract(a):
    from .blob import get_blob_store
    from .extract import run_extract
    from .extractors import get_reader

    s = get_settings()
    sf = _sf()
    try:
        summary = run_extract(sf, get_blob_store(s), get_reader(s), a.batch)
    finally:
        sf.close()
    if not summary:
        print("Nothing QUEUED. Run `python -m rxpipe batch` first.")
    for bid, info in summary.items():
        print(f"  {bid}: {info['ok']} read, {info['errors']} failed -> {info['file']}")


def cmd_load_results(a):
    _run_script("40_load_results.sql", {"max_attempts": get_settings().max_attempts})


def cmd_transform(a):
    cmd = ["dbt", a.dbt_command, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    if a.select:
        cmd += ["--select", a.select]
    if a.regression:
        cmd += ["--vars", "{run_regression: true}"]
    print("$", " ".join(cmd))
    sys.exit(subprocess.call(cmd, env=os.environ.copy()))


def cmd_status(a):
    sf = _sf()
    try:
        _print_rows(sf.query(
            "SELECT status, COUNT(*) AS files FROM raw.file_registry GROUP BY 1 ORDER BY 1"), "File registry")
        _print_rows(sf.query(
            "SELECT relative_path, status, batch_id, attempts, LEFT(last_error, 50) AS last_error "
            "FROM raw.file_registry ORDER BY relative_path"), "Every file")
        try:
            _print_rows(sf.query(
                "SELECT route, review_status, COUNT(*) AS documents FROM gold.fct_review_queue "
                "GROUP BY 1, 2 ORDER BY 1, 2"), "Review queue (after transform)")
        except Exception:
            print("\nReview queue: not built yet (run `python -m rxpipe transform`).")
    finally:
        sf.close()


def cmd_sql(a):
    sf = _sf()
    try:
        _print_rows(sf.query(a.query))
    finally:
        sf.close()


def cmd_review(a):
    from . import review

    sf = _sf()
    try:
        if a.action == "list":
            _print_rows(review.pending(sf), "Waiting for review")
        elif a.action == "show":
            print(json.dumps(review.show(sf, a.target), indent=2, default=str))
        elif a.action in ("approve", "reject"):
            review.decide(sf, a.target, "approved" if a.action == "approve" else "rejected", a.note)
            print(f"{a.action}d {a.target}. Run `python -m rxpipe transform` to rebuild GOLD.")
        elif a.action == "correct":
            review.correct_line(sf, a.target, dose_value=a.dose, dose_unit=a.unit,
                                drug_name=a.drug, frequency=a.frequency)
            print(f"Corrected {a.target}. Approve the document next, then transform.")
        elif a.action == "reject-line":
            review.reject_line(sf, a.target)
            print(f"Rejected line {a.target}.")
    finally:
        sf.close()


def cmd_deploy_app(a):
    sf = _sf()
    try:
        app = PROJECT_ROOT / "snowflake" / "streamlit" / "review_app.py"
        sf.execute(f"PUT 'file://{app.as_posix()}' @raw.app_stage/review AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        sf.run_script("95_review_app.sql")
        print("Deployed. Snowsight > Projects > Streamlit > RX_REVIEW")
    finally:
        sf.close()


def cmd_run(a):
    """Stages 2-7 in one go, for when you've understood them one by one."""
    for step in (cmd_load_meta, cmd_register):
        step(a)
    a.all = True
    cmd_batch(a)
    a.batch = None
    cmd_extract(a)
    cmd_load_results(a)
    print("\nNext: python -m rxpipe transform")


# ---------------------------------------------------------------- argument parsing
def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m rxpipe", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    sp = add("render-sql", cmd_render_sql, "print a snowflake/*.sql file with your .env values filled in")
    sp.add_argument("file")
    add("setup", cmd_setup, "create stages, RAW tables, UDF and procedure (01_objects.sql)")
    sp = add("samples", cmd_samples, "STAGE 1: generate the 11 synthetic test documents")
    sp.add_argument("--move-patient", nargs=3, metavar=("KEY", "CLINIC", "SINCE"),
                    help='simulate a clinic change, e.g. A "Northgate Surgery" 01/07/2021')
    sp = add("upload", cmd_upload, "STAGE 1: upload documents + metadata to Azure Blob")
    sp.add_argument("--path", help="folder to upload (default data/samples)")
    add("load-meta", cmd_load_meta, "STAGE 2: COPY manifest + patient list into Snowflake")
    add("register", cmd_register, "STAGE 3: register new files, fingerprint, dedupe")
    sp = add("batch", cmd_batch, "STAGE 4: build the next batch (RAW.BUILD_BATCH)")
    sp.add_argument("--all", action="store_true", help="keep building batches until none can be made")
    sp = add("extract", cmd_extract, "STAGE 5: read QUEUED documents with Document Intelligence")
    sp.add_argument("--batch", help="only this batch id")
    add("load-results", cmd_load_results, "STAGE 6: COPY the AI results into Snowflake, update statuses")
    sp = add("transform", cmd_transform, "STAGE 7: dbt build (seeds, snapshot, models, tests)")
    sp.add_argument("--select", help="dbt selector, e.g. +fct_medication")
    sp.add_argument("--regression", action="store_true", help="also run the sample-set regression test")
    sp.add_argument("--dbt-command", default="build", choices=["build", "run", "test", "seed", "snapshot", "compile"])
    sp = add("review", cmd_review, "STAGE 8: human review from the command line")
    sp.add_argument("action", choices=["list", "show", "approve", "reject", "correct", "reject-line"])
    sp.add_argument("target", nargs="?", help="report_id, or medication_line_id for correct/reject-line")
    sp.add_argument("--note")
    sp.add_argument("--dose", type=float)
    sp.add_argument("--unit")
    sp.add_argument("--drug")
    sp.add_argument("--frequency")
    add("status", cmd_status, "show where every file is")
    sp = add("sql", cmd_sql, "run one SQL query and print the result")
    sp.add_argument("query")
    add("deploy-app", cmd_deploy_app, "deploy the Streamlit review app to Snowflake")
    add("run", cmd_run, "stages 2-6 in one go")

    a = p.parse_args(argv)
    if a.command == "review" and a.action != "list" and not a.target:
        p.error(f"review {a.action} needs a report_id or medication_line_id")
    a.fn(a)


if __name__ == "__main__":
    main()
