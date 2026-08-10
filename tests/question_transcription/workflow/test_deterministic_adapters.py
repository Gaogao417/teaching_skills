"""Lane D deterministic-adapter offline tests.

The heavy deterministic functions (extract_docx_source / render_pdf_pages / assemble
/ expand / materialize / audit) need soffice/pdftoppm and real fixtures, so they are
exercised end-to-end only with live DOCX/PDF runs. Here we test the pure pieces:

- the final-review reader's status projection (pure file logic);
- the source-paper v2 projection from a v1 transcription (pure dict transform);
- the composition root binds real adapters under ``mode="live"`` (import-only).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.review import (
    DeterministicFinalReviewReader,
)
from scripts.question_transcription.workflow.adapters.source.extraction import (
    DocxOrPdfSourceExtractor,
)
from scripts.question_transcription.workflow.adapters.source.image_attribution import (
    DocxOrPdfImageAttribution,
)
from scripts.question_transcription.workflow.adapters.source.source_paper import (
    _project_minimal_v2,
)
from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
    DeterministicDraftProjector,
)
from scripts.question_transcription.workflow.contracts import SourceInput
from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


# --------------------------------------------------------------------------- #
# Final review reader
# --------------------------------------------------------------------------- #


def _write_item_review(staging: Path, item: str, status: str) -> None:
    d = staging / "items" / item
    d.mkdir(parents=True, exist_ok=True)
    (d / "review.yaml").write_text(yaml.safe_dump({"status": status}), encoding="utf-8")


def test_final_review_reader_approved(tmp_path):
    store = _store(tmp_path)
    reader = DeterministicFinalReviewReader(store)
    staging = Path(store.layout.root) / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    _write_item_review(staging, "Q001", "approved")
    _write_item_review(staging, "Q002", "approved")
    status, failure, detail, items = reader.read_status(str(staging))
    assert status == "approved"
    assert items == []


def test_final_review_reader_pending(tmp_path):
    store = _store(tmp_path)
    reader = DeterministicFinalReviewReader(store)
    staging = Path(store.layout.root) / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    _write_item_review(staging, "Q001", "approved")
    _write_item_review(staging, "Q002", "pending")
    status, failure, detail, items = reader.read_status(str(staging))
    assert status == "pending"
    assert items == ["Q002"]


def test_final_review_reader_rejected(tmp_path):
    store = _store(tmp_path)
    reader = DeterministicFinalReviewReader(store)
    staging = Path(store.layout.root) / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    _write_item_review(staging, "Q001", "approved")
    _write_item_review(staging, "Q002", "rejected")
    status, failure, detail, items = reader.read_status(str(staging))
    assert status == "rejected"
    assert items == ["Q002"]


def test_final_review_reader_empty_is_pending(tmp_path):
    store = _store(tmp_path)
    reader = DeterministicFinalReviewReader(store)
    staging = Path(store.layout.root) / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    status, *_ = reader.read_status(str(staging))
    assert status == "pending"


# --------------------------------------------------------------------------- #
# Source-paper v2 projection
# --------------------------------------------------------------------------- #


def test_project_minimal_v2_preserves_text_fields():
    transcription = {
        "schema": "math_question_transcription/v1",
        "paper": {"id": "PAPER-A", "title": "t", "grade": "初三", "source_archive": "x"},
        "sections": [
            {"section_ref": "1", "title": "一", "questions": [
                {"question_ref": "1", "question_number": 1, "question_type": "problem",
                 "points": 10,
                 "content": {"stem_latex": "求 $x$", "answer": "2", "clue": "c",
                             "solution_steps": ["step one", "step two"]},
                 "evidence": {"question": [{"kind": "page", "source": "p", "page_number": 1}],
                              "solution": [{"kind": "page", "source": "p", "page_number": 2}],
                              "solution_start_anchor": "a", "solution_end_anchor": "b"}},
            ]}
        ],
        "provider": {"kind": "agent", "name": "glm-5.2", "version": "v1"},
    }
    v2 = _project_minimal_v2(transcription)
    assert v2["schema"] == "math_exam_source_paper/v2"
    assert v2["paper_id"] == "PAPER-A"
    q = v2["questions"][0]
    assert q["question_ref"] == "1"
    assert q["content"]["stem"][0]["text"] == "求 $x$"
    assert q["content"]["answer"] == "2"
    assert [s["content"][0]["text"] for s in q["content"]["solution_steps"]] == [
        "step one", "step two"
    ]


# --------------------------------------------------------------------------- #
# Composition binds real adapters under mode=live (import-only smoke)
# --------------------------------------------------------------------------- #


def test_composition_live_binding_imports_real_adapters(tmp_path):
    from scripts.question_transcription.workflow.bootstrap.composition import bind, build_run_layout
    from scripts.question_transcription.workflow.bootstrap.config import RuntimeAdapterConfig

    layout = build_run_layout(tmp_path / "build", "p", "r")
    # bind(mode="live") must import the real adapter modules without network/key use
    # (keys are only read at call time). This catches import-wiring regressions.
    deps = bind(RuntimeAdapterConfig(), layout, mode="live")
    assert deps.page_text_extractor is not None
    assert deps.whole_paper_transcriber is not None
    assert deps.deterministic.source_extractor is not None


# --------------------------------------------------------------------------- #
# DOCX manifest -> image attribution -> draft contract
# --------------------------------------------------------------------------- #


def test_docx_manifest_identity_and_media_paths_reach_draft(tmp_path):
    """Workflow metadata and extracted media survive the real adapter chain."""

    store = _store(tmp_path)
    source_path = tmp_path / "original.docx"
    source_path.write_bytes(b"docx fixture")

    output_dir = store.layout.source_dir / "docx"
    media_path = output_dir / "media" / "image18.png"
    page_path = output_dir / "pages" / "page-001.png"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    page_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"png fixture")
    page_path.write_bytes(b"page fixture")

    manifest = {
        "schema": "math_word_source_extract/v1",
        "source": {
            "path": "source.docx",
            "format": "docx",
            "sha256": "sha256:" + "0" * 64,
        },
        "media": [
            {
                "path": "media/image18.png",
                "sha256": "sha256:" + "1" * 64,
                "width_px": 320,
                "height_px": 180,
            }
        ],
        "image_attribution_status": "complete",
        "image_attribution": [
            {
                "media": "media/image18.png",
                "bucket": "prompt",
                "question_number": 1,
                "confidence": "high",
                "paragraph_index": 3,
            }
        ],
        "rendered_pages": [{"path": "pages/page-001.png"}],
    }
    source = SourceInput(
        paper_id="PAPER-1",
        source_kind="docx",
        source_path=str(source_path),
        source_archive=str(source_path),
    )
    extractor = DocxOrPdfSourceExtractor(store)
    extracted, failure, detail = extractor._materialize_extracted(
        source, manifest, output_dir, kind="docx"
    )
    assert (failure, detail) == (None, None)

    frozen_manifest = store.read_yaml(extracted.manifest)
    assert frozen_manifest["paper_id"] == "PAPER-1"
    assert frozen_manifest["source_archive"] == str(source_path)

    image_adapter = DocxOrPdfImageAttribution(store)
    images_ref, status, issues_ref, detail = image_adapter.attribute(extracted.manifest)
    assert (status, issues_ref, detail) == ("complete", None, None)
    images = store.read_yaml(images_ref)
    assert images["paper_id"] == "PAPER-1"
    assert images["assets"][0]["source"] == str(media_path.resolve())

    transcription = {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": "PAPER-1",
            "title": "Contract fixture",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": str(source_path),
            "question_bank": "../../question-bank.yaml",
        },
        "sections": [
            {
                "section_ref": "problems",
                "title": "解答题",
                "questions": [
                    {
                        "question_ref": "1",
                        "question_number": 1,
                        "question_type": "problem",
                        "points": 10,
                        "content": {
                            "stem_latex": "如图，求$x$。",
                            "answer": "$x=1$",
                            "clue": "代入。",
                            "solution_steps": ["代入得$x=1$。"],
                            "solution_notes": [],
                        },
                        "evidence": {
                            "question": [
                                {
                                    "kind": "page",
                                    "source": str(page_path.resolve()),
                                    "page_number": 1,
                                }
                            ],
                            "solution": [
                                {
                                    "kind": "page",
                                    "source": str(page_path.resolve()),
                                    "page_number": 1,
                                }
                            ],
                            "solution_start_anchor": "解：",
                            "solution_end_anchor": "结束",
                        },
                    }
                ],
            }
        ],
        "provider": {"kind": "agent", "name": "fixture", "version": "v1"},
    }
    transcription_ref = store.commit_yaml(
        "structured/transcription.yaml",
        transcription,
        "math_question_transcription/v1",
    )
    # Build the authoritative v2 source paper via the builder (it joins the
    # transcription + image bundle + manifest), instead of committing a minimal
    # stub. The projector now consumes the v2 paper, not the v1 bundles directly.
    from scripts.question_transcription.workflow.adapters.source.source_paper import (
        DeterministicSourcePaperBuilder,
    )

    builder = DeterministicSourcePaperBuilder(store)
    build_result, b_failure, b_detail = builder.build(
        transcription_ref,
        images_ref,
        extracted.manifest,
        None,
    )
    assert (b_failure, b_detail) == (None, None)
    source_paper_ref = build_result.source_paper
    draft_ref, failure, detail = DeterministicDraftProjector(store).project(
        source_paper_ref
    )
    assert (failure, detail) == (None, None), f"project failed: {failure}: {detail}"
    draft = store.read_yaml(draft_ref)
    assert draft["sections"][0]["items"][0]["prompt"][0]["source"] == str(
        media_path.resolve()
    )
