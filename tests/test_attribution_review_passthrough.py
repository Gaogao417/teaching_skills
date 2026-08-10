"""Staging passthrough tests for ``attribution_review`` on crops.

Pins the chain: a draft crop carrying ``attribution_review`` (produced by the
assembler for a ``needs_review`` attribution) must survive expand → source.yaml
→ CropEvidence validation → materialize, and a change in the review metadata
must change ``content_hash`` so human review is re-triggered.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOPIC_SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
INGESTION_SCRIPTS = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
for _p in (str(TOPIC_SCRIPTS), str(INGESTION_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from exam_source_contracts import AttributionReview, CropEvidence, ExamItemSource  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


expand = _load_module("expand_staging_draft", INGESTION_SCRIPTS / "expand_staging_draft.py")
materialize = _load_module("materialize_staging", INGESTION_SCRIPTS / "materialize_staging.py")


def _png(path: Path, width: int, height: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image as _Image
    _Image.new("RGB", (width, height), "white").save(path, format="PNG")


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    # The expander/materializer resolve skill scripts under .codex; symlink it.
    link = tmp_path / ".codex"
    try:
        link.symlink_to(ROOT / ".codex", target_is_directory=True)
    except (FileExistsError, OSError):
        pytest.skip("cannot symlink .codex on this platform")
    return tmp_path


def _draft(repo: Path, *, prompt_review: dict | None = None) -> dict:
    _png(repo / "documents/p/media/img.png", 120, 120)
    for page in range(1, 3):
        _png(repo / "documents/p/word/pages" / f"{page:03d}.png", 800, 1100)
    prompt_crops = [
        {"source": "documents/p/media/img.png", "box_px": [0, 0, 120, 120]}
    ]
    if prompt_review is not None:
        prompt_crops[0]["attribution_review"] = prompt_review
    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {
            "id": "P-REVIEW",
            "title": "T",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": "documents/p",
        },
        "question_bank": "../../question-bank.yaml",
        "sections": [{
            "id": "problem",
            "title": "三、解答题",
            "items": [{
                "item_id": "Q001",
                "question_number": 1,
                "question_type": "problem",
                "points": 8,
                "prompt": prompt_crops,
                "question_word_evidence": [
                    {"page_image": "documents/p/word/pages/001.png", "page_number": 1},
                ],
                "official_solution": {
                    "start_anchor": "1.",
                    "end_anchor": "2.",
                    "word_evidence": [
                        {"page_image": "documents/p/word/pages/002.png", "page_number": 2},
                    ],
                    "crops": [],
                },
                "block": {
                    "stem_latex": "如图。",
                    "answer": "1",
                    "clue": "c",
                    "solution_steps": ["s1"],
                },
            }],
        }],
    }


def test_crop_evidence_accepts_optional_attribution_review():
    """CropEvidence validates with attribution_review and defaults to None."""
    base = {
        "source": "x.png",
        "source_sha256": "sha256:" + "a" * 64,
        "box_px": [0, 0, 10, 10],
        "output": "assets/prompt-00.png",
        "output_sha256": "sha256:" + "b" * 64,
    }
    # No review -> valid (accepted crop).
    assert CropEvidence(**base).attribution_review is None
    # With review -> valid.
    ce = CropEvidence(
        **base,
        attribution_review={
            "attribution_id": "attr-1",
            "state": "needs_review",
            "confidence": "medium",
        },
    )
    assert isinstance(ce.attribution_review, AttributionReview)
    assert ce.attribution_review.state == "needs_review"
    assert ce.attribution_review.confidence == "medium"


def test_crop_evidence_rejects_unknown_extra_keys():
    """extra='forbid' means an unknown top-level key is rejected — the field
    must be declared explicitly (this is why we added attribution_review)."""
    base = {
        "source": "x.png",
        "source_sha256": "sha256:" + "a" * 64,
        "box_px": [0, 0, 10, 10],
        "output": "assets/prompt-00.png",
        "output_sha256": "sha256:" + "b" * 64,
    }
    with pytest.raises(Exception):
        CropEvidence(**base, review_flags={"state": "needs_review"})


def test_attribution_review_passes_through_expand_to_source_yaml(fake_repo: Path):
    repo = fake_repo
    (repo / "question-bank.yaml").write_text(
        "schema: math_topic_question_bank/v1\n", encoding="utf-8"
    )
    staging = repo / "staging" / "P-REVIEW"
    staging.mkdir(parents=True, exist_ok=True)
    review = {
        "attribution_id": "attr-1",
        "state": "needs_review",
        "confidence": "medium",
    }
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(_draft(repo, prompt_review=review),
                       allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    expand.expand_draft(staging / "paper.draft.yaml")
    source = yaml.safe_load(
        (staging / "items" / "Q001" / "source.yaml").read_text("utf-8")
    )
    # The review survived into source.yaml.
    prompt_crop = source["crops"]["prompt"][0]
    assert prompt_crop["attribution_review"] == review
    # And the staging contract validates with it.
    item = ExamItemSource.model_validate(source)
    assert item.crops.prompt[0].attribution_review is not None
    assert item.crops.prompt[0].attribution_review.state == "needs_review"


def test_attribution_review_change_changes_content_hash(fake_repo: Path):
    """A change in attribution_review metadata must change content_hash."""
    repo = fake_repo
    (repo / "question-bank.yaml").write_text(
        "schema: math_topic_question_bank/v1\n", encoding="utf-8"
    )
    staging = repo / "staging" / "P-REVIEW"
    staging.mkdir(parents=True, exist_ok=True)
    review_medium = {
        "attribution_id": "attr-1", "state": "needs_review", "confidence": "medium"}
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(_draft(repo, prompt_review=review_medium),
                       allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    expand.expand_draft(staging / "paper.draft.yaml")
    materialize.materialize_item(staging / "items" / "Q001", repo)
    h1 = yaml.safe_load(
        (staging / "items" / "Q001" / "source.yaml").read_text("utf-8")
    )["content_hash"]

    # Re-expand with a different confidence and re-materialize.
    review_low = {
        "attribution_id": "attr-1", "state": "needs_review", "confidence": "low"}
    # Remove the review.yaml guard if a prior review was written, then re-expand.
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(_draft(repo, prompt_review=review_low),
                       allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    # expand refuses if review.yaml exists; clear the item dir to re-run cleanly.
    import shutil
    shutil.rmtree(staging / "items")
    expand.expand_draft(staging / "paper.draft.yaml")
    materialize.materialize_item(staging / "items" / "Q001", repo)
    h2 = yaml.safe_load(
        (staging / "items" / "Q001" / "source.yaml").read_text("utf-8")
    )["content_hash"]
    assert h1 != h2, "changing attribution_review confidence must change content_hash"
