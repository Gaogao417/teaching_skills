from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXAM_SOURCE_SCRIPTS = (
    ROOT / ".codex/skills/math-topic-question-bank/scripts"
)
if str(EXAM_SOURCE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(EXAM_SOURCE_SCRIPTS))

from exam_source_contracts import ExamItemReview
from scripts.question_transcription.workflow import run_live_paper
from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
    DeterministicCatalogNotifier,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.run_live_paper import (
    _approve_final_review,
)


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


def test_catalog_notifier_exposes_run_staging_to_review_ui(tmp_path: Path) -> None:
    store = _store(tmp_path)
    staging = store.layout.structured_dir
    (staging / "paper.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_paper/v1",
                "paper": {"id": "p", "title": "Paper P"},
                "sections": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    notifier = DeterministicCatalogNotifier(store)
    result, failure, detail = notifier.refresh(str(staging))

    assert (result, failure, detail) == (None, None, None)
    catalog_root = store.layout.root / "review-catalog"
    alias = catalog_root / "langgraph" / "staging" / "p"
    assert alias.is_symlink()
    assert alias.resolve() == staging.resolve()
    assert (staging / ".catalog-version").is_file()
    assert list(catalog_root.glob("*/staging/*/paper.yaml")) == [
        alias / "paper.yaml"
    ]


def test_auto_approval_copies_source_identity_and_current_hash(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "PAPER-A"
    item_dir = staging / "items" / "Q001"
    item_dir.mkdir(parents=True)
    source = {
        "schema": "math_exam_item_source/v1",
        "item_id": "Q001",
        "source_key": "PAPER-A-Q01",
        "content_hash": f"sha256:{'1' * 64}",
    }
    (item_dir / "source.yaml").write_text(
        yaml.safe_dump(source, sort_keys=False), encoding="utf-8"
    )

    assert _approve_final_review(str(staging)) == 1

    review = yaml.safe_load((item_dir / "review.yaml").read_text(encoding="utf-8"))
    assert review["schema"] == "math_exam_item_review/v1"
    assert review["item_id"] == source["item_id"]
    assert review["source_key"] == source["source_key"]
    assert review["content_hash"] == source["content_hash"]
    assert review["status"] == "approved"
    assert review["reviewer"] == "live-verification-driver"
    assert review["reviewed_at"]
    assert review["notes"] == []
    ExamItemReview.model_validate(review)


def test_auto_approval_rebinds_stale_review_to_current_source_hash(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "PAPER-A"
    item_dir = staging / "items" / "Q001"
    item_dir.mkdir(parents=True)
    current_hash = f"sha256:{'2' * 64}"
    (item_dir / "source.yaml").write_text(
        yaml.safe_dump(
            {
                "item_id": "Q001",
                "source_key": "PAPER-A-Q01",
                "content_hash": current_hash,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (item_dir / "review.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_exam_item_review/v1",
                "item_id": "Q001",
                "status": "pending",
                "content_hash": f"sha256:{'1' * 64}",
                "notes": ["keep this note"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    _approve_final_review(str(staging))

    review = yaml.safe_load((item_dir / "review.yaml").read_text(encoding="utf-8"))
    assert review["source_key"] == "PAPER-A-Q01"
    assert review["content_hash"] == current_hash
    assert review["notes"] == ["keep this note"]


def test_cli_defaults_to_human_final_review(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "paper.docx"
    source.write_bytes(b"placeholder")
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return "run-test"

    monkeypatch.setattr(run_live_paper, "run", fake_run)

    assert (
        run_live_paper.main(
            [
                "--paper-id",
                "PAPER-A",
                "--source",
                str(source),
                "--source-kind",
                "docx",
            ]
        )
        == 0
    )
    assert captured["final_review_mode"] == "human"


def test_cli_resumes_existing_review_checkpoint_without_source(monkeypatch) -> None:
    captured = {}

    def fake_resume(**kwargs):
        captured.update(kwargs)
        return kwargs["run_id"]

    monkeypatch.setattr(run_live_paper, "resume", fake_resume)

    assert (
        run_live_paper.main(
            [
                "--paper-id",
                "PAPER-A",
                "--resume-run-id",
                "run-123",
            ]
        )
        == 0
    )
    assert captured == {
        "paper_id": "PAPER-A",
        "run_id": "run-123",
        "agent_host": "claude-code",
        "page_provider": "qwen",
    }
