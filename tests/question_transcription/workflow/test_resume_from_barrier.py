from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.cli import resume_from_barrier
from scripts.question_transcription.workflow.bootstrap.composition import (
    bind,
    build_run_layout,
)
from scripts.question_transcription.workflow.bootstrap.config import (
    RuntimeAdapterConfig,
)
from scripts.question_transcription.workflow.checkpoint import (
    make_sqlite_checkpointer,
)
from scripts.question_transcription.workflow.graph import build_graph
from scripts.question_transcription.workflow.orchestration.langgraph.state import (
    initial_state,
)


def _seed_run_via_graph(tmp_path: Path) -> tuple:
    """Run the real graph in fake mode to leave a schema-valid checkpoint.

    The fake composition completes the whole graph, so the checkpoint carries
    valid values for every downstream channel. We then corrupt the
    page-text/error channels to mimic an E-class barrier failure (incomplete
    extracts + a stale terminal error) before handing the run to resume_one.
    """
    build_root = tmp_path / "build"
    layout = build_run_layout(build_root, "PAPER-E", "run-e1")
    deps = bind(RuntimeAdapterConfig(), layout, mode="fake")
    saver = make_sqlite_checkpointer(layout.root / "run-e1.sqlite")
    app = build_graph(deps, checkpointer=saver)
    config = {"configurable": {"thread_id": "run-e1"}, "recursion_limit": 200}
    state = initial_state(
        run_id="run-e1",
        paper_id="PAPER-E",
        source_kind="docx",
        source_archive=str(layout.root / "source.docx"),
    )
    app.invoke(state, config)
    return layout, deps, config


def test_apply_clears_stale_barrier_error_and_reruns_chain(tmp_path: Path) -> None:
    """The stale page-extraction error in the checkpoint must not survive.

    We seed a valid graph checkpoint, then corrupt it to mimic an E-class run
    (incomplete extracts + a stale terminal error), and confirm resume_one drops
    the stale error, substitutes the extracts from state.json, and drives the
    full chain to completion.
    """
    layout, deps, config = _seed_run_via_graph(tmp_path)

    # Corrupt the checkpoint to mimic an E-class barrier failure: drop the
    # whole-paper/source/draft outputs (downstream never ran) and inject a stale
    # terminal error plus incomplete extracts.
    tup = make_sqlite_checkpointer(layout.root / "run-e1.sqlite").get_tuple(
        {"configurable": {"thread_id": "run-e1"}}
    )
    channels = dict(tup.checkpoint["channel_values"])
    for key in (
        "whole_paper_transcription",
        "source_paper",
        "draft",
        "staging_directory",
        "review_state",
    ):
        channels.pop(key, None)
    channels["page_text_extracts"] = []  # incomplete at barrier time
    channels["terminal_errors"] = [
        "page extraction failed: ['page 1: invalid_response (boom)']"
    ]
    # Re-put the corrupted checkpoint through the saver so resume_one reads it.
    import langgraph.checkpoint.base as base

    saver = make_sqlite_checkpointer(layout.root / "run-e1.sqlite")
    saver.put(
        {"configurable": {"thread_id": "run-e1", "checkpoint_ns": ""}},
        {**tup.checkpoint, "channel_values": channels},
        {"source": "loop", "step": 99, "writes": {"page_barrier": ["terminal_errors"]}},
        {},
    )

    # retry_page_text's output: complete extracts + cleared errors in state.json.
    extract = {
        "artifact": {
            "page_number": 1,
            "text": {
                "path": "pages/page-001.txt",
                "sha256": "sha256:" + "1" * 64,
                "schema": "text/plain",
            },
            "metadata": {
                "path": "pages/page-001.extract.yaml",
                "sha256": "sha256:" + "2" * 64,
                "schema": "page-text-extract/v1",
            },
            "provenance": {
                "adapter_id": "mimo",
                "model": "mimo",
                "prompt_version": "page-text-ocr-v1",
            },
        }
    }
    (layout.root / "state.json").write_text(
        json.dumps(
            {"page_text_extracts": [extract], "page_text_failures": [], "terminal_errors": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = resume_from_barrier.resume_one(
        layout, agent_host="opencode", page_provider="mimo", apply=True, mode="fake"
    )

    assert result.status == "resumed", f"detail={result.detail}"
    assert [s["node"] for s in result.stages] == [
        "transcribe_whole_paper",
        "build_source_paper",
        "build_draft",
        "complete_evidence",
        "split_into_questions",
        "build_assets",
        "audit_staging",
        "refresh_review_ui",
    ]
    assert all(s["status"] == "passed" for s in result.stages)


def test_resume_blocks_when_checkpoint_missing(tmp_path: Path) -> None:
    layout = build_run_layout(tmp_path / "build", "PAPER-E", "run-e1")
    layout.ensure()
    (layout.root / "state.json").write_text(
        json.dumps({"page_text_extracts": [], "terminal_errors": []}),
        encoding="utf-8",
    )

    result = resume_from_barrier.resume_one(
        layout, agent_host="opencode", page_provider="mimo", apply=True, mode="fake"
    )

    assert result.status == "blocked"
    assert "checkpoint" in (result.detail or "")


def test_resume_blocks_when_state_json_missing(tmp_path: Path) -> None:
    layout, _deps, _config = _seed_run_via_graph(tmp_path)
    # state.json absent (retry_page_text not run).

    result = resume_from_barrier.resume_one(
        layout, agent_host="opencode", page_provider="mimo", apply=True, mode="fake"
    )

    assert result.status == "blocked"
    assert "state.json" in (result.detail or "")


def test_dry_run_lists_planned_stages_without_calling_agent(tmp_path: Path) -> None:
    layout, _deps, _config = _seed_run_via_graph(tmp_path)
    (layout.root / "state.json").write_text(
        json.dumps({"page_text_extracts": [], "terminal_errors": []}),
        encoding="utf-8",
    )

    result = resume_from_barrier.resume_one(
        layout, agent_host="opencode", page_provider="mimo", apply=False, mode="fake"
    )

    assert result.status == "dry-run"
    assert len(result.stages) == 8
    assert all(s["status"] == "planned" for s in result.stages)
