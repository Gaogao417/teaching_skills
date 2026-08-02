from __future__ import annotations

import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription import recover_failed_runs
from scripts.question_transcription.recover_failed_runs import (
    RecoveryResult,
    RunRecord,
    _snapshot_failure,
    recover_one,
    verify_one,
)
from scripts.question_transcription.workflow.contracts import ArtifactRef
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout


def _record(error_class: str, paper_id: str = "PAPER-X", run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        paper_id=paper_id,
        run_id=run_id,
        run_dir=Path(f"/tmp/{paper_id}/{run_id}"),
        error_class=error_class,
        errors=(f"sample {error_class} error",),
    )


def _layout_for(tmp_path: Path, record: RunRecord) -> tuple[Path, RunLayout]:
    # recover_failed_runs._layout builds RunLayout(runs_root.parent, paper, run),
    # so arrange runs_root = <build_root>/question-ingestion to get a tmp-backed run.
    build_root = tmp_path / "build"
    runs_root = build_root / "question-ingestion"
    layout = RunLayout(build_root, record.paper_id, record.run_id)
    layout.ensure()
    return runs_root, layout


def _patch_audit(monkeypatch, *, failure: str | None, detail: str | None) -> None:
    calls: list[bool] = []

    def fake_audit(self, staging_directory, require_approved_review):  # noqa: ANN001
        calls.append(require_approved_review)
        return ("ref", failure, detail)

    monkeypatch.setattr(
        recover_failed_runs.DeterministicStagingAuditor, "audit", fake_audit
    )
    return calls


def test_verify_approved_passes_when_audit_clean(tmp_path, monkeypatch) -> None:
    record = _record("A")
    runs_root, _layout = _layout_for(tmp_path, record)
    _patch_audit(monkeypatch, failure=None, detail=None)

    result = verify_one(record, runs_root=runs_root, aggregate_root=tmp_path / "catalog")

    assert result.status == "verified"
    assert result.stages[0]["node"] == "approved_audit"
    assert result.stages[0]["status"] == "passed"


def test_verify_structural_passes_when_audit_clean_and_backup_complete(
    tmp_path, monkeypatch
) -> None:
    record = _record("B")
    runs_root, layout = _layout_for(tmp_path, record)
    # B/C require a complete recovery-input backup.
    recovery_input = layout.reports_dir / "recovery-input"
    recovery_input.mkdir(parents=True, exist_ok=True)
    for name in ("paper.draft.before.yaml", "state.before.json"):
        (recovery_input / name).write_text("placeholder", encoding="utf-8")
    (recovery_input / "terminal-errors.yaml").write_text("errors: []", encoding="utf-8")
    (recovery_input / "snapshot-hashes.yaml").write_text("hashes: {}", encoding="utf-8")
    require_calls = _patch_audit(monkeypatch, failure=None, detail=None)

    result = verify_one(record, runs_root=runs_root, aggregate_root=tmp_path / "catalog")

    assert result.status == "verified"
    # B-class gate must be structural, not approved.
    assert require_calls == [False]
    audit_stages = [s for s in result.stages if s["node"] == "audit_staging"]
    assert audit_stages and audit_stages[0]["status"] == "passed"


def test_verify_blocks_when_audit_fails(tmp_path, monkeypatch) -> None:
    record = _record("A")
    runs_root, _layout = _layout_for(tmp_path, record)
    _patch_audit(monkeypatch, failure="audit_failed", detail="boom")

    result = verify_one(record, runs_root=runs_root, aggregate_root=tmp_path / "catalog")

    assert result.status == "blocked"
    assert result.detail.startswith("approved_audit: audit_failed: boom")


def test_verify_blocks_when_recovery_input_missing(tmp_path, monkeypatch) -> None:
    record = _record("C")
    runs_root, _layout = _layout_for(tmp_path, record)
    # audit is clean, but recovery-input backup is absent.
    _patch_audit(monkeypatch, failure=None, detail=None)

    result = verify_one(record, runs_root=runs_root, aggregate_root=tmp_path / "catalog")

    assert result.status == "blocked"
    # recovery_input is checked BEFORE the audit, so it is the blocking node and
    # the audit stage never runs.
    assert result.detail.startswith("recovery_input: missing")
    assert [stage["node"] for stage in result.stages] == ["recovery_input"]


