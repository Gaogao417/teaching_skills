"""Tests for the DOCX image adapter (Track 2).

The headline test adapts the REAL Yangpu 2025 word-source.yaml into a bundle,
joins it with the golden Q18 transcription through the real assembler, and
checks that image10.png lands as the Q18 solution image (full crop) and
image9.png as the prompt -- exactly the regression the architecture calls out
in §11 Track 2 and §12 test 8.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.source.adapt_docx_images import adapt  # noqa: E402
from scripts.question_transcription.workflow.adapters.staging.assemble_paper_draft import assemble  # noqa: E402
from scripts.question_transcription.contracts import (  # noqa: E402
    AttributionAsset,
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"
YANGPU_WORD_SOURCE = (
    ROOT
    / "documents/初三/2025届-上海市杨浦区-初三二模数学-试卷及解析/word/word-source.yaml"
)
YANGPU_ARCHIVE = "documents/初三/2025届-上海市杨浦区-初三二模数学-试卷及解析"


def _load_word_source() -> dict:
    return yaml.safe_load(YANGPU_WORD_SOURCE.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Adapter unit: real Yangpu word-source -> bundle
# --------------------------------------------------------------------------- #


def test_adapt_real_yangpu_word_source_shape():
    bundle_dict = adapt(
        _load_word_source(),
        paper_id="2025-YANGPU-ERMO",
        source_archive=YANGPU_ARCHIVE,
    )
    bundle = ImageAttributionBundle.model_validate(bundle_dict)
    # 24 media in the Yangpu paper, all referenced -> all attributed.
    assert len(bundle.assets) == 24
    # image9 and image10 both present
    leaves = {a.asset_id for a in bundle.assets}
    assert "word-image9" in leaves
    assert "word-image10" in leaves
    # All DOCX attributions are crop: full (Word media originals).
    for attr in bundle.attributions:
        assert attr.crop.kind == "full"
    # image10 attribution -> q18, role solution, state accepted (high confidence)
    img10 = [a for a in bundle.attributions if a.asset_id == "word-image10"]
    assert len(img10) == 1
    assert img10[0].question_ref == "18"
    assert img10[0].role == "solution"
    assert img10[0].state == "accepted"
    # image9 -> q18 prompt
    img9 = [a for a in bundle.attributions if a.asset_id == "word-image9"]
    assert img9[0].role == "prompt"
    assert img9[0].question_ref == "18"


def test_adapt_source_path_under_archive():
    bundle_dict = adapt(
        _load_word_source(),
        paper_id="2025-YANGPU-ERMO",
        source_archive=YANGPU_ARCHIVE,
    )
    for asset in bundle_dict["assets"]:
        assert asset["source"].startswith(YANGPU_ARCHIVE + "/word/media/")


def test_adapt_orphan_bucket_marks_asset_ignored():
    ws = _load_word_source()
    # Force image1 into an orphan bucket to exercise the ignored disposition.
    for entry in ws["image_attribution"]:
        if entry["media"] == "media/image1.png":
            entry["bucket"] = "orphan"
    bundle = ImageAttributionBundle.model_validate(
        adapt(ws, paper_id="2025-YANGPU-ERMO", source_archive=YANGPU_ARCHIVE)
    )
    a1 = next(a for a in bundle.assets if a.asset_id == "word-image1")
    assert a1.disposition == "ignored"
    assert a1.disposition_reason == "orphan_in_paragraph_stream"
    # No attribution references image1 anymore.
    assert not any(a.asset_id == "word-image1" for a in bundle.attributions)


def test_adapt_low_confidence_becomes_needs_review():
    ws = _load_word_source()
    for entry in ws["image_attribution"]:
        if entry["media"] == "media/image10.png":
            entry["confidence"] = "low"
    bundle = ImageAttributionBundle.model_validate(
        adapt(ws, paper_id="2025-YANGPU-ERMO", source_archive=YANGPU_ARCHIVE)
    )
    img10 = next(a for a in bundle.attributions if a.asset_id == "word-image10")
    assert img10.state == "needs_review"


def test_adapt_medium_confidence_does_not_auto_accept():
    ws = _load_word_source()
    for entry in ws["image_attribution"]:
        if entry["media"] == "media/image10.png":
            entry["confidence"] = "medium"
    bundle = ImageAttributionBundle.model_validate(
        adapt(ws, paper_id="2025-YANGPU-ERMO", source_archive=YANGPU_ARCHIVE)
    )
    img10 = next(a for a in bundle.attributions if a.asset_id == "word-image10")
    assert img10.state == "needs_review"


def test_adapt_rejects_unknown_media_in_attribution():
    ws = _load_word_source()
    ws["image_attribution"].append(
        {"media": "media/image9999.png", "question_number": 1, "bucket": "prompt", "paragraph_index": 0, "confidence": "high"}
    )
    with pytest.raises(Exception):
        adapt(ws, paper_id="X", source_archive="documents/x")


def test_adapt_blocks_failed_image_attribution_but_not_word_source_itself():
    ws = _load_word_source()
    ws["image_attribution_status"] = "failed"
    ws["image_attribution"] = []
    ws["image_attribution_error"] = {
        "code": "question_number_state_lost",
        "detail": "expected question 5, found question 36",
    }
    with pytest.raises(
        ValueError,
        match=r"text transcription may continue.*image adaptation is blocked",
    ):
        adapt(ws, paper_id="X", source_archive="documents/x")


def test_adapt_accepts_explicit_complete_status():
    ws = _load_word_source()
    ws["image_attribution_status"] = "complete"
    bundle = adapt(
        ws,
        paper_id="2025-YANGPU-ERMO",
        source_archive=YANGPU_ARCHIVE,
    )
    assert bundle["attributions"]


# --------------------------------------------------------------------------- #
# §11 Track 2 acceptance: real adapter -> real assembler (Yangpu Q18)
# --------------------------------------------------------------------------- #


def test_yangpu_q18_end_to_end_real_adapter_through_assembler():
    """The Yangpu Q18 regression at the full DOCX track (§11 Track 2 / §12-8).

    The full Yangpu paper has 24 attributions across Q4-Q25; this regression
    isolates the Q18 attributions (image9 -> prompt, image10 -> solution) and
    joins them with the golden Q18 transcription through the real assembler.
    """
    transcription = QuestionTranscriptionBundle.model_validate(
        yaml.safe_load((FIX / "yangpu-q18.transcription.yaml").read_text("utf-8"))
    )
    full_bundle = ImageAttributionBundle.model_validate(
        adapt(_load_word_source(), paper_id="2025-YANGPU-ERMO", source_archive=YANGPU_ARCHIVE)
    )
    # Isolate Q18 attributions so the join targets exactly the transcribed
    # question (the regression is about the Q18 path, not the whole paper).
    q18_attr = [a for a in full_bundle.attributions if a.question_ref == "18"]
    q18_assets = {a.asset_id for a in q18_attr}
    image_bundle = ImageAttributionBundle.model_validate(
        {
            "schema": "math_image_attribution/v1",
            "paper_id": "2025-YANGPU-ERMO",
            "assets": [
                a.model_dump(by_alias=True, exclude_none=True)
                for a in full_bundle.assets
                if a.asset_id in q18_assets
            ],
            "attributions": [
                a.model_dump(by_alias=True, exclude_none=True) for a in q18_attr
            ],
        }
    )
    draft, report = assemble(transcription, image_bundle)
    assert draft is not None
    assert report.errors == []
    item = draft["sections"][0]["items"][0]
    # image9.png -> prompt, full crop of its real dims.
    prompt = item["prompt"]
    assert len(prompt) == 1
    assert prompt[0]["source"].endswith("/word/media/image9.png")
    assert prompt[0]["box_px"] == [0, 0, 475, 512]
    # image10.png -> official_solution.crops, full crop of its real dims.
    sol = item["official_solution"]["crops"]
    assert len(sol) == 1
    assert sol[0]["source"].endswith("/word/media/image10.png")
    assert sol[0]["box_px"] == [0, 0, 510, 512]
    # Six solution steps preserved (not collapsed to step1).
    assert len(item["block"]["solution_steps"]) == 6
