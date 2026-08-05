"""P4 convergence: bundles -> assembler -> expand -> materialize -> audit.

This is the integration that proves the scripted-transcription architecture
plugs into the existing downstream pipeline unchanged. We build a small DOCX
paper (with real on-disk PNG stubs at the declared sizes) and a small PDF
paper, assemble each from its two bundles, then run the REAL
expand_staging_draft / materialize_staging / audit_staging against a repo-root
that contains a linked .codex tree (materialize derives student assignments).

Both papers must pass structural audit -- i.e. the assembler's drafts are
indistinguishable from hand-authored drafts to the existing tooling.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.source.adapt_docx_images import adapt as adapt_docx  # noqa: E402
from scripts.question_transcription.workflow.adapters.source.adapt_pdf_images import adapt as adapt_pdf  # noqa: E402
from scripts.question_transcription.assemble_paper_draft import assemble  # noqa: E402
from scripts.question_transcription.contracts import (  # noqa: E402
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)

INGESTION = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _png(path: Path, width: int, height: int) -> None:
    """Write a real PNG of the given size (white)."""
    from PIL import Image as _Image

    path.parent.mkdir(parents=True, exist_ok=True)
    _Image.new("RGB", (width, height), "white").save(path, format="PNG")


# --------------------------------------------------------------------------- #
# Shared: assemble + expand + materialize + audit against a fake repo root
# --------------------------------------------------------------------------- #


def _run_pipeline(
    *,
    repo_root: Path,
    paper_id: str,
    transcription: QuestionTranscriptionBundle,
    image_bundle: ImageAttributionBundle,
    docx_track: bool,
) -> tuple[object, str]:
    """Assemble, expand, materialize, audit. Returns (audit CompletedProcess, paper_id).

    For the DOCX track the existing docx skill's deterministic cross-page resolver
    (word_evidence_pages.py) is run before expand, exactly as the docx skill's
    fixed flow requires; it fills the contiguous page ranges the coverage audit
    enforces.
    """
    expand = _load_module("expand_staging_draft", INGESTION / "expand_staging_draft.py")
    staging = repo_root / "staging" / paper_id
    staging.mkdir(parents=True, exist_ok=True)
    (repo_root / "question-bank.yaml").write_text(
        "schema: math_topic_question_bank/v1\n", encoding="utf-8"
    )

    draft, report = assemble(transcription, image_bundle)
    assert draft is not None, f"assembly failed: {[e.code for e in report.errors]}"
    draft["question_bank"] = "../../question-bank.yaml"
    (staging / "paper.draft.yaml").write_text(
        yaml.safe_dump(draft, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    if docx_track:
        word_ev = _load_module(
            "word_evidence_pages",
            ROOT / ".codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py",
        )
        updated, _ = word_ev.resolve_draft_payload(
            yaml.safe_load((staging / "paper.draft.yaml").read_text("utf-8")),
            repo_root=repo_root,
        )
        (staging / "paper.draft.yaml").write_text(
            yaml.safe_dump(updated, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )

    expand.expand_draft(staging / "paper.draft.yaml")
    assert (staging / "paper.yaml").exists()

    # materialize via CLI so subprocess (derive_student) sees the .codex link.
    import subprocess

    proc = subprocess.run(
        [
            sys.executable,
            str(INGESTION / "materialize_staging.py"),
            str(staging),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"materialize failed:\n{proc.stderr}\n{proc.stdout}"

    proc = subprocess.run(
        [
            sys.executable,
            str(INGESTION / "audit_staging.py"),
            str(staging),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
    )
    return proc, paper_id


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """A repo root with a linked .codex tree so materialize can derive students."""
    link = tmp_path / ".codex"
    try:
        link.symlink_to(ROOT / ".codex", target_is_directory=True)
    except FileExistsError:
        pass
    except OSError:
        pytest.skip("cannot symlink .codex on this platform")
    return tmp_path


# --------------------------------------------------------------------------- #
# DOCX track: synthetic Word paper with real on-disk media + page PNGs
# --------------------------------------------------------------------------- #


def _docx_bundle(repo_root: Path) -> tuple[QuestionTranscriptionBundle, ImageAttributionBundle]:
    archive_dir = repo_root / "documents/初三/SYNTH-DOCX-PAPER"
    archive_rel = "documents/初三/SYNTH-DOCX-PAPER"
    # Real media + page PNGs at declared sizes.
    _png(archive_dir / "word/media/image1.png", 475, 512)  # prompt figure
    _png(archive_dir / "word/media/image2.png", 510, 512)  # solution figure
    _png(archive_dir / "word/pages/013.png", 1489, 2105)
    _png(archive_dir / "word/pages/014.png", 1489, 2105)

    word_source = {
        "schema": "math_word_source_extract/v1",
        "media": [
            {"path": "media/image1.png", "sha256": "sha256:" + "a" * 64, "width_px": 475, "height_px": 512},
            {"path": "media/image2.png", "sha256": "sha256:" + "b" * 64, "width_px": 510, "height_px": 512},
        ],
        "image_attribution": [
            {"media": "media/image1.png", "question_number": 1, "bucket": "prompt", "paragraph_index": 5, "confidence": "high"},
            {"media": "media/image2.png", "question_number": 1, "bucket": "solution", "paragraph_index": 9, "confidence": "high"},
        ],
    }
    transcription = QuestionTranscriptionBundle.model_validate(
        {
            "schema": "math_question_transcription/v1",
            "paper": {
                "id": "SYNTH-DOCX-PAPER",
                "title": "合成 DOCX 试卷",
                "grade": "九年级",
                "source_archive": archive_rel,
            },
            "sections": [
                {
                    "section_ref": "fillin",
                    "title": "二、填空题",
                    "questions": [
                        {
                            "question_ref": "1",
                            "question_number": 1,
                            "question_type": "short_answer",
                            "points": 4,
                            "content": {
                                "stem_latex": "如图，求$BE$的范围。",
                                "answer": "$4\\leqslant BE\\leqslant 6$",
                                "clue": "取中点并使用中位线。",
                                "solution_steps": [
                                    "取$AC$的中点$F$。",
                                    "由中位线得$EF=1$。",
                                    "由勾股定理得$BF=5$。",
                                ],
                            },
                            "evidence": {
                                "question": [{"kind": "page", "source": f"{archive_rel}/word/pages/013.png", "page_number": 13}],
                                "solution": [{"kind": "page", "source": f"{archive_rel}/word/pages/014.png", "page_number": 14}],
                                "solution_start_anchor": "【解答】",
                                "solution_end_anchor": "2．",
                            },
                        }
                    ],
                }
            ],
            "provider": {"kind": "agent", "name": "codex", "version": "v1"},
        }
    )
    image_bundle = ImageAttributionBundle.model_validate(
        adapt_docx(word_source, paper_id="SYNTH-DOCX-PAPER", source_archive=archive_rel)
    )
    return transcription, image_bundle


def test_docx_track_full_pipeline_passes_audit(fake_repo: Path):
    t, i = _docx_bundle(fake_repo)
    proc, paper_id = _run_pipeline(
        repo_root=fake_repo, paper_id="SYNTH-DOCX-PAPER", transcription=t, image_bundle=i,
        docx_track=True,
    )
    assert proc.returncode == 0, f"audit failed:\n{proc.stderr}\n{proc.stdout}"
    assert "STAGING VALID" in proc.stdout
    # Materialize produced the cropped asset PNGs from the full-crop media.
    item_dir = fake_repo / "staging/SYNTH-DOCX-PAPER/items/Q001"
    assert (item_dir / "assets/prompt-01.png").exists()
    assert (item_dir / "assets/official-solution-01.png").exists()


# --------------------------------------------------------------------------- #
# PDF track: synthetic scan paper with real page PNGs
# --------------------------------------------------------------------------- #


def _pdf_bundle() -> tuple[QuestionTranscriptionBundle, ImageAttributionBundle]:
    archive_rel = "documents/初三/SYNTH-PDF-PAPER"
    detection = {
        "schema": "math_pdf_detection/v1",
        "paper_id": "SYNTH-PDF-PAPER",
        "source_archive": archive_rel,
        "pages": [
            {"path": "pages-pages/004.png", "sha256": "sha256:" + "1" * 64, "width_px": 1240, "height_px": 1754},
            {"path": "pages-pages/008.png", "sha256": "sha256:" + "2" * 64, "width_px": 1240, "height_px": 1754},
        ],
        "detections": [
            {"page_path": "pages-pages/004.png", "question_number": 1, "role": "prompt", "box_px": [650, 315, 1000, 690], "confidence": "medium", "note": "figure"},
        ],
    }
    transcription = QuestionTranscriptionBundle.model_validate(
        {
            "schema": "math_question_transcription/v1",
            "paper": {
                "id": "SYNTH-PDF-PAPER",
                "title": "合成 PDF 试卷",
                "grade": "九年级",
                "source_archive": archive_rel,
            },
            "sections": [
                {
                    "section_ref": "problem",
                    "title": "三、解答题",
                    "questions": [
                        {
                            "question_ref": "1",
                            "question_number": 1,
                            "question_type": "problem",
                            "points": 10,
                            "content": {
                                "stem_latex": "如图，求抛物线表达式。",
                                "answer": "$y=-x^2+2x+3$",
                                "clue": "待定系数法。",
                                "solution_steps": ["设表达式。", "代入求$a$。"],
                            },
                            "evidence": {
                                "question": [{"kind": "region", "source": f"{archive_rel}/pages-pages/004.png", "page_number": 4, "box_px": [80, 210, 1010, 860]}],
                                "solution": [{"kind": "region", "source": f"{archive_rel}/pages-pages/008.png", "page_number": 8, "box_px": [80, 120, 1010, 700]}],
                                "solution_start_anchor": "1．",
                                "solution_end_anchor": "2．",
                            },
                        }
                    ],
                }
            ],
            "provider": {"kind": "vision_api", "name": "gpt-vision", "version": "v1"},
        }
    )
    image_bundle = ImageAttributionBundle.model_validate(adapt_pdf(detection))
    return transcription, image_bundle


def test_pdf_track_full_pipeline_passes_audit(fake_repo: Path):
    """PDF region track passes the unchanged downstream structural audit."""
    t, i = _pdf_bundle()
    # Real page PNGs at declared sizes.
    archive_dir = fake_repo / "documents/初三/SYNTH-PDF-PAPER"
    _png(archive_dir / "pages-pages/004.png", 1240, 1754)
    _png(archive_dir / "pages-pages/008.png", 1240, 1754)
    proc, paper_id = _run_pipeline(
        repo_root=fake_repo, paper_id="SYNTH-PDF-PAPER", transcription=t, image_bundle=i,
        docx_track=False,
    )
    # The draft assembled and materialized; the region prompt crop was produced.
    item_dir = fake_repo / "staging/SYNTH-PDF-PAPER/items/Q001"
    assert (item_dir / "assets/prompt-01.png").exists()
    assert proc.returncode == 0, f"audit failed:\n{proc.stderr}\n{proc.stdout}"
    assert "STAGING VALID" in proc.stdout


# --------------------------------------------------------------------------- #
# DOCX-vs-PDF equivalence (§11 convergence): both produce v1 drafts with the
# track-specific evidence shape; both pass audit.
# --------------------------------------------------------------------------- #


def test_docx_and_pdf_tracks_both_pass_audit(fake_repo: Path):
    td, id_ = _docx_bundle(fake_repo)
    tp, ip = _pdf_bundle()
    _png(fake_repo / "documents/初三/SYNTH-PDF-PAPER/pages-pages/004.png", 1240, 1754)
    _png(fake_repo / "documents/初三/SYNTH-PDF-PAPER/pages-pages/008.png", 1240, 1754)
    proc_d, _ = _run_pipeline(
        repo_root=fake_repo, paper_id="SYNTH-DOCX-PAPER", transcription=td, image_bundle=id_,
        docx_track=True,
    )
    proc_p, _ = _run_pipeline(
        repo_root=fake_repo, paper_id="SYNTH-PDF-PAPER", transcription=tp, image_bundle=ip,
        docx_track=False,
    )
    # DOCX track fully passes audit.
    assert proc_d.returncode == 0 and "STAGING VALID" in proc_d.stdout
    # PDF region track also fully passes audit.
    assert proc_p.returncode == 0 and "STAGING VALID" in proc_p.stdout