def test_verify_skips_non_recoverable_class(tmp_path) -> None:
    record = _record("D")
    runs_root, _layout = _layout_for(tmp_path, record)

    result = verify_one(record, runs_root=runs_root, aggregate_root=tmp_path / "catalog")

    assert result.status == "skipped"


def test_snapshot_failure_writes_hashes_for_copied_backups(tmp_path) -> None:
    record = _record("B")
    _runs_root, layout = _layout_for(tmp_path, record)
    # Source draft + state exist; snapshot must copy + hash them.
    layout.draft_path.write_text("draft: v1", encoding="utf-8")
    (layout.root / "state.json").write_text('{"source_kind": "docx"}', encoding="utf-8")

    _snapshot_failure(record, layout)

    target = layout.reports_dir / "recovery-input"
    hashes = yaml.safe_load((target / "snapshot-hashes.yaml").read_text(encoding="utf-8"))
    assert hashes["schema"] == "question_ingestion_snapshot_hashes/v1"
    assert hashes["paper_id"] == "PAPER-X"
    assert set(hashes["hashes"]) == {"paper.draft.before.yaml", "state.before.json"}
    assert all(v.startswith("sha256:") for v in hashes["hashes"].values())


def test_recover_one_threads_layout_override_into_evidence_completer(
    tmp_path, monkeypatch
) -> None:
    """The --layout/--layout-override-seeds flags reach the evidence completer.

    A B-class replay must forward the human-confirmed layout (and the seed-repair
    opt-in) to ``DeterministicEvidenceCompleter.complete``. Without this wiring
    the recover command could not unblock the 'cannot infer Word source layout'
    runs at all.
    """
    record = _record("B")
    runs_root, layout = _layout_for(tmp_path, record)
    # The B/C replay path needs a source paper + state with a source_kind.
    layout.source_paper_path.write_text("paper: {}", encoding="utf-8")
    (layout.root / "state.json").write_text('{"source_kind": "docx"}', encoding="utf-8")

    seen: dict = {}

    def fake_project(self, source_ref):  # noqa: ANN001
        return (
            ArtifactRef(
                path="structured/paper.draft.yaml",
                sha256="sha256:" + "0" * 64,
                schema="x",
            ),
            None,
            None,
        )

    def fake_complete(  # noqa: ANN001
        self, draft_ref, source_kind, layout=None, layout_override_seeds=False
    ):
        seen["source_kind"] = source_kind
        seen["layout"] = layout
        seen["layout_override_seeds"] = layout_override_seeds
        return draft_ref, None, None

    def fake_expand(self, draft_ref):  # noqa: ANN001
        return str(layout.structured_dir), None, None

    def fake_materialize(self, staging_directory):  # noqa: ANN001
        return None, None, None

    monkeypatch.setattr(
        recover_failed_runs.DeterministicDraftProjector, "project", fake_project
    )
    monkeypatch.setattr(
        recover_failed_runs.DeterministicEvidenceCompleter, "complete", fake_complete
    )
    monkeypatch.setattr(
        recover_failed_runs.DeterministicStagingExpander, "expand", fake_expand
    )
    monkeypatch.setattr(
        recover_failed_runs.DeterministicAssetMaterializer,
        "materialize",
        fake_materialize,
    )
    _patch_audit(monkeypatch, failure=None, detail=None)

    result = recover_one(
        record,
        runs_root=runs_root,
        aggregate_root=tmp_path / "catalog",
        word_evidence_layout="separated",
        word_evidence_override_seeds=True,
    )

    assert result.status == "recovered"
    assert seen == {
        "source_kind": "docx",
        "layout": "separated",
        "layout_override_seeds": True,
    }
