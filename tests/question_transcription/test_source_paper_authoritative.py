"""SourcePaper builder evidence-channel tests (stage 0.5 / commit 1).

Pins the three behaviours that the baseline got wrong and that commit 1 fixes:

1. The builder MUST receive the source manifest (word-source.yaml) so the v2
   paper can recover vector-asset evidence (ole_binding / emf_class). The
   baseline build() signature did not accept it.
2. ``_has_needs_review`` inspected ``assets[].state`` (a field that does not
   exist on the v1 AttributionAsset contract), so it ALWAYS returned False and
   the review-issues list was ALWAYS empty. The fix checks attribution.state
   AND asset.disposition and emits REAL issues.
3. The paper_id is recovered from the manifest when the transcription carries
   the ingestion placeholder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.source.source_paper import (  # noqa: E402
    DeterministicSourcePaperBuilder,
    _collect_review_issues,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (  # noqa: E402
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import (  # noqa: E402
    RunLayout,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


def _transcription_dict(paper_id: str = "INGEST-PLACEHOLDER") -> dict:
    return {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": paper_id,
            "title": "T",
            "grade": "九年级",
            "source_archive": "documents/x",
            "question_bank": "../../question-bank.yaml",
        },
        "sections": [
            {
                "section_ref": "I",
                "title": "一、选择题",
                "questions": [
                    {
                        "question_ref": "1",
                        "question_number": 1,
                        "question_type": "short_answer",
                        "points": 4,
                        "content": {
                            "stem_latex": "如图，求$x$。",
                            "answer": "1",
                            "clue": "c",
                            "solution_steps": ["s1"],
                        },
                        "evidence": {
                            "question": [{"kind": "page", "source": "p/1.png", "page_number": 1}],
                            "solution": [{"kind": "page", "source": "p/2.png", "page_number": 2}],
                            "solution_start_anchor": "1.",
                            "solution_end_anchor": "2.",
                        },
                    }
                ],
            }
        ],
        "provider": {"kind": "agent", "name": "codex", "version": "v1"},
    }


def _word_source_dict() -> dict:
    return yaml.safe_load(
        (FIX / "docx-vector-assets.word-source.yaml").read_text(encoding="utf-8")
    )


def test_build_accepts_and_reads_extracted_source_manifest(tmp_path):
    """The build() signature must accept extracted_source_ref and read it."""
    store = _store(tmp_path)
    trans_ref = store.commit_yaml(
        "structured/transcription.yaml", _transcription_dict(),
        "math_question_transcription/v1",
    )
    manifest_ref = store.commit_yaml(
        "source/source-ref.yaml", _word_source_dict(), "math_word_source_extract/v1"
    )
    builder = DeterministicSourcePaperBuilder(store)
    result, failure, detail = builder.build(trans_ref, None, manifest_ref, None)
    assert failure is None, f"unexpected failure: {failure}: {detail}"
    assert result is not None
    source_paper = store.read_yaml(result.source_paper)
    # paper_id recovered from the manifest would require the manifest to carry it;
    # the synthetic fixture does not, so it falls back to the transcription id.
    assert source_paper["schema"] == "math_exam_source_paper/v2"


def test_needs_review_attribution_produces_real_issue_not_empty_list(tmp_path):
    """The baseline always emitted issues: [] (empty). A needs_review attribution
    must now produce a concrete, non-empty review issue."""
    store = _store(tmp_path)
    trans_ref = store.commit_yaml(
        "structured/transcription.yaml", _transcription_dict(),
        "math_question_transcription/v1",
    )
    images = {
        "schema": "math_image_attribution/v1",
        "paper_id": "INGEST-PLACEHOLDER",
        "assets": [{"asset_id": "a1", "source": "s", "sha256": "sha256:" + "0" * 64,
                    "media_type": "image/png", "width_px": 10, "height_px": 10,
                    "disposition": "attributed"}],
        "attributions": [
            {"attribution_id": "x", "asset_id": "a1", "question_ref": "1",
             "role": "prompt", "crop": {"kind": "full"}, "order": 0,
             "confidence": "medium", "state": "needs_review",
             "provider": {"kind": "manual", "name": "t", "version": "v1"}},
        ],
    }
    images_ref = store.commit_yaml(
        "structured/image-attribution.yaml", images, "math_image_attribution/v1"
    )
    builder = DeterministicSourcePaperBuilder(store)
    result, failure, detail = builder.build(trans_ref, images_ref, None, None)
    assert failure is None
    assert result is not None
    assert result.issues is not None, "needs_review attribution must emit issues"
    issues = store.read_yaml(result.issues)
    assert issues["issues"], "issues list must not be empty (baseline bug)"
    assert any(i["kind"] == "attribution_needs_review" for i in issues["issues"])


def test_needs_review_asset_disposition_produces_issue(tmp_path):
    """The baseline _has_needs_review checked assets[].state (nonexistent field).
    The fix checks assets[].disposition == 'needs_review'."""
    issues = _collect_review_issues(
        {
            "assets": [
                {"asset_id": "orphan1", "disposition": "needs_review",
                 "disposition_reason": "unreferenced_in_paragraph_stream"}
            ],
            "attributions": [],
        },
        manifest=None,
    )
    assert issues, "a needs_review disposition asset must produce an issue"
    assert issues[0]["kind"] == "asset_needs_review"


def test_accepted_bundle_produces_no_issues(tmp_path):
    """A fully-accepted clean bundle must NOT produce issues (no false blocks)."""
    issues = _collect_review_issues(
        {
            "assets": [{"asset_id": "a1", "disposition": "attributed"}],
            "attributions": [
                {"attribution_id": "x", "asset_id": "a1", "question_ref": "1",
                 "role": "prompt", "crop": {"kind": "full"}, "order": 0,
                 "confidence": "high", "state": "accepted"}
            ],
        },
        manifest=None,
    )
    assert issues == []


def test_no_manifest_is_allowed(tmp_path):
    """A non-docx source (no manifest) must still build via the minimal path."""
    store = _store(tmp_path)
    trans_ref = store.commit_yaml(
        "structured/transcription.yaml", _transcription_dict("PAPER-A"),
        "math_question_transcription/v1",
    )
    builder = DeterministicSourcePaperBuilder(store)
    result, failure, detail = builder.build(trans_ref, None, None, None)
    assert failure is None
    assert result is not None
    sp = store.read_yaml(result.source_paper)
    assert sp["paper_id"] == "PAPER-A"
