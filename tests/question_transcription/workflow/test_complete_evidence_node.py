from __future__ import annotations

import sys
from pathlib import Path

import yaml
from PIL import Image


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.staging import existing_pipeline
from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
    DeterministicAssetMaterializer,
    DeterministicEvidenceCompleter,
    DeterministicStagingAuditor,
    DeterministicStagingExpander,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.contracts import ArtifactRef
from scripts.question_transcription.workflow.nodes.downstream import (
    make_complete_evidence_node,
)


def _page(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 96), "white").save(path)


def _draft(repo: Path) -> dict:
    pages = repo / "documents" / "PAPER-EVIDENCE" / "word" / "pages"
    for page in range(1, 6):
        _page(pages / f"{page:03d}.png")

    def evidence(page: int) -> list[dict]:
        return [
            {
                "page_image": str(pages / f"{page:03d}.png"),
                "page_number": page,
            }
        ]

    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {
            "id": "PAPER-EVIDENCE",
            "title": "Word evidence regression",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": str(repo / "documents" / "PAPER-EVIDENCE"),
        },
        "question_bank": "../../question-bank.yaml",
        "sections": [
            {
                "id": "choice",
                "title": "一、选择题",
                "items": [
                    {
                        "item_id": "Q001",
                        "question_number": 1,
                        "question_type": "choice",
                        "points": 3,
                        "question_word_evidence": evidence(1),
                        "prompt": [],
                        "official_solution": {
                            "start_anchor": "1.",
                            "end_anchor": "2.",
                            "word_evidence": evidence(2),
                            "crops": [],
                        },
                        "block": {
                            "stem_latex": "第一题",
                            "choices": ["甲", "乙", "丙", "丁"],
                            "answer": "A",
                            "clue": "逐项判断。",
                        },
                    },
                    {
                        "item_id": "Q002",
                        "question_number": 2,
                        "question_type": "choice",
                        "points": 3,
                        "question_word_evidence": evidence(3),
                        "prompt": [],
                        "official_solution": {
                            "start_anchor": "2.",
                            "end_anchor": "<END_OF_SOURCE>",
                            "word_evidence": evidence(4),
                            "crops": [],
                        },
                        "block": {
                            "stem_latex": "第二题",
                            "choices": ["甲", "乙", "丙", "丁"],
                            "answer": "B",
                            "clue": "逐项判断。",
                        },
                    },
                ],
            }
        ],
    }


def _store(tmp_path: Path) -> ArtifactStore:
    (tmp_path / ".codex").symlink_to(ROOT / ".codex", target_is_directory=True)
    (tmp_path / ".venv").symlink_to(ROOT / ".venv", target_is_directory=True)
    layout = RunLayout(tmp_path / "build", "PAPER-EVIDENCE", "run-regression")
    layout.ensure()
    return ArtifactStore(layout)


def test_complete_evidence_node_fills_last_page_and_real_audit_passes(
    tmp_path: Path, monkeypatch
) -> None:
    """Regression for the 155 runs that stopped at Word coverage audit.

    This exercises the actual ``complete_evidence`` graph node, then the real
    expand/materialize/audit adapters.  A direct unit test of
    ``word_evidence_pages`` alone would not catch the missing workflow wiring.
    """

    monkeypatch.setattr(existing_pipeline, "repo_root", lambda: tmp_path)
    store = _store(tmp_path)
    draft_ref = store.commit_yaml(
        "structured/paper.draft.yaml",
        _draft(tmp_path),
        "math_exam_staging_draft/v1",
    )
    deps = type(
        "Deps",
        (),
        {
            "deterministic": type(
                "Ports",
                (),
                {"evidence_completer": DeterministicEvidenceCompleter(store)},
            )()
        },
    )()

    result = make_complete_evidence_node(deps)(
        {
            "draft": draft_ref.model_dump(mode="json"),
            "source_kind": "docx",
        }
    )

    assert "terminal_errors" not in result
    completed_ref = ArtifactRef.model_validate(result["draft"])
    completed = store.read_yaml(completed_ref)
    q2 = completed["sections"][0]["items"][1]
    assert [
        entry["page_number"]
        for entry in q2["official_solution"]["word_evidence"]
    ] == [4, 5]
    report = yaml.safe_load(
        (store.layout.reports_dir / "word-evidence-report.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert report["last_page"] == 5
    assert report["changes"]

    staging, failure, detail = DeterministicStagingExpander(store).expand(
        completed_ref
    )
    assert (failure, detail) == (None, None)
    _, failure, detail = DeterministicAssetMaterializer(store).materialize(staging)
    assert (failure, detail) == (None, None)
    _, failure, detail = DeterministicStagingAuditor(store).audit(
        staging, require_approved_review=False
    )
    assert (failure, detail) == (None, None)


def test_complete_evidence_node_reports_its_own_stage_on_invalid_seed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(existing_pipeline, "repo_root", lambda: tmp_path)
    store = _store(tmp_path)
    draft = _draft(tmp_path)
    draft["sections"][0]["items"][1]["official_solution"]["word_evidence"] = []
    draft_ref = store.commit_yaml(
        "structured/paper.draft.yaml",
        draft,
        "math_exam_staging_draft/v1",
    )
    deps = type(
        "Deps",
        (),
        {
            "deterministic": type(
                "Ports",
                (),
                {"evidence_completer": DeterministicEvidenceCompleter(store)},
            )()
        },
    )()

    result = make_complete_evidence_node(deps)(
        {
            "draft": draft_ref.model_dump(mode="json"),
            "source_kind": "doc",
        }
    )

    assert result["terminal_errors"][0].startswith(
        "complete_evidence: evidence_failed:"
    )
    assert "word_evidence.official_solution must not be empty" in result[
        "terminal_errors"
    ][0]
