"""Tests for the PDF image adapter (Track 3).

Wraps a vision-detection payload into the standard ImageAttributionBundle and
verifies the join with the golden Q24 transcription through the real assembler.
Also checks the region crop is preserved verbatim (§12 test 7) and that a page
with no detection is reported, not silently dropped.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.source.adapt_pdf_images import adapt  # noqa: E402
from scripts.question_transcription.assemble_paper_draft import assemble  # noqa: E402
from scripts.question_transcription.contracts import (  # noqa: E402
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


def _load(name: str) -> dict:
    return yaml.safe_load((FIX / name).read_text(encoding="utf-8"))


def _detection() -> dict:
    return _load("pdf-region-q24.detection.yaml")


# --------------------------------------------------------------------------- #
# Adapter unit
# --------------------------------------------------------------------------- #


def test_adapt_pdf_detection_shape():
    bundle = ImageAttributionBundle.model_validate(adapt(_detection()))
    assert bundle.paper_id == "2024-FENGXIAN-ERMO"
    assert len(bundle.assets) == 2  # two pages
    # source path under archive
    assert bundle.assets[0].source == (
        "documents/初三/2024届-上海市奉贤区-初三二模数学-试卷及参考答案/pages/004.png"
    )
    assert {a.asset_id for a in bundle.assets} == {"page-004", "page-008"}
    # two detections, region crops
    assert len(bundle.attributions) == 2
    for attr in bundle.attributions:
        assert attr.crop.kind == "region"


def test_adapt_confidence_state_mapping():
    bundle = ImageAttributionBundle.model_validate(adapt(_detection()))
    by_role = {a.role: a for a in bundle.attributions}
    assert by_role["prompt"].state == "accepted"   # medium
    assert by_role["solution"].state == "needs_review"  # low


def test_adapt_unknown_page_rejected():
    det = _detection()
    det["detections"].append(
        {
            "page_path": "pages/999.png",
            "question_number": 24,
            "role": "prompt",
            "box_px": [0, 0, 10, 10],
            "confidence": "high",
        }
    )
    with pytest.raises(Exception):
        adapt(det)


def test_adapt_bad_role_rejected():
    det = _detection()
    det["detections"][0]["role"] = "diagram"
    with pytest.raises(Exception):
        adapt(det)


# --------------------------------------------------------------------------- #
# End-to-end: PDF adapter -> assembler (parabola Q24, §12-7)
# --------------------------------------------------------------------------- #


def test_pdf_region_q24_end_to_end_through_assembler():
    transcription = QuestionTranscriptionBundle.model_validate(
        _load("pdf-region-q24.transcription.yaml")
    )
    image_bundle = ImageAttributionBundle.model_validate(adapt(_detection()))
    draft, report = assemble(transcription, image_bundle)
    assert draft is not None
    assert report.errors == []
    # The low-confidence solution detection -> needs_review warning, but the
    # crop now enters the draft (pending human confirmation), no longer omitted.
    codes = {w.code for w in report.warnings}
    assert "image_needs_review" in codes
    item = draft["sections"][0]["items"][0]
    # prompt region bbox preserved verbatim
    assert item["prompt"][0]["box_px"] == [650, 315, 1000, 690]
    assert item["prompt"][0]["source"].endswith("pages/004.png")
    # question_evidence region preserved (from transcription, not attribution)
    assert item["question_evidence"][0]["box_px"] == [80, 210, 1010, 860]
    # the needs_review solution IMAGE bbox [120,120,1100,1200] enters crops,
    # tagged with an attribution_review block for downstream UI surfacing.
    sol_crops = item["official_solution"]["crops"]
    nr = [c for c in sol_crops if "attribution_review" in c]
    assert len(nr) == 1
    assert tuple(nr[0]["box_px"]) == (120, 120, 1100, 1200)
    assert nr[0]["attribution_review"]["state"] == "needs_review"
    # and the region-evidence solution crop (page 008, [80,120,1010,700]) is present
    sol_boxes = [tuple(c["box_px"]) for c in sol_crops]
    assert (80, 120, 1010, 700) in sol_boxes


# --------------------------------------------------------------------------- #
# DOCX-vs-PDF structural equivalence (§11 convergence)
# --------------------------------------------------------------------------- #


def test_docx_and_pdf_both_produce_expandable_drafts():
    """Both tracks emit the same draft schema; the assembler is the convergence
    point. Here we just assert the PDF draft carries the v1 schema and the
    expected region-evidence shape (the DOCX equivalence is covered by Track 2).
    """
    transcription = QuestionTranscriptionBundle.model_validate(
        _load("pdf-region-q24.transcription.yaml")
    )
    image_bundle = ImageAttributionBundle.model_validate(adapt(_detection()))
    draft, _ = assemble(transcription, image_bundle)
    assert draft["schema"] == "math_exam_staging_draft/v1"
    item = draft["sections"][0]["items"][0]
    # PDF track uses region evidence -> question_evidence + official_solution.crops
    assert "question_evidence" in item
    assert "question_word_evidence" not in item
    assert "crops" in item["official_solution"]
    assert "word_evidence" not in item["official_solution"]
