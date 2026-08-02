#!/usr/bin/env python3
"""Audit and deterministically recover terminal question-ingestion runs.

Terminal LangGraph checkpoints cannot be resumed because they have no pending task.
This command therefore replays only the deterministic downstream node sequence on
the existing run artifacts.  It never calls OCR/LLM providers and never creates or
changes review decisions.

Recovery policy:

* A (malformed/stale approved review): re-run approved audit, then expose staging.
  The command does not manufacture approvals; invalid reviews remain blocked.
* B (Word evidence coverage) and C (multi-crop assignment_path): only runs with no
  ``review.yaml`` may replay build_draft -> complete_evidence -> split ->
  build_assets -> audit -> refresh_review_ui.
* Other classes are inventory-only and require a separate source/provider repair.

Before a B/C replay, the failing draft and state are copied to
``reports/recovery-input/`` and their sha256 digests are recorded in
``reports/recovery-input/snapshot-hashes.yaml``.  ``state.json`` and the SQLite
checkpoint are never rewritten, so the original terminal node/error remain
available as regression evidence.

``--verify`` re-runs the read-only audits against the artifacts already on disk
and checks the recovery-input backup + review-catalog alias, but never invokes
the four writing adapters (build_draft / complete_evidence / split /
build_assets) and never refreshes the catalog.  It therefore cannot prove the
replay chain can *rebuild* artifacts — only that the last ``--apply`` output
still passes its gate (approved for A, structural for B/C).  Failures are
localised by node name and the process exits non-zero.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
    DeterministicAssetMaterializer,
    DeterministicCatalogNotifier,
    DeterministicDraftProjector,
    DeterministicEvidenceCompleter,
    DeterministicStagingAuditor,
    DeterministicStagingExpander,
)
from scripts.question_transcription.workflow.contracts import ArtifactRef
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
    sha256_file,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "build" / "question-ingestion"
RECOVERABLE_CLASSES = {"A", "B", "C"}


@dataclass(frozen=True)
class RunRecord:
    paper_id: str
    run_id: str
    run_dir: Path
    error_class: str
    errors: tuple[str, ...]


@dataclass
class RecoveryResult:
    record: RunRecord
    status: str
    stages: list[dict] = field(default_factory=list)
    detail: str | None = None
    catalog_alias: str | None = None


def classify_errors(errors: Iterable[str]) -> str:
    """Reproduce the historical exclusive A/B/C/D/E/Z error buckets."""

    values = tuple(str(error) for error in errors)
    joined = "\n".join(values)
    if "approved_audit:" in joined:
        return "A"
    if "Word evidence coverage:" in joined:
        return "B"
    if "assignment_path when there are multiple crops" in joined:
        return "C"
    if any(error.startswith("build_draft:") for error in values):
        return "D"
    if any(error.startswith("page extraction failed:") for error in values):
        return "E"
    return "Z"


def inventory(runs_root: Path) -> list[RunRecord]:
    records: list[RunRecord] = []
    for state_path in sorted(runs_root.glob("*/*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        errors = tuple(str(value) for value in state.get("terminal_errors") or [])
        run_dir = state_path.parent
        records.append(
            RunRecord(
                paper_id=str(state.get("paper_id") or run_dir.parent.name),
                run_id=str(state.get("run_id") or run_dir.name),
                run_dir=run_dir,
                error_class=classify_errors(errors),
                errors=errors,
            )
        )
    return records


def _layout(record: RunRecord, runs_root: Path) -> RunLayout:
    # runs_root is <build-root>/question-ingestion.
    return RunLayout(runs_root.parent, record.paper_id, record.run_id)


def _snapshot_failure(record: RunRecord, layout: RunLayout) -> None:
    target = layout.reports_dir / "recovery-input"
    target.mkdir(parents=True, exist_ok=True)
    for source, name in (
        (layout.draft_path, "paper.draft.before.yaml"),
        (layout.root / "state.json", "state.before.json"),
    ):
        destination = target / name
        if source.is_file() and not destination.exists():
            shutil.copy2(source, destination)
    errors_path = target / "terminal-errors.yaml"
    if not errors_path.exists():
        errors_path.write_text(
            yaml.safe_dump(
                {
                    "schema": "question_ingestion_recovery_input/v1",
                    "paper_id": record.paper_id,
                    "run_id": record.run_id,
                    "error_class": record.error_class,
                    "terminal_errors": list(record.errors),
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )
    # Record sha256 of the just-copied backups so the pre-replay state is
    # traceable. This is read-only over the copies (never over state.json or the
    # SQLite checkpoint themselves, which this command never rewrites).
    hashes_path = target / "snapshot-hashes.yaml"
    if not hashes_path.exists():
        digests: dict[str, str] = {}
        for name in ("paper.draft.before.yaml", "state.before.json"):
            backup = target / name
            if backup.is_file():
                digests[name] = sha256_file(backup)
        hashes_path.write_text(
            yaml.safe_dump(
                {
                    "schema": "question_ingestion_snapshot_hashes/v1",
                    "paper_id": record.paper_id,
                    "run_id": record.run_id,
                    "hashes": digests,
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )


def _source_paper_ref(layout: RunLayout) -> ArtifactRef:
    if not layout.source_paper_path.is_file():
        raise FileNotFoundError(f"source paper missing: {layout.source_paper_path}")
    return ArtifactRef(
        path=str(layout.source_paper_path.relative_to(layout.root)),
        sha256=sha256_file(layout.source_paper_path),
        schema="math_exam_source_paper/v2",
    )


def _record_stage(
    result: RecoveryResult,
    node: str,
    failure: str | None,
    detail: str | None,
) -> bool:
    result.stages.append(
        {
            "node": node,
            "status": "passed" if failure is None else "failed",
            **({"failure": failure, "detail": detail} if failure else {}),
        }
    )
    if failure is not None:
        result.status = "blocked"
        result.detail = f"{node}: {failure}: {detail}"
        return False
    return True


def _aggregate_alias(
    aggregate_root: Path, record: RunRecord, staging_directory: str
) -> Path:
    alias = (
        aggregate_root
        / f"langgraph-recovery-{record.run_id}"
        / "staging"
        / record.paper_id
    )
    alias.parent.mkdir(parents=True, exist_ok=True)
    target = Path(staging_directory).resolve()
    if alias.is_symlink():
        if alias.resolve() != target:
            raise ValueError(
                f"aggregate alias points at {alias.resolve()}, expected {target}"
            )
    elif alias.exists():
        raise ValueError(f"aggregate alias is not a symlink: {alias}")
    else:
        alias.symlink_to(
            os.path.relpath(target, start=alias.parent),
            target_is_directory=True,
        )
    # Migrate the first recovery-catalog layout.  It grouped every run into one
    # source bank, so duplicate paper ids were intentionally hidden by Review UI.
    legacy = (
        aggregate_root
        / "langgraph-recovery"
        / "staging"
        / f"{record.paper_id}--{record.run_id}"
    )
    if legacy.is_symlink() and legacy.resolve() == target:
        legacy.unlink()
    return alias


def recover_one(
    record: RunRecord,
    *,
    runs_root: Path,
    aggregate_root: Path,
) -> RecoveryResult:
    result = RecoveryResult(record=record, status="running")
    if record.error_class not in RECOVERABLE_CLASSES:
        result.status = "skipped"
        result.detail = "class is not deterministic-recovery eligible"
        return result

    layout = _layout(record, runs_root)
    store = ArtifactStore(layout)
    staging = str(layout.structured_dir)
    auditor = DeterministicStagingAuditor(store)
    notifier = DeterministicCatalogNotifier(store)

    if record.error_class == "A":
        _, failure, detail = auditor.audit(staging, require_approved_review=True)
        if not _record_stage(result, "approved_audit", failure, detail):
            return result
    else:
        reviews = sorted(layout.structured_dir.glob("items/*/review.yaml"))
        if reviews:
            result.status = "blocked"
            result.detail = (
                "refusing deterministic replay because review.yaml exists: "
                + ", ".join(str(path) for path in reviews[:3])
            )
            return result
        _snapshot_failure(record, layout)

        projector = DeterministicDraftProjector(store)
        draft_ref, failure, detail = projector.project(_source_paper_ref(layout))
        if not _record_stage(result, "build_draft", failure, detail):
            return result

        completer = DeterministicEvidenceCompleter(store)
        draft_ref, failure, detail = completer.complete(
            draft_ref,
            json.loads((layout.root / "state.json").read_text(encoding="utf-8"))[
                "source_kind"
            ],
        )
        if not _record_stage(result, "complete_evidence", failure, detail):
            return result

        staging, failure, detail = DeterministicStagingExpander(store).expand(draft_ref)
        if not _record_stage(result, "split_into_questions", failure, detail):
            return result

        _, failure, detail = DeterministicAssetMaterializer(store).materialize(staging)
        if not _record_stage(result, "build_assets", failure, detail):
            return result

        _, failure, detail = auditor.audit(staging, require_approved_review=False)
        if not _record_stage(result, "audit_staging", failure, detail):
            return result

    _, failure, detail = notifier.refresh(staging)
    if not _record_stage(result, "refresh_review_ui", failure, detail):
        return result
    alias = _aggregate_alias(aggregate_root, record, staging)
    result.catalog_alias = str(alias)
    result.status = "recovered"
    return result


def verify_one(
    record: RunRecord,
    *,
    runs_root: Path,
    aggregate_root: Path,
) -> RecoveryResult:
    """Read-only re-check of an already-recovered run.

    Re-runs the gate audit (approved for A, structural for B/C) against the
    staging artifacts currently on disk and confirms the recovery-input backup
    and review-catalog alias are intact.  It never calls the four writing
    adapters and never refreshes the catalog, so it validates "the last
    ``--apply`` output still passes" rather than "the replay chain can rebuild".
    """
    result = RecoveryResult(record=record, status="running")
    if record.error_class not in RECOVERABLE_CLASSES:
        result.status = "skipped"
        result.detail = "class is not deterministic-recovery eligible"
        return result

    layout = _layout(record, runs_root)
    store = ArtifactStore(layout)
    staging = str(layout.structured_dir)
    auditor = DeterministicStagingAuditor(store)

    # 1. recovery-input backup must be complete (draft/state/terminal-errors/hashes).
    recovery_input = layout.reports_dir / "recovery-input"
    expected_backup_names = (
        "paper.draft.before.yaml",
        "state.before.json",
        "terminal-errors.yaml",
        "snapshot-hashes.yaml",
    )
    missing_backup = [
        name for name in expected_backup_names if not (recovery_input / name).is_file()
    ]
    # A-class runs never replay, so they have no recovery-input snapshot; only
    # B/C are required to carry one.
    if record.error_class != "A" and missing_backup:
        if not _record_stage(
            result,
            "recovery_input",
            "missing",
            ", ".join(missing_backup),
        ):
            return result

    # 2. re-run the gate audit against the on-disk staging (read-only subprocess).
    require_approved = record.error_class == "A"
    _, failure, detail = auditor.audit(staging, require_approved_review=require_approved)
    gate = "approved_audit" if require_approved else "audit_staging"
    if not _record_stage(result, gate, failure, detail):
        return result

    # 3. the review-catalog alias, if present, must still resolve to this staging.
    alias = (
        aggregate_root
        / f"langgraph-recovery-{record.run_id}"
        / "staging"
        / record.paper_id
    )
    if alias.is_symlink():
        target = Path(staging).resolve()
        if alias.resolve() != target:
            if not _record_stage(
                result,
                "review_catalog_alias",
                "misaligned",
                f"{alias} -> {alias.resolve()}, expected {target}",
            ):
                return result
    elif alias.exists():
        if not _record_stage(
            result,
            "review_catalog_alias",
            "not_a_symlink",
            str(alias),
        ):
            return result
    # A missing alias is allowed: a run may pass audit without having been
    # exposed to the aggregate catalog yet.

    result.status = "verified"
    return result


def _write_result(layout: RunLayout, result: RecoveryResult) -> None:
    ArtifactStore(layout).commit_yaml(
        "reports/recovery-report.yaml",
        {
            "schema": "question_ingestion_recovery_report/v1",
            "paper_id": result.record.paper_id,
            "run_id": result.record.run_id,
            "original_error_class": result.record.error_class,
            "original_terminal_errors": list(result.record.errors),
            "status": result.status,
            "stages": result.stages,
            "detail": result.detail,
            "catalog_alias": result.catalog_alias,
        },
        "question_ingestion_recovery_report/v1",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument(
        "--classes",
        default="A,B,C",
        help="comma-separated historical error classes (default: A,B,C)",
    )
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument(
        "--apply",
        action="store_true",
        help="perform recovery; without this flag only print inventory",
    )
    action_group.add_argument(
        "--verify",
        action="store_true",
        help=(
            "read-only re-check: re-run the gate audit (approved for A, "
            "structural for B/C) against on-disk staging and confirm the "
            "recovery-input backup + catalog alias, without invoking any "
            "writing adapter or refreshing the catalog"
        ),
    )
    args = parser.parse_args(argv)

    runs_root = args.runs_root.resolve()
    requested = {value.strip() for value in args.classes.split(",") if value.strip()}
    records = [
        record
        for record in inventory(runs_root)
        if record.error_class in requested
        and (not args.paper_id or record.paper_id in set(args.paper_id))
    ]
    if args.limit is not None:
        records = records[: args.limit]

    counts: dict[str, int] = {}
    for record in inventory(runs_root):
        counts[record.error_class] = counts.get(record.error_class, 0) + 1
    print("INVENTORY " + " ".join(f"{key}={counts.get(key, 0)}" for key in "ABCDEZ"))
    print(f"SELECTED runs={len(records)} classes={','.join(sorted(requested))}")
    if not args.apply and not args.verify:
        for record in records:
            print(f"DRY-RUN {record.error_class} {record.paper_id} {record.run_id}")
        return 0

    aggregate_root = runs_root / "recovery-review-catalog"

    if args.verify:
        verified = blocked = skipped = 0
        for record in records:
            try:
                result = verify_one(
                    record,
                    runs_root=runs_root,
                    aggregate_root=aggregate_root,
                )
            except Exception as exc:
                result = RecoveryResult(
                    record=record,
                    status="blocked",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            if result.status == "verified":
                verified += 1
            elif result.status == "blocked":
                blocked += 1
            else:
                skipped += 1
            print(
                f"VERIFY {result.status.upper()} {record.error_class} "
                f"{record.paper_id} {record.run_id}"
                + (f" :: {result.detail}" if result.detail else "")
            )
        print(
            f"SUMMARY verified={verified} blocked={blocked} skipped={skipped} "
            f"catalog={aggregate_root}"
        )
        return 1 if blocked else 0
    recovered = blocked = skipped = 0
    for record in records:
        try:
            result = recover_one(
                record,
                runs_root=runs_root,
                aggregate_root=aggregate_root,
            )
        except Exception as exc:
            result = RecoveryResult(
                record=record,
                status="blocked",
                detail=f"{type(exc).__name__}: {exc}",
            )
        _write_result(_layout(record, runs_root), result)
        if result.status == "recovered":
            recovered += 1
        elif result.status == "blocked":
            blocked += 1
        else:
            skipped += 1
        print(
            f"{result.status.upper()} {record.error_class} "
            f"{record.paper_id} {record.run_id}"
            + (f" :: {result.detail}" if result.detail else "")
        )
    print(
        f"SUMMARY recovered={recovered} blocked={blocked} skipped={skipped} "
        f"catalog={aggregate_root}"
    )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
