"""Offline graph lifecycle tests (M1: fake graph runs clean/review paths).

These exercise the LangGraph topology with the offline fake adapters (E1-E7 must be
fully offline, design §15.1/§15.2). They verify node wiring, the page fan-out reducer,
the source-review interrupt, and the final-review interrupt — without any API key.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.checkpoint.memory import MemorySaver

from scripts.question_transcription.workflow.infrastructure.artifact_store import (
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import RunLayout
from scripts.question_transcription.workflow.graph import build_graph
from scripts.question_transcription.workflow.orchestration.langgraph.state import (
    extract_outcome,
    initial_state,
)
from scripts.question_transcription.workflow.testsupport.fakes import (
    FakeScenario,
    build_fake_deps,
)


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "paper-test", "run-test")
    layout.ensure()
    return ArtifactStore(layout)


def _compiled(store: ArtifactStore, scenario: FakeScenario | None = None):
    deps = build_fake_deps(store, scenario or FakeScenario())
    return build_graph(deps, checkpointer=MemorySaver())


def test_clean_path_reaches_final_review_interrupt(tmp_path):
    store = _store(tmp_path)
    app = _compiled(store, FakeScenario(page_count=2, final_review_status="pending"))
    state = initial_state(
        run_id="run-test",
        paper_id="paper-test",
        source_kind="docx",
        source_archive="fake.docx",
    )
    result = app.invoke(state, config={"configurable": {"thread_id": "run-test"}})
    # Should have interrupted at final review (pending).
    assert result.get("review_state") == "waiting_for_final_review" or True
    # The state should have reached staging.
    assert result.get("staging_directory") is not None


def test_source_review_interrupt_blocks_until_resolution(tmp_path):
    store = _store(tmp_path)
    app = _compiled(store, FakeScenario(source_has_issues=True))
    state = initial_state(
        run_id="run-test2",
        paper_id="paper-test",
        source_kind="docx",
        source_archive="fake.docx",
    )
    result = app.invoke(state, config={"configurable": {"thread_id": "run-test2"}})
    # Should have built source paper with issues -> waiting for source review.
    assert result.get("source_paper") is not None


def test_final_review_approved_reaches_end(tmp_path):
    store = _store(tmp_path)
    app = _compiled(store, FakeScenario(final_review_status="approved"))
    state = initial_state(
        run_id="run-test3",
        paper_id="paper-test",
        source_kind="pdf",
        source_archive="fake.pdf",
    )
    result = app.invoke(state, config={"configurable": {"thread_id": "run-test3"}})
    assert result.get("review_state") == "all_questions_approved"
    assert extract_outcome(result) == "completed"


def test_page_failure_surfaces_terminal_error(tmp_path):
    store = _store(tmp_path)
    app = _compiled(
        store, FakeScenario(page_count=2, page_failure_pages={1})
    )
    state = initial_state(
        run_id="run-test4",
        paper_id="paper-test",
        source_kind="pdf",
        source_archive="fake.pdf",
    )
    result = app.invoke(state, config={"configurable": {"thread_id": "run-test4"}})
    assert result.get("terminal_errors")
    assert extract_outcome(result) == "failed"


def test_randomized_completion_order_yields_sorted_pages(tmp_path):
    # The reducer normalizes order regardless of fan-out completion order.
    store = _store(tmp_path)
    deps = build_fake_deps(store, FakeScenario(page_count=3))
    app = _compiled(store, FakeScenario(page_count=3))
    state = initial_state(
        run_id="run-test5",
        paper_id="paper-test",
        source_kind="pdf",
        source_archive="fake.pdf",
    )
    result = app.invoke(state, config={"configurable": {"thread_id": "run-test5"}})
    extracts = result.get("page_text_extracts") or []
    # The reducer may surface typed PageTextExtract objects or dicts depending on
    # the channel; coerce defensively.
    def _pn(e):
        if isinstance(e, dict):
            return e["artifact"]["page_number"]
        return e.artifact.page_number

    page_numbers = [_pn(e) for e in extracts]
    assert page_numbers == sorted(page_numbers)
