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
from scripts.question_transcription.workflow.adapters.source.source_paper import (
    _project_minimal_v2,
)
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
