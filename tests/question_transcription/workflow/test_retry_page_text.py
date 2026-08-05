from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.cli import retry_page_text
from scripts.question_transcription.workflow.contracts import (
    ArtifactRef,
    PageTextJob,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import (
    RunLayout,
)


def _write_state(run_dir: Path, *, paper_id: str, run_id: str, jobs: list[dict],
                 terminal_errors: list[str]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "paper_id": paper_id,
                "run_id": run_id,
                "page_text_jobs": jobs,
                "page_text_extracts": [],
                "page_text_failures": [],
                "terminal_errors": terminal_errors,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _page_job(page_number: int, *, paper_id: str, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "paper_id": paper_id,
        "page_number": page_number,
        "image": {
            "path": f"source/pages/{page_number:03d}.png",
            "sha256": "sha256:" + "a" * 64,
            "schema": "image/png",
        },
        "input_fingerprint": "sha256:" + "a" * 64,
    }


def _make_run(tmp_path: Path) -> tuple[Path, retry_page_text.PageTextRun]:
    """A 3-page E-class run whose page 2 is missing."""
    build_root = tmp_path / "build"
    run_layout = RunLayout(build_root, "PAPER-E", "run-e1")
    run_layout.ensure()
    run_dir = run_layout.root
    jobs = [_page_job(n, paper_id="PAPER-E", run_id="run-e1") for n in (1, 2, 3)]
    _write_state(
        run_dir,
        paper_id="PAPER-E",
        run_id="run-e1",
        jobs=jobs,
        terminal_errors=[
            "page extraction failed: ['page 2: invalid_response (RemoteProtocolError: boom)']"
        ],
    )
    # pages 1 and 3 already have text + sidecar (done); page 2 is missing.
    pages_dir = run_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for n in (1, 3):
        (pages_dir / f"page-{n:03d}.txt").write_text(f"page {n} text\n", encoding="utf-8")
        (pages_dir / f"page-{n:03d}.extract.yaml").write_text(
            yaml.safe_dump(
                {
                    "page_number": n,
                    "model": "qwen3.5-ocr",
                    "adapter_id": "qwen",
                    "prompt_version": "page-text-ocr-v1",
                    "schema": "page-text-extract/v1",
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    # The page images must exist for the extractor to read them.
    for n in (1, 2, 3):
        img = run_dir / "source" / "pages" / f"{n:03d}.png"
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"\x89PNG fake")

    record = retry_page_text.PageTextRun(
        paper_id="PAPER-E",
        run_id="run-e1",
        run_dir=run_dir,
        jobs=tuple(PageTextJob.model_validate(j) for j in jobs),
    )
    return build_root, record


def test_missing_pages_detects_blank_or_absent_text(tmp_path: Path) -> None:
    _, record = _make_run(tmp_path)

    missing = retry_page_text._missing_pages(record)

    assert [job.page_number for job in missing] == [2]


def test_dry_run_reports_inventory_without_calling_provider(tmp_path: Path) -> None:
    build_root, _record = _make_run(tmp_path)
    runs_root = build_root / "question-ingestion"

    exit_code = retry_page_text.main(
        ["--runs-root", str(runs_root)]
    )

    assert exit_code == 0
    # No state mutation in dry-run.
    state = json.loads(
        (runs_root / "PAPER-E" / "run-e1" / "state.json").read_text(encoding="utf-8")
    )
    assert state["terminal_errors"]  # unchanged


def test_apply_re_extracts_only_missing_pages_and_clears_errors(
    tmp_path: Path, monkeypatch
) -> None:
    _build_root, record = _make_run(tmp_path)
    called: list[int] = []

    class FakeExtractor:
        def extract(self, job: PageTextJob):  # noqa: ANN001
            called.append(job.page_number)
            from scripts.question_transcription.workflow.contracts import (
                ExecutionProvenance,
                PageTextArtifact,
                PageTextExtract,
            )
            from scripts.question_transcription.workflow.adapters.page_text._common import (
                commit_extract,
            )
            from scripts.question_transcription.workflow.infrastructure.artifact_store import (
                ArtifactStore,
            )

            store = ArtifactStore(
                RunLayout(record.run_dir.parents[2], record.paper_id, record.run_id)
            )
            extract = commit_extract(
                job=job,
                text=f"recovered page {job.page_number}",
                store=store,
                model="qwen3.5-ocr",
                adapter_id="qwen",
                prompt_version="page-text-ocr-v1",
                cache_hit=False,
            )
            return extract, None

    monkeypatch.setattr(
        retry_page_text, "_build_extractor", lambda provider, store: FakeExtractor()
    )

    missing_count, reextracted, failure = retry_page_text.retry_one(
        record, provider="qwen", apply=True
    )

    assert (missing_count, reextracted, failure) == (1, 1, None)
    # Only the missing page (2) was re-extracted; pages 1 and 3 untouched.
    assert called == [2]
    # state.json cleared and page_text_extracts rebuilt from all 3 sidecars.
    state = json.loads((record.run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_errors"] == []
    assert state["page_text_failures"] == []
    assert len(state["page_text_extracts"]) == 3
    # The reconstructed extracts must validate against the contract.
    from scripts.question_transcription.workflow.contracts import PageTextExtract

    for entry in state["page_text_extracts"]:
        PageTextExtract.model_validate(entry)


def test_apply_records_failure_without_clearing_state(tmp_path: Path, monkeypatch) -> None:
    _build_root, record = _make_run(tmp_path)

    class FailingExtractor:
        def extract(self, job: PageTextJob):  # noqa: ANN001
            from scripts.question_transcription.workflow.contracts import PageTextFailure

            return None, PageTextFailure(
                adapter_id="qwen",
                kind="invalid_response",
                attempts=3,
                detail="still timing out",
            )

    monkeypatch.setattr(
        retry_page_text, "_build_extractor", lambda provider, store: FailingExtractor()
    )

    missing_count, reextracted, failure = retry_page_text.retry_one(
        record, provider="qwen", apply=True
    )

    assert reextracted == 0
    assert failure is not None and "page 2" in failure and "invalid_response" in failure
    # On failure the terminal_errors must remain intact (no silent masking).
    state = json.loads((record.run_dir / "state.json").read_text(encoding="utf-8"))
    assert state["terminal_errors"]  # unchanged


def test_non_e_runs_are_skipped_by_inventory(tmp_path: Path) -> None:
    build_root = tmp_path / "build"
    run_layout = RunLayout(build_root, "PAPER-OK", "run-ok")
    run_layout.ensure()
    # A run whose terminal error is NOT a page-extraction failure.
    _write_state(
        run_layout.root,
        paper_id="PAPER-OK",
        run_id="run-ok",
        jobs=[_page_job(1, paper_id="PAPER-OK", run_id="run-ok")],
        terminal_errors=["audit: audit_failed: STAGING INVALID"],
    )

    records = retry_page_text.inventory(build_root / "question-ingestion")

    assert records == []
