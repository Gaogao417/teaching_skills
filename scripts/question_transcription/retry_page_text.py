#!/usr/bin/env python3
"""Re-run page-text OCR for the missing pages of a terminal E-class run.

A terminal E-class run failed at the ``page_barrier`` because a handful of pages
hit transient provider errors (``RemoteProtocolError`` / ``ReadTimeout`` /
``ConnectError``). Most pages already have a committed ``page-NNN.txt``; only the
missing ones need re-extraction. Starting a whole new run would discard the
per-run content-addressed OCR cache and re-bill every page; this command replays
*only* the missing pages against the existing run directory, so cache hits stay
free and the completed pages are untouched.

After every missing page is filled, the run's ``state.json`` is rewritten in
place (never the SQLite checkpoint) to drop ``terminal_errors`` and refresh
``page_text_extracts`` from the on-disk sidecars, so the run no longer classifies
as E.

Scope note: an E-class run died at ``page_barrier``, *before*
``transcribe_whole_paper`` / ``build_source_paper`` / ``build_draft``, so it has
no source paper or draft on disk and no surviving SQLite checkpoint. Filling the
missing pages does NOT by itself produce staging — it only unblocks the
page-text barrier. The remaining downstream stages (whole-paper transcription,
source-paper build, draft/split/audit) require a separate graph run that reuses
this run directory. This command deliberately stops at the page-text layer; it
does not fake the downstream replay.

This command calls the configured OCR provider and therefore needs the matching
API key (``DASHSCOPE_API_KEY`` for ``--provider qwen``, ``MIMO_API_KEY`` for
``--provider mimo``); load it with ``source ~/.zshrc`` before running.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.question_transcription.workflow.bootstrap.composition import (
    _bind_page_text,
)
from scripts.question_transcription.workflow.bootstrap.config import (
    PageTextProviderChoice,
    RuntimeAdapterConfig,
)
from scripts.question_transcription.workflow.contracts import PageTextJob
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "build" / "question-ingestion"


@dataclass(frozen=True)
class PageTextRun:
    paper_id: str
    run_id: str
    run_dir: Path
    jobs: tuple[PageTextJob, ...]


def _load_run(state_path: Path) -> PageTextRun | None:
    """Read a terminal run's frozen ``page_text_jobs`` from its state.json.

    Returns None (and is skipped by the caller) when the run is not an E-class
    page-extraction failure -- those have no ``page_text_jobs`` worth retrying.
    """
    state = json.loads(state_path.read_text(encoding="utf-8"))
    raw_jobs = state.get("page_text_jobs") or []
    if not raw_jobs:
        return None
    errors = state.get("terminal_errors") or []
    if not any("page extraction failed" in str(error) for error in errors):
        return None
    jobs = tuple(
        PageTextJob.model_validate(job if isinstance(job, dict) else json.loads(job))
        for job in raw_jobs
    )
    run_dir = state_path.parent
    return PageTextRun(
        paper_id=str(state.get("paper_id") or run_dir.parent.name),
        run_id=str(state.get("run_id") or run_dir.name),
        run_dir=run_dir,
        jobs=jobs,
    )


def inventory(runs_root: Path) -> list[PageTextRun]:
    records: list[PageTextRun] = []
    for state_path in sorted(runs_root.glob("*/*/state.json")):
        record = _load_run(state_path)
        if record is not None:
            records.append(record)
    return records


def _missing_pages(run: PageTextRun) -> list[PageTextJob]:
    """The page jobs whose ``page-NNN.txt`` is absent or blank on disk."""
    missing: list[PageTextJob] = []
    pages_dir = run.run_dir / "pages"
    for job in sorted(run.jobs, key=lambda j: j.page_number):
        text_path = pages_dir / f"page-{job.page_number:03d}.txt"
        if not text_path.is_file() or not text_path.read_text(encoding="utf-8").strip():
            missing.append(job)
    return missing


def _build_extractor(provider: PageTextProviderChoice, store: ArtifactStore):
    config = RuntimeAdapterConfig(page_text_provider=provider)
    return _bind_page_text(config, store)


def _rewrite_state_after_recovery(run: PageTextRun) -> None:
    """Drop terminal_errors and refresh page_text_extracts from on-disk sidecars.

    Only ``state.json`` (the terminal run's serialized state) is rewritten; the
    LangGraph SQLite checkpoint is never touched, so the original terminal node
    and its error record stay intact as regression evidence.
    """
    from scripts.question_transcription.workflow.infrastructure.artifact_store import (  # noqa: PLC0415
        sha256_file,
    )

    state_path = run.run_dir / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["terminal_errors"] = []
    # Rebuild extracts from sidecars so the deterministic downstream replay sees a
    # complete, consistent page-text set without re-deriving it from the graph.
    # Each ArtifactRef carries a sha256, so recompute it from the committed files
    # rather than leaving the field blank (the contract requires the pattern).
    pages_dir = run.run_dir / "pages"
    sidecars = sorted(pages_dir.glob("page-*.extract.yaml"))
    import yaml  # noqa: PLC0415

    extracts: list[dict[str, Any]] = []
    for sidecar in sidecars:
        meta = yaml.safe_load(sidecar.read_text(encoding="utf-8")) or {}
        page_number = meta.get("page_number")
        if not isinstance(page_number, int):
            continue
        text_path = pages_dir / f"page-{page_number:03d}.txt"
        extracts.append(
            {
                "artifact": {
                    "page_number": page_number,
                    "text": {
                        "path": f"pages/page-{page_number:03d}.txt",
                        "sha256": sha256_file(text_path),
                        "schema": "text/plain",
                    },
                    "metadata": {
                        "path": sidecar.relative_to(run.run_dir).as_posix(),
                        "sha256": sha256_file(sidecar),
                        "schema": meta.get("schema") or "page-text-extract/v1",
                    },
                    "provenance": {
                        "adapter_id": meta.get("adapter_id") or "qwen",
                        "model": meta.get("model") or "",
                        "prompt_version": meta.get("prompt_version")
                        or "page-text-ocr-v1",
                    },
                }
            }
        )
    state["page_text_extracts"] = extracts
    state["page_text_failures"] = []
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def retry_one(
    run: PageTextRun,
    *,
    provider: PageTextProviderChoice,
    apply: bool,
) -> tuple[int, int, str | None]:
    """Re-extract missing pages for one run.

    Returns ``(missing_count, reextracted_count, failure_detail)``. When
    ``apply`` is False the function only counts and reports; when True it calls
    the OCR provider for each missing page.
    """
    missing = _missing_pages(run)
    if not missing:
        return 0, 0, None
    if not apply:
        return len(missing), 0, None

    layout = RunLayout(
        run.run_dir.parents[2], run.paper_id, run.run_id
    )
    store = ArtifactStore(layout)
    extractor = _build_extractor(provider, store)

    failures: list[str] = []
    reextracted = 0
    for job in missing:
        extract, failure = extractor.extract(job)
        if failure is not None:
            failures.append(f"page {job.page_number}: {failure.kind} ({failure.detail})")
            continue
        if extract is None:
            failures.append(f"page {job.page_number}: no extract returned")
            continue
        text = store.read_text(extract.artifact.text)
        if not text.strip():
            failures.append(f"page {job.page_number}: blank text (contract failure)")
            continue
        reextracted += 1

    if failures:
        return len(missing), reextracted, "; ".join(failures)
    _rewrite_state_after_recovery(run)
    return len(missing), reextracted, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument(
        "--provider",
        choices=("qwen", "mimo"),
        default="qwen",
        help="page-text OCR provider (qwen uses DASHSCOPE_API_KEY, mimo uses MIMO_API_KEY)",
    )
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="re-extract missing pages; without this flag only print the inventory",
    )
    args = parser.parse_args(argv)

    runs_root = args.runs_root.resolve()
    records = [
        record
        for record in inventory(runs_root)
        if not args.paper_id or record.paper_id in set(args.paper_id)
    ]
    if args.limit is not None:
        records = records[: args.limit]

    if not args.apply:
        total_missing = 0
        for record in records:
            missing = _missing_pages(record)
            total_missing += len(missing)
            pages = ", ".join(str(job.page_number) for job in missing[:10])
            more = f" +{len(missing) - 10} more" if len(missing) > 10 else ""
            print(
                f"DRY-RUN {record.paper_id} {record.run_id} "
                f"jobs={len(record.jobs)} missing={len(missing)} pages=[{pages}{more}]"
            )
        print(
            f"SUMMARY runs={len(records)} missing_pages={total_missing} "
            f"(pass --apply to re-extract)"
        )
        return 0

    filled = blocked = 0
    for record in records:
        missing_count, reextracted, failure = retry_one(
            record, provider=args.provider, apply=True
        )
        if failure is not None:
            blocked += 1
            print(
                f"BLOCKED {record.paper_id} {record.run_id} "
                f"missing={missing_count} reextracted={reextracted} :: {failure}"
            )
            continue
        filled += 1
        print(
            f"FILLED {record.paper_id} {record.run_id} "
            f"missing={missing_count} reextracted={reextracted}"
        )

    print(
        f"SUMMARY filled={filled} blocked={blocked} provider={args.provider} "
        f"(E-class runs still need a downstream graph run to reach staging)"
    )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
