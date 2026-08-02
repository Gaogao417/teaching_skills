"""End-to-end placement → expand → materialize → audit (stage 6/7 acceptance).

This is the test the commit-3 work was missing: it runs the REAL downstream
pipeline (expand_staging_draft / materialize_staging / audit_staging) on a draft
that has multi-image roles resolved by the placement planner, against a fake
repo root with real on-disk PNGs. It proves the composed group PNG is actually
written, has correct dimensions, and survives cropping + audit — not just that
the "assignment_path" error string stops appearing.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INGESTION = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _png(path: Path, width: int, height: int) -> None:
    from PIL import Image as _Image

    path.parent.mkdir(parents=True, exist_ok=True)
    _Image.new("RGB", (width, height), "white").save(path, format="PNG")


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    link = tmp_path / ".codex"
    try:
        link.symlink_to(ROOT / ".codex", target_is_directory=True)
    except (FileExistsError, OSError):
        pytest.skip("cannot symlink .codex on this platform")
    return tmp_path


def _baoshan_q24_draft(repo: Path) -> dict:
    """A v1 draft mirroring Baoshan Q24: one problem question, three prompt
    figures, with Word page evidence and an official solution anchor."""
    for name, w, h in [
        ("image295.png", 1068, 954),
        ("image301.png", 1181, 1037),
        ("image302.png", 1177, 1068),
    ]:
        _png(repo / "documents/q24/media" / name, w, h)
    # The word-evidence resolver expands q stem pages 1-3 and solution pages 4-7
    # into contiguous ranges, so every page in 1..7 must exist on disk.
    for page in range(1, 8):
        _png(repo / "documents/q24/word/pages" / f"{page:03d}.png", 1489, 2105)
    return {
        "schema": "math_exam_staging_draft/v1",
        "paper": {
            "id": "2026-BAOSHAN-ERMO",
            "title": "2026 宝山初三二模",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": "documents/q24",
        },
        "question_bank": "../../question-bank.yaml",
        "sections": [{
            "id": "problem",
            "title": "三、解答题",
            "items": [{
                "item_id": "Q001",
                "question_number": 24,
                "question_type": "problem",
                "points": 12,
                "prompt": [
                    {"source": "documents/q24/media/image295.png", "box_px": [0, 0, 1068, 954]},
                    {"source": "documents/q24/media/image301.png", "box_px": [0, 0, 1181, 1037]},
                    {"source": "documents/q24/media/image302.png", "box_px": [0, 0, 1177, 1068]},
                ],
                "question_word_evidence": [
                    {"page_image": "documents/q24/word/pages/001.png", "page_number": 1},
                    {"page_image": "documents/q24/word/pages/002.png", "page_number": 2},
                    {"page_image": "documents/q24/word/pages/003.png", "page_number": 3},
                ],
                "official_solution": {
                    "start_anchor": "24.",
                    "end_anchor": "25.",
                    "word_evidence": [
                        {"page_image": "documents/q24/word/pages/007.png", "page_number": 7},
                    ],
                    "crops": [],
                },
                "block": {
                    "stem_latex": "如图，抛物线$y=ax^2+bx+c$经过$A(-1,0)$、$B(3,0)$。",
                    "answer": "见官方解答",
                    "clue": "分小问依次求解。",
                    "solution_steps": ["(1) 求抛物线表达式。"],
                },
            }],
        }],
    }


def test_multi_image_resolved_draft_runs_full_pipeline(fake_repo: Path):
    """The composed group PNG must be written to disk with real dimensions and
    survive expand → materialize → audit. This is the test that was missing from
    commit 3 and would have caught the not-written / box_px=[0,0,0,0] bugs."""
    from scripts.question_transcription.materialize_image_group import (
        resolve_placement_decisions,
    )

    expand = _load_module("expand_staging_draft", INGESTION / "expand_staging_draft.py")
    repo = fake_repo
    (repo / "question-bank.yaml").write_text(
        "schema: math_topic_question_bank/v1\n", encoding="utf-8"
    )
    staging = repo / "staging" / "2026-BAOSHAN-ERMO"
    staging.mkdir(parents=True, exist_ok=True)

    draft = _baoshan_q24_draft(repo)
    # Phase 1: resolve placements (rewrite draft, stash composition plan). The
    # staging tree does not exist yet, so no PNG is written here.
    resolved = resolve_placement_decisions(draft, repo, staging_dir=None)
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(resolved.draft, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    item = resolved.draft["sections"][0]["items"][0]
    assert len(item["prompt"]) == 1
    crop = item["prompt"][0]
    # P0-2: box_px must have positive area, not [0,0,0,0].
    left, top, right, bottom = crop["box_px"]
    assert right > left and bottom > top, (
        f"composed crop box_px must have positive area, got {crop['box_px']}"
    )

    # Run the DOCX word-evidence resolver exactly as the docx skill's fixed flow
    # requires — it fills the contiguous page ranges the coverage audit enforces.
    # Must run BEFORE expand (it rewrites paper.draft.yaml in place).
    word_ev = _load_module(
        "word_evidence_pages",
        ROOT / ".codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py",
    )
    draft_payload = yaml.safe_load((staging / "paper.draft.yaml").read_text("utf-8"))
    updated, _ = word_ev.resolve_draft_payload(draft_payload, repo_root=repo)
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(updated, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    # Expand must succeed (single-crop role with assignment_path) and create the
    # staging/items tree.
    expand.expand_draft(staging / "paper.draft.yaml")
    assert (staging / "paper.yaml").exists()

    # Phase 2: NOW the staging tree exists — write the composed group PNGs.
    assert resolved.renderer is not None
    resolved.renderer.compose_groups(staging)

    # P0-1: the composed group PNG must actually exist on disk before materialize.
    # compose_groups patches the item's source.yaml so the composed crop's source
    # is the absolute path of the written PNG.
    source_yaml = yaml.safe_load(
        (staging / "items" / "Q001" / "source.yaml").read_text(encoding="utf-8")
    )
    composed_source = source_yaml["crops"]["prompt"][0]["source"]
    composed_path = Path(composed_source)
    assert composed_path.is_file(), (
        f"composed group PNG was not written to disk: {composed_path}"
    )

    # Materialize must crop the composed PNG without error.
    proc = subprocess.run(
        [sys.executable, str(INGESTION / "materialize_staging.py"),
         str(staging), "--repo-root", str(repo)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"materialize failed:\n{proc.stderr}\n{proc.stdout}"

    # The cropped prompt asset exists.
    item_dir = staging / "items" / "Q001"
    assert (item_dir / "assets/prompt-01.png").exists()

    # Audit must pass.
    proc = subprocess.run(
        [sys.executable, str(INGESTION / "audit_staging.py"),
         str(staging), "--repo-root", str(repo)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"audit failed:\n{proc.stderr}\n{proc.stdout}"
    assert "STAGING VALID" in proc.stdout
