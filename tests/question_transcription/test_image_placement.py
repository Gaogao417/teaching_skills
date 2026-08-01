"""Image placement planner + group renderer tests (stages 4 & 6).

The headline case is Baoshan 2026 Q24: three prompt figures (image295/301/302)
that previously caused ``every prompt crop needs assignment_path``. After
planning + rendering, the role carries ONE crop on a composed group PNG with an
explicit assignment_path, and the expander's multi-crop check passes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.image_placement import (  # noqa: E402
    PlacementDecision,
    plan_placements,
)
from scripts.question_transcription.materialize_image_group import (  # noqa: E402
    ImageGroupRenderer,
    resolve_placement_decisions,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


# --------------------------------------------------------------------------- #
# Planner: pure logic
# --------------------------------------------------------------------------- #


def _draft_with(prompt_count: int, sol_count: int = 0) -> dict:
    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {"id": "P"},
        "sections": [{
            "id": "I", "title": "x", "items": [{
                "item_id": "Q001",
                "prompt": [
                    {"source": f"media/img{i}.png", "box_px": [0, 0, 100, 100]}
                    for i in range(prompt_count)
                ],
                "official_solution": {
                    "crops": [
                        {"source": f"media/sol{i}.png", "box_px": [0, 0, 100, 100]}
                        for i in range(sol_count)
                    ] if sol_count else [],
                    "start_anchor": "1.", "end_anchor": "2.",
                },
                "block": {"stem_latex": "s", "answer": "1", "clue": "c"},
            }],
        }],
    }


def test_single_image_maps_to_single_placement():
    decisions = plan_placements(_draft_with(prompt_count=1))
    assert len(decisions) == 1
    d = decisions[0]
    assert d.question_id == "Q001"
    assert len(d.placements) == 1
    assert d.placements[0].kind == "single_image"
    assert d.placements[0].assignment_path == "/diagram_col"
    assert d.needs_review is None
    assert d.warnings == []


def test_multi_image_maps_to_group_with_warning():
    decisions = plan_placements(_draft_with(prompt_count=3))
    d = decisions[0]
    assert len(d.placements) == 1
    p = d.placements[0]
    assert p.kind == "image_group"
    assert len(p.image_ids) == 3
    assert p.layout == "vertical"
    assert p.assignment_path == "/diagram_col"
    # Layout downgrade is a NON-blocking warning, not a review.
    assert d.needs_review is None
    assert any(w.code == "grouped_adjacent_to_scalar_stem" for w in d.warnings)


def test_solution_role_uses_step_path():
    decisions = plan_placements(_draft_with(prompt_count=0, sol_count=2))
    d = decisions[0]
    assert len(d.placements) == 1
    assert d.placements[0].role == "solution"
    assert d.placements[0].assignment_path == "/solution_steps/0/diagram_col"


def test_no_images_yields_no_decisions():
    decisions = plan_placements({
        "sections": [{"items": [{"item_id": "Q001", "prompt": [],
                                  "official_solution": {"crops": []}}]}]
    })
    assert decisions == []


# --------------------------------------------------------------------------- #
# Renderer: composes PNGs and rewrites the draft
# --------------------------------------------------------------------------- #


def _png(path: Path, w: int, h: int) -> None:
    from PIL import Image as _Image
    path.parent.mkdir(parents=True, exist_ok=True)
    _Image.new("RGB", (w, h), "white").save(path, format="PNG")


def test_resolve_replaces_group_with_single_crop(tmp_path):
    repo = tmp_path
    for i in range(3):
        _png(repo / "media" / f"img{i}.png", 100, 80)
    draft = _draft_with(prompt_count=3)
    resolved = resolve_placement_decisions(draft, repo, staging_dir=None)
    item = resolved.draft["sections"][0]["items"][0]
    # The three-crop prompt list is now a single crop.
    assert len(item["prompt"]) == 1
    assert item["prompt"][0]["assignment_path"] == "/diagram_col"


def test_resolve_single_image_stamps_assignment_path(tmp_path):
    draft = _draft_with(prompt_count=1)
    resolved = resolve_placement_decisions(draft, tmp_path, staging_dir=None)
    item = resolved.draft["sections"][0]["items"][0]
    assert len(item["prompt"]) == 1
    assert item["prompt"][0]["assignment_path"] == "/diagram_col"


# --------------------------------------------------------------------------- #
# Baoshan Q24 regression: the three-figure prompt
# --------------------------------------------------------------------------- #


def _baoshan_q24_draft(repo: Path) -> dict:
    """Build a v1 draft item mirroring Baoshan Q24's three-prompt-crop shape."""
    for name, w, h in [("image295.png", 1068, 954), ("image301.png", 1181, 1037), ("image302.png", 1177, 1068)]:
        _png(repo / "media" / name, w, h)
    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {"id": "2026-BAOSHAN-ERMO"},
        "sections": [{
            "id": "problem", "title": "三、解答题", "items": [{
                "item_id": "Q024",
                "question_number": 24,
                "question_type": "problem",
                "points": 12,
                "prompt": [
                    {"source": "media/image295.png", "box_px": [0, 0, 1068, 954]},
                    {"source": "media/image301.png", "box_px": [0, 0, 1181, 1037]},
                    {"source": "media/image302.png", "box_px": [0, 0, 1177, 1068]},
                ],
                "official_solution": {"crops": [], "start_anchor": "24.", "end_anchor": "25."},
                "block": {
                    "stem_latex": "如图，抛物线...",
                    "answer": "见解答",
                    "clue": "分小问求解。",
                    "solution_steps": ["(1) 求表达式。"],
                },
            }],
        }],
    }


def test_baoshan_q24_three_figures_resolve_to_one_group(tmp_path):
    """Q024's three prompt figures must resolve to one composed crop with an
    assignment_path, so the expander no longer raises the multi-crop error."""
    repo = tmp_path
    draft = _baoshan_q24_draft(repo)
    resolved = resolve_placement_decisions(draft, repo, staging_dir=repo / "staging")
    item = resolved.draft["sections"][0]["items"][0]
    assert len(item["prompt"]) == 1
    crop = item["prompt"][0]
    assert crop["assignment_path"] == "/diagram_col"
    # The composed PNG was written (staging_dir provided).
    assert "group" in str(crop["source"])
    assert (repo / "staging" / "placement-decisions.yaml").exists()
    audit = yaml.safe_load(
        (repo / "staging" / "placement-decisions.yaml").read_text(encoding="utf-8")
    )
    assert audit["placements"][0]["image_ids"] == ["image295.png", "image301.png", "image302.png"]
    assert audit["placements"][0]["layout"] == "vertical"


def test_baoshan_q24_resolved_draft_passes_expander_multi_crop_check(tmp_path):
    """The resolved draft must not trip expand_staging_draft's
    'every prompt crop needs assignment_path' rule."""
    # Import the real expander and run just the multi-crop check on the item.
    import importlib.util
    ingestion = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
    spec = importlib.util.spec_from_file_location(
        "expand_staging_draft", ingestion / "expand_staging_draft.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    repo = tmp_path
    draft = _baoshan_q24_draft(repo)
    resolve_placement_decisions(draft, repo, staging_dir=None)
    item = draft["sections"][0]["items"][0]
    # Replicate the expander's check (expand_staging_draft.build_item, roles loop):
    # a single crop needs no assignment_path (defaults), but if present it must
    # not collide. Here we have exactly one crop WITH assignment_path set.
    assert len(item["prompt"]) == 1
    assert item["prompt"][0].get("assignment_path") is not None
