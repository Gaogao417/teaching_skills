"""Vector asset guard classification tests (stage 1).

The guard is pure logic. These tests pin the four classification branches against
the synthetic fixture and the real Fengxian media entries (image71 OLE formula,
image72 13x15 tiny fragment), so a regression in the guard surfaces here before
it reaches the v2 builder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.vector_asset_guard import (  # noqa: E402
    GuardInput,
    TINY_VECTOR_MAX_PX,
    VectorAssetGuard,
    guard_input_from_media_entry,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"
FENGXIAN_WORD_SOURCE = (
    ROOT
    / "build/question-ingestion/2025-FENGXIAN-ERMO/run-ecea3a25e6d3/source/docx/word-source.yaml"
)

_GUARD = VectorAssetGuard()


# --------------------------------------------------------------------------- #
# Synthetic fixture: all four branches
# --------------------------------------------------------------------------- #


def _synthetic_media() -> list[dict]:
    ws = yaml.safe_load(
        (FIX / "docx-vector-assets.word-source.yaml").read_text(encoding="utf-8")
    )
    return ws["media"]


def test_ole_equation_wmf_is_ignored_as_formula():
    media = guard_input_from_media_entry(
        next(m for m in _synthetic_media() if m["path"] == "media/image-ole-eq.wmf")
    )
    decision = _GUARD.classify(media)
    assert decision.disposition == "ignored"
    assert decision.reason == "ole_formula"
    assert decision.uses_rendition is False


def test_tiny_wmf_fragment_is_ignored():
    media = guard_input_from_media_entry(
        next(m for m in _synthetic_media() if m["path"] == "media/image-tiny.wmf")
    )
    decision = _GUARD.classify(media)
    assert decision.disposition == "ignored"
    assert decision.reason == "tiny_vector_fragment"


def test_larger_wmf_without_rendition_needs_review():
    media = guard_input_from_media_entry(
        next(
            m
            for m in _synthetic_media()
            if m["path"] == "media/image-big-no-rendition.wmf"
        )
    )
    decision = _GUARD.classify(media)
    assert decision.disposition == "needs_review"
    assert decision.reason == "vector_rendition_missing"
    assert decision.uses_rendition is False


def test_ordinary_png_is_accepted_self_rendition():
    media = guard_input_from_media_entry(
        next(m for m in _synthetic_media() if m["path"] == "media/image-normal.png")
    )
    decision = _GUARD.classify(media)
    assert decision.disposition == "accepted"
    assert decision.reason is None
    # Raster originals are their own rendition; no separate PNG needed.
    assert decision.uses_rendition is False


# --------------------------------------------------------------------------- #
# Size gate boundary
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("w,h,ignored", [
    (TINY_VECTOR_MAX_PX, TINY_VECTOR_MAX_PX, True),     # exactly at gate
    (TINY_VECTOR_MAX_PX + 1, TINY_VECTOR_MAX_PX, False),  # one dim over
    (TINY_VECTOR_MAX_PX, TINY_VECTOR_MAX_PX + 1, False),
    (1, 1, True),
    (17, 17, False),
])
def test_size_gate_requires_both_dims_small(w, h, ignored):
    media = GuardInput(
        media_path="media/edge.wmf",
        media_type="image/wmf",
        width_px=w,
        height_px=h,
        emf_class="diagram",
        ole_binding_embedded=False,
        has_png_rendition=False,
    )
    decision = _GUARD.classify(media)
    if ignored:
        assert decision.reason == "tiny_vector_fragment"
        assert decision.disposition == "ignored"
    else:
        # over the gate, no rendition -> needs_review (not accepted)
        assert decision.disposition == "needs_review"
        assert decision.reason == "vector_rendition_missing"


def test_larger_wmf_with_rendition_is_accepted_via_rendition():
    media = GuardInput(
        media_path="media/big-rendition.wmf",
        media_type="image/wmf",
        width_px=200,
        height_px=150,
        emf_class="diagram",
        ole_binding_embedded=False,
        has_png_rendition=True,
    )
    decision = _GUARD.classify(media)
    assert decision.disposition == "accepted"
    assert decision.uses_rendition is True


# --------------------------------------------------------------------------- #
# Real Fengxian regression: image71 (formula) and image72 (13x15 fragment)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def fengxian_media():
    if not FENGXIAN_WORD_SOURCE.exists():
        pytest.skip("Fengxian batch run not present in this checkout")
    ws = yaml.safe_load(FENGXIAN_WORD_SOURCE.read_text(encoding="utf-8"))
    return {m["path"]: m for m in ws["media"]}


def test_real_fengxian_image71_formula_is_ignored(fengxian_media):
    media = guard_input_from_media_entry(fengxian_media["media/image71.wmf"])
    decision = _GUARD.classify(media)
    assert decision.disposition == "ignored"
    assert decision.reason == "ole_formula"


def test_real_fengxian_image72_tiny_fragment_is_ignored(fengxian_media):
    """image72.wmf (13x15) was accepted as an attributed prompt/solution figure
    in the baseline run, which caused the downstream WMF loader crash. The guard
    must classify it as a tiny fragment so it never reaches the v2 assets."""
    media = guard_input_from_media_entry(fengxian_media["media/image72.wmf"])
    decision = _GUARD.classify(media)
    assert decision.disposition == "ignored"
    assert decision.reason == "tiny_vector_fragment"


def test_guard_input_reports_honest_media_type_for_wmf(fengxian_media):
    """The baseline adapt_docx_images misreported .wmf as image/png. The guard's
    media-type helper must report image/wmf for vector media."""
    media = guard_input_from_media_entry(fengxian_media["media/image72.wmf"])
    assert media.media_type == "image/wmf"
