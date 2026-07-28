"""Tests for the DraftAssembler (Track 1, §12 acceptance set).

These use the golden fixtures (Yangpu Q18 DOCX + PDF region) and synthetic
bundles for the error classes. The assembler is exercised in-memory; the CLI
is smoke-tested separately.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.assemble_paper_draft import assemble  # noqa: E402
from scripts.question_transcription.contracts import (  # noqa: E402
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _bundle_t(name: str) -> QuestionTranscriptionBundle:
    return QuestionTranscriptionBundle.model_validate(_load(FIX / name))


def _bundle_i(name: str) -> ImageAttributionBundle:
    return ImageAttributionBundle.model_validate(_load(FIX / name))


# --------------------------------------------------------------------------- #
# §12 test 1: determinism
# --------------------------------------------------------------------------- #


def test_determinism_two_runs_identical():
    t, i = _bundle_t("yangpu-q18.transcription.yaml"), _bundle_i("yangpu-q18.attribution.yaml")
    d1, _ = assemble(t, i)
    d2, _ = assemble(t, i)
    assert d1 == d2
    import yaml as _yaml

    # Byte-stable serialization too.
    text1 = _yaml.safe_dump(d1, allow_unicode=True, sort_keys=False, width=1000)
    text2 = _yaml.safe_dump(d2, allow_unicode=True, sort_keys=False, width=1000)
    assert text1 == text2


# --------------------------------------------------------------------------- #
# §12 test 2: single consumption; ignored asset not consumed
# --------------------------------------------------------------------------- #


def test_accepted_consumed_once_ignored_not_consumed():
    t, i = _bundle_t("yangpu-q18.transcription.yaml"), _bundle_i("yangpu-q18.attribution.yaml")
    draft, report = assemble(t, i)
    assert draft is not None
    assert report.errors == []
    assert report.accepted_attributions == 2
    assert report.consumed_attributions == 2
    assert report.ignored_assets == 1
    item = draft["sections"][0]["items"][0]
    # image9 -> prompt, image10 -> official_solution.crops
    assert item["prompt"][0]["box_px"] == [0, 0, 475, 512]  # full crop of image9
    assert item["official_solution"]["crops"][0]["box_px"] == [0, 0, 510, 512]
    assert item["official_solution"]["crops"][0]["source"].endswith("image10.png")


# --------------------------------------------------------------------------- #
# §12 test 5 & 8: solution_steps preserved verbatim (Yangpu Q18)
# --------------------------------------------------------------------------- #


def test_yangpu_q18_solution_steps_preserved():
    t, i = _bundle_t("yangpu-q18.transcription.yaml"), _bundle_i("yangpu-q18.attribution.yaml")
    draft, _ = assemble(t, i)
    item = draft["sections"][0]["items"][0]
    steps = item["block"]["solution_steps"]
    assert len(steps) == 6
    assert steps == t.sections[0].questions[0].content.solution_steps
    assert steps[0].startswith("取$AC$的中点$F$")
    assert steps[-1] == "所以$4\\leqslant BE\\leqslant 6$。"


def test_item_id_assigned_in_paper_order():
    t, i = _bundle_t("yangpu-q18.transcription.yaml"), _bundle_i("yangpu-q18.attribution.yaml")
    draft, _ = assemble(t, i)
    assert draft["sections"][0]["items"][0]["item_id"] == "Q001"
    assert draft["sections"][0]["items"][0]["question_number"] == 18


# --------------------------------------------------------------------------- #
# §12 test 6: DOCX full crop -> full pixel box
# (covered above); explicit assertion on the source path under archive.
# --------------------------------------------------------------------------- #


def test_docx_full_crop_uses_media_original_under_archive():
    t, i = _bundle_t("yangpu-q18.transcription.yaml"), _bundle_i("yangpu-q18.attribution.yaml")
    draft, _ = assemble(t, i)
    item = draft["sections"][0]["items"][0]
    archive = t.paper.source_archive
    assert item["prompt"][0]["source"].startswith(archive)
    assert "/word/media/image9.png" in item["prompt"][0]["source"]


# --------------------------------------------------------------------------- #
# §12 test 7: PDF region crop bbox preserved; §12 test 4: needs_review warns
# --------------------------------------------------------------------------- #


def test_pdf_region_crop_and_needs_review_warning():
    t, i = _bundle_t("pdf-region-q24.transcription.yaml"), _bundle_i("pdf-region-q24.attribution.yaml")
    draft, report = assemble(t, i)
    assert draft is not None
    assert report.errors == []
    # The needs_review attribution is omitted from draft, only warned.
    codes = {w.code for w in report.warnings}
    assert "image_needs_review" in codes
    item = draft["sections"][0]["items"][0]
    # question_evidence region bbox preserved verbatim
    assert item["question_evidence"][0]["box_px"] == [80, 210, 1010, 860]
    # prompt region bbox preserved verbatim (accepted medium-confidence)
    assert item["prompt"][0]["box_px"] == [650, 315, 1000, 690]
    # needs_review solution attribution did NOT enter crops
    sources = [c["source"] for c in item["official_solution"]["crops"]]
    assert not any("page-008" in s for s in sources)
    # but the region-evidence solution crop (page 008, accepted as evidence) IS there
    assert any("pages/008.png" in s for s in sources)
    assert item["official_solution"]["start_anchor"] == "24．"
    assert item["official_solution"]["end_anchor"] == "25．"


def test_pdf_unresolved_asset_reported():
    t, i = _bundle_t("pdf-region-q24.transcription.yaml"), _bundle_i("pdf-region-q24.attribution.yaml")
    _, report = assemble(t, i)
    assert report.unresolved_assets == 1  # page-008 asset disposition=needs_review


# --------------------------------------------------------------------------- #
# §12 test 3: hard-error classes
# --------------------------------------------------------------------------- #


def test_unknown_question_ref_fails():
    t = _bundle_t("yangpu-q18.transcription.yaml")
    i = _bundle_i("yangpu-q18.attribution.yaml")
    payload = i.model_dump(by_alias=True, exclude_none=True)
    payload["attributions"][0]["question_ref"] = "99"  # not in transcription
    bundle = ImageAttributionBundle.model_validate(payload)
    draft, report = assemble(t, bundle)
    assert draft is None
    codes = {e.code for e in report.errors}
    assert "unknown_question_ref" in codes


def test_duplicate_order_fails():
    t = _bundle_t("yangpu-q18.transcription.yaml")
    payload = _load(FIX / "yangpu-q18.attribution.yaml")
    # add a second accepted prompt attribution for q18 with the same order=0
    payload["assets"].append(
        {
            "asset_id": "word-image-99",
            "source": "documents/初三/2025届-上海市杨浦区-初三二模数学-试卷及解析/word/media/image99.png",
            "sha256": "sha256:9999999999999999999999999999999999999999999999999999999999999999",
            "media_type": "image/png",
            "width_px": 100,
            "height_px": 100,
            "disposition": "attributed",
        }
    )
    payload["attributions"].append(
        {
            "attribution_id": "attr-dup",
            "asset_id": "word-image-99",
            "question_ref": "18",
            "role": "prompt",
            "crop": {"kind": "full"},
            "order": 0,  # collides with the existing prompt order=0
            "confidence": "high",
            "state": "accepted",
            "provider": {"kind": "agent", "name": "x", "version": "v1"},
        }
    )
    bundle = ImageAttributionBundle.model_validate(payload)
    draft, report = assemble(t, bundle)
    assert draft is None
    assert any(e.code == "duplicate_order" for e in report.errors)


def test_out_of_bounds_region_crop_fails():
    t = _bundle_t("pdf-region-q24.transcription.yaml")
    payload = _load(FIX / "pdf-region-q24.attribution.yaml")
    # region box exceeds the page-004 asset dims (1240x1754)
    payload["attributions"][0]["crop"]["box_px"] = [0, 0, 9999, 9999]
    bundle = ImageAttributionBundle.model_validate(payload)
    draft, report = assemble(t, bundle)
    assert draft is None
    assert any(e.code == "crop_out_of_bounds" for e in report.errors)


def test_paper_id_mismatch_fails():
    t = _bundle_t("yangpu-q18.transcription.yaml")
    i = _bundle_i("yangpu-q18.attribution.yaml")
    payload = i.model_dump(by_alias=True, exclude_none=True)
    payload["paper_id"] = "OTHER-PAPER"
    bundle = ImageAttributionBundle.model_validate(payload)
    draft, report = assemble(t, bundle)
    assert draft is None
    assert any(e.code == "paper_id_mismatch" for e in report.errors)


def test_path_escape_fails():
    t = _bundle_t("yangpu-q18.transcription.yaml")
    payload = _load(FIX / "yangpu-q18.attribution.yaml")
    payload["assets"][0]["source"] = "../escape/media/image9.png"
    bundle = ImageAttributionBundle.model_validate(payload)
    draft, report = assemble(t, bundle)
    assert draft is None
    assert any(e.code == "path_escape" for e in report.errors)


# --------------------------------------------------------------------------- #
# Draft is expandable by the existing expander (real downstream contract)
# --------------------------------------------------------------------------- #


def test_yangpu_draft_is_expandable_by_existing_expander(tmp_path):
    """The DOCX full-crop draft must pass the real expand_staging_draft.py."""
    import importlib.util

    t, i = _bundle_t("yangpu-q18.transcription.yaml"), _bundle_i("yangpu-q18.attribution.yaml")
    draft, report = assemble(t, i)
    assert draft is not None and report.errors == []
    # The expander needs a sibling question-bank.yaml and the source paths to
    # not exist on disk (it never opens them during expand). Write minimal stubs.
    staging = tmp_path / "staging" / "2025-YANGPU-ERMO"
    staging.mkdir(parents=True)
    (tmp_path / "question-bank.yaml").write_text("schema: math_topic_question_bank/v1\n", encoding="utf-8")
    draft["question_bank"] = "../../question-bank.yaml"  # relative to staging/2025-.../
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(draft, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    expand_path = (
        ROOT
        / ".codex/skills/math-pdf-question-bank-ingestion/scripts/expand_staging_draft.py"
    )
    spec = importlib.util.spec_from_file_location("expand_staging_draft", expand_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    module.expand_draft(staging / "paper.draft.yaml")
    assert (staging / "paper.yaml").exists()
    assert (staging / "items/Q001/source.yaml").exists()
    # The source.yaml records the prompt + solution crops and the word evidence.
    src = yaml.safe_load((staging / "items/Q001/source.yaml").read_text("utf-8"))
    assert src["crops"]["prompt"][0]["box_px"] == [0, 0, 475, 512]
    assert src["crops"]["official_solution"][0]["box_px"] == [0, 0, 510, 512]
    assert src["word_evidence"]["question"][0]["page_number"] == 13
    assert src["word_evidence"]["official_solution"][0]["page_number"] == 14
