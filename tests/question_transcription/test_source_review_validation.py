"""Cross-bundle tests for image classification review gating."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    AssetClassificationIssue,
    AssetClassificationResolution,
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
    compute_asset_issue_hash,
)
from scripts.question_transcription.source_contracts import (  # noqa: E402
    ImageAttributionV2,
    ImageRendition,
    ImageNode,
    OleFormulaBinding,
    QuestionContentV2,
    SourceImageAsset,
    SourcePaper,
    SourceQuestion,
    TargetQuestionStem,
    TextNode,
)
from scripts.question_transcription.source_review_validation import (  # noqa: E402
    assert_source_review_ready,
    validate_source_review_gate,
)

_HASH_A = "sha256:" + "a" * 64
_HASH_B = "sha256:" + "b" * 64


def _asset(emf_class: str, issue_id: str | None = None) -> SourceImageAsset:
    return SourceImageAsset(
        asset_id="emf-7",
        original_path="word/media/image7.emf",
        original_sha256=_HASH_A,
        original_media_type="image/x-emf",
        emf_class=emf_class,
        ole_binding=OleFormulaBinding(embedded=False),
        review_issue_id=issue_id,
        rendition=ImageRendition(
            path="rend/image7.png",
            sha256=_HASH_B,
            media_type="image/png",
            width_px=200,
            height_px=100,
        ),
    )


def _paper(asset: SourceImageAsset) -> SourcePaper:
    return SourcePaper(
        schema="math_exam_source_paper/v2",
        paper_id="PAPER",
        questions=[
            SourceQuestion(
                question_ref="1",
                question_number=1,
                question_type="fillin",
                points=3,
                content=QuestionContentV2(
                    stem=[TextNode(kind="text", text="填空")],
                    answer="1",
                    clue="c",
                ),
            )
        ],
        assets=[asset],
    )


def _issue() -> AssetClassificationIssue:
    payload = {
        "asset_id": "emf-7",
        "question_ref": "1",
        "question_number": 1,
        "evidence": [
            {"kind": "page", "source": "pages/page-1.png", "page_number": 1}
        ],
        "detail": "疑似整块题干在 EMF 内，但无法确定图文边界。",
    }
    payload["issue_hash"] = compute_asset_issue_hash(payload)
    return AssetClassificationIssue(issue_id="issue-emf-7", **payload)


def _bundles(selected: str = "mixed_content"):
    issue = _issue()
    issues = ReviewIssuesBundle(
        schema="math_transcription_review_issues/v1",
        paper_id="PAPER",
        generated_at=datetime(2026, 7, 29, 10, 0, 0),
        issues=[issue],
    )
    resolutions = ReviewResolutionsBundle(
        schema="math_transcription_review_resolutions/v1",
        paper_id="PAPER",
        resolutions=[
            AssetClassificationResolution(
                issue_id=issue.issue_id,
                selected_class=selected,
                resolved_issue_hash=issue.issue_hash,
                reviewer="human",
                resolved_at=datetime(2026, 7, 29, 10, 5, 0),
            )
        ],
    )
    return issues, resolutions


def test_deterministic_diagram_needs_no_review_sidecar():
    assert validate_source_review_gate(_paper(_asset("diagram"))) == []


def test_needs_review_blocks_structural_projection():
    paper = _paper(_asset("needs_review", "issue-emf-7"))
    issues, _ = _bundles()
    errors = validate_source_review_gate(paper, issues)
    assert any("classification remains needs_review" in error for error in errors)
    assert any("unresolved blocking" in error for error in errors)


def test_confirmed_mixed_content_passes():
    paper = _paper(_asset("mixed_content", "issue-emf-7"))
    issues, resolutions = _bundles("mixed_content")
    assert validate_source_review_gate(paper, issues, resolutions) == []
    assert_source_review_ready(paper, issues, resolutions)


def test_reviewed_class_must_match_source_asset():
    paper = _paper(_asset("diagram", "issue-emf-7"))
    issues, resolutions = _bundles("mixed_content")
    errors = validate_source_review_gate(paper, issues, resolutions)
    assert any("does not match reviewed class" in error for error in errors)


def test_missing_asset_issue_blocks():
    paper = _paper(_asset("mixed_content", "issue-emf-7"))
    errors = validate_source_review_gate(paper)
    assert any("is missing" in error for error in errors)


def test_content_image_without_exact_attribution_blocks_projection():
    asset = _asset("diagram")
    paper = _paper(asset)
    question = paper.questions[0].model_copy(
        update={
            "content": QuestionContentV2(
                stem=[ImageNode(kind="image", asset_id=asset.asset_id)],
                answer="1",
                clue="c",
            )
        }
    )
    paper = paper.model_copy(update={"questions": [question]})
    errors = validate_source_review_gate(paper)
    assert any("no accepted attribution" in error for error in errors)


def test_needs_review_attribution_satisfies_content_image_binding():
    """A needs_review attribution carries a valid content-image binding (the
    ImageNode is emitted for it), so the gate must NOT block on it — it flows
    downstream for human confirmation instead."""
    asset = _asset("diagram")
    paper = _paper(asset)
    question = paper.questions[0].model_copy(
        update={
            "content": QuestionContentV2(
                stem=[
                    TextNode(kind="text", text="如图。"),
                    ImageNode(kind="image", asset_id=asset.asset_id),
                ],
                answer="1",
                clue="c",
            )
        }
    )
    attribution = ImageAttributionV2(
        attribution_id="attr-1",
        asset_id=asset.asset_id,
        question_ref="1",
        target=TargetQuestionStem(target="question_stem"),
        order=1,
        confidence="medium",
        state="needs_review",
    )
    paper = paper.model_copy(update={"questions": [question], "attributions": [attribution]})
    assert validate_source_review_gate(paper) == []
