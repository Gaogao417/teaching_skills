#!/usr/bin/env python3
"""Batch DOCX step-1 extraction for all pending question-bank papers.

Combines scan + prepare + extract into one idempotent driver:

  1. scan_pending_ingestions.py  -> pending papers (status != COMPLETE)
  2. prepare_source_archives.py  -> copy each collection .doc/.docx into
     documents/初三/<规范名>/source.doc(.docx)  (idempotent EXISTS skip)
  3. extract_docx_source.py      -> per-paper word/ (media + pages + yaml)

Each paper has its own archive dir, so soffice profiles never collide
across papers and the extraction runs safely in parallel.

Skipped on purpose:
  - papers whose word/ is already complete (word-source.yaml + non-empty
    pages/): re-running would be a no-op and extract refuses overwrite.
  - papers with no DOC/DOCX source (e.g. image-only / PDF scans): these
    belong to math-pdf-question-bank-ingestion, reported as NODOC.

Note: 2012 宝山区嘉定区 is a single combined source.doc that yields two
paper_ids (BAOSHAN-ERMO + JIADING-ERMO); both resolve to the same word/,
so one of the two parallel tasks hits "File exists" — this is benign and
the single word/ ends up complete.

Usage:
  ./.venv/bin/python tools/question-bank/batch_extract_docx_source.py
  ./.venv/bin/python tools/question-bank/batch_extract_docx_source.py --parallel 4
  ./.venv/bin/python tools/question-bank/batch_extract_docx_source.py --dry-run
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = str(REPO / ".venv/bin/python")
EXTRACT = REPO / ".codex/skills/math-docx-question-bank-ingestion/scripts/extract_docx_source.py"
SCAN = REPO / "tools/question-bank/scan_pending_ingestions.py"
DOCS = REPO / "documents"

# import archive_dir_name from the prepare tool
sys.path.insert(0, str(REPO / "tools/question-bank"))
from prepare_source_archives import archive_dir_name  # noqa: E402


def scan_pending() -> list[dict]:
    out = subprocess.run([PY, str(SCAN)], cwd=REPO, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)["pending"]


def resolve_archive(paper: dict) -> Path:
    if paper.get("origin") == "dir":
        return REPO / paper["source_rel"]
    m = re.match(r"^(\d{4})-([A-Z]+)-(YIMO|ERMO)$", paper["paper_id"])
    year, code, kind_en = int(m.group(1)), m.group(2), m.group(3)
    kind_cn = "一模" if kind_en == "YIMO" else "二模"
    return DOCS / archive_dir_name(year, code, kind_cn)


def find_source(archive: Path) -> Path | None:
    """source.doc/.docx at archive root, else inside word/ (old layout)."""
    for cand in (archive / "source.doc", archive / "source.docx"):
        if cand.exists():
            return cand
    if (archive / "word").is_dir():
        for cand in (archive / "word" / "source.doc", archive / "word" / "source.docx"):
            if cand.exists():
                return cand
    return None


def build_todo(skip_complete: bool = True) -> tuple[list[dict], list[str]]:
    """Return (tasks-to-extract, skipped-paper-ids-with-reason)."""
    pending = scan_pending()
    tasks: list[dict] = []
    skipped: list[str] = []
    for p in pending:
        archive = resolve_archive(p)
        src = find_source(archive)
        word = archive / "word"
        complete = (
            word.is_dir()
            and (word / "word-source.yaml").exists()
            and (word / "pages").is_dir()
            and any((word / "pages").iterdir())
        )
        if src is None:
            skipped.append(f"NODOC  {p['paper_id']}  (no DOC/DOCX source)")
            continue
        if complete and skip_complete:
            skipped.append(f"DONE   {p['paper_id']}  (word/ already complete)")
            continue
        tasks.append({
            "paper_id": p["paper_id"],
            "source": str(src.relative_to(REPO)),
            "word": str(word.relative_to(REPO)),
        })
    return tasks, skipped


def extract_one(task: dict, timeout: int) -> tuple[str, str, str]:
    src_abs = str(REPO / task["source"])
    word_abs = str(REPO / task["word"])
    # idempotency: skip if already complete (shared-archive races etc.)
    word = Path(word_abs)
    if (word / "word-source.yaml").exists() and (word / "pages").is_dir() and any((word / "pages").iterdir()):
        return ("SKIP", task["paper_id"], "already complete")
    # clear any stale/partial word/ before re-running
    if word.is_dir():
        shutil.rmtree(word, ignore_errors=True)
    t0 = time.time()
    try:
        r = subprocess.run([PY, str(EXTRACT), src_abs, word_abs],
                           capture_output=True, text=True, timeout=timeout)
        dt = int(time.time() - t0)
        ok_yaml = (word / "word-source.yaml").exists()
        pages = list((word / "pages").iterdir()) if (word / "pages").is_dir() else []
        if r.returncode == 0 and ok_yaml and pages:
            return ("OK", task["paper_id"], f"pages={len(pages)} {dt}s")
        detail = f"rc={r.returncode} yaml={ok_yaml} pages={len(pages)} {dt}s"
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:]
        return ("INCOMPLETE", task["paper_id"], detail + (" | " + tail[0][:120] if tail else ""))
    except subprocess.TimeoutExpired:
        return ("FAIL", task["paper_id"], f"timeout>{timeout}s")
    except Exception as e:  # noqa: BLE001
        return ("FAIL", task["paper_id"], f"{type(e).__name__}:{e}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parallel", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=300, help="per-paper seconds")
    ap.add_argument("--dry-run", action="store_true", help="list tasks, do not extract")
    args = ap.parse_args()

    tasks, skipped = build_todo()
    print(f"pending papers: {len(tasks) + len(skipped)}")
    print(f"  to extract: {len(tasks)}")
    print(f"  skipped: {len(skipped)}")
    for s in skipped:
        print(f"    {s}")
    if args.dry_run or not tasks:
        return 0

    counts = {"OK": 0, "SKIP": 0, "FAIL": 0, "INCOMPLETE": 0}
    done = 0
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.parallel) as ex:
        futs = {ex.submit(extract_one, t, args.timeout): t["paper_id"] for t in tasks}
        for fut in as_completed(futs):
            status, pid, detail = fut.result()
            counts[status] += 1
            done += 1
            if status != "OK" or done % 20 == 0:
                print(f"  [{done}/{len(tasks)}] {status} {pid} {detail}")
    print("=== DONE ===")
    for k in ("OK", "SKIP", "FAIL", "INCOMPLETE"):
        print(f"{k}: {counts[k]}")
    print(f"elapsed: {int(time.time() - t0)}s  parallel={args.parallel}")
    # non-zero exit if anything failed, so callers can detect partial runs
    return 1 if counts["FAIL"] or counts["INCOMPLETE"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
