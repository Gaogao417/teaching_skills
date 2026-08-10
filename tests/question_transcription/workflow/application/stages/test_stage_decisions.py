"""Unit tests for the framework-agnostic application stages (architecture §3.4, M4).

These prove the application stages are testable WITHOUT LangGraph: they are pure
decision/validation helpers imported directly, with no graph compilation. They also
assert the stages import no LangGraph/provider-SDK symbols.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.application.stages.page_text import (
    PageBarrierDecision,
    decide_page_barrier,
)
from scripts.question_transcription.workflow.application.stages.source import (
    SourceReadyDecision,
    decide_source_ready,
)
from scripts.question_transcription.workflow.application.stages.whole_paper import (
    validate_page_coverage,
)
from scripts.question_transcription.workflow.contracts import (
    ArtifactRef,
    PageTextArtifact,
    PageTextExtract,
    ExecutionProvenance,
)


def _extract(page: int) -> PageTextExtract:
    return PageTextExtract(
        artifact=PageTextArtifact(
            page_number=page,
            text=ArtifactRef(path=f"p{page}.txt", sha256="sha256:" + "a" * 64, schema="text/plain"),
            metadata=ArtifactRef(path=f"p{page}.yaml", sha256="sha256:" + "b" * 64, schema="x/v1"),
            provenance=ExecutionProvenance(adapter_id="qwen", model="m", prompt_version="v1"),
        )
    )


# --------------------------------------------------------------------------- #
# Page barrier decision
# --------------------------------------------------------------------------- #


def test_barrier_ready_on_exact_coverage():
    decision, detail = decide_page_barrier([1, 2], [_extract(1), _extract(2)], [])
    assert decision == PageBarrierDecision.READY
    assert detail == [1, 2]


def test_barrier_wait_on_missing_pages():
    decision, detail = decide_page_barrier([1, 2, 3], [_extract(1)], [])
    assert decision == PageBarrierDecision.WAIT
    assert detail == [2, 3]


def test_barrier_stop_on_failures():
    decision, detail = decide_page_barrier([1], [], ["page 1: empty_text"])
    assert decision == PageBarrierDecision.STOP_FAILURES
    assert detail == ["page 1: empty_text"]


def test_barrier_stop_on_duplicate_pages():
    decision, detail = decide_page_barrier([1, 2], [_extract(1), _extract(1)], [])
    assert decision == PageBarrierDecision.STOP_COVERAGE


def test_barrier_stop_on_unexpected_pages():
    decision, detail = decide_page_barrier([1], [_extract(1), _extract(2)], [])
    assert decision == PageBarrierDecision.STOP_COVERAGE


# --------------------------------------------------------------------------- #
# Whole-paper coverage validation
# --------------------------------------------------------------------------- #


def test_validate_page_coverage_orders_and_accepts():
    ordered, err = validate_page_coverage([_extract(2), _extract(1)])
    assert err is None
    assert [e.artifact.page_number for e in ordered] == [1, 2]


def test_validate_page_coverage_rejects_empty_and_duplicates():
    assert validate_page_coverage([])[1] == "no page text extracts"
    assert "duplicate" in validate_page_coverage([_extract(1), _extract(1)])[1]


# --------------------------------------------------------------------------- #
# Source-ready gate
# --------------------------------------------------------------------------- #


def test_source_gate_stop_when_no_build_result():
    decision, _ = decide_source_ready(None, None)
    assert decision == SourceReadyDecision.STOP


def test_source_gate_wait_when_issues_present():
    issues = ArtifactRef(path="i.yaml", sha256="sha256:" + "c" * 64, schema="issues/v1")
    decision, ref = decide_source_ready(object(), issues)
    assert decision == SourceReadyDecision.WAIT_REVIEW
    assert ref is issues


def test_source_gate_continue_when_clean():
    decision, ref = decide_source_ready(object(), None)
    assert decision == SourceReadyDecision.CONTINUE
    assert ref is None


# --------------------------------------------------------------------------- #
# Boundary: application stages import no LangGraph / provider SDK
# --------------------------------------------------------------------------- #


def test_application_stages_do_not_import_langgraph_or_provider_sdk():
    import importlib
    import sys

    mods = [
        "scripts.question_transcription.workflow.application.stages.page_text",
        "scripts.question_transcription.workflow.application.stages.source",
        "scripts.question_transcription.workflow.application.stages.whole_paper",
    ]
    for mod in mods:
        importlib.import_module(mod)
    # After importing the stages, neither langgraph nor pydantic_ai should be loaded
    # purely because of them (they may be loaded by other test imports, so check the
    # stage modules' own declared imports instead).
    import ast
    import inspect

    forbidden_roots = {"langgraph", "pydantic_ai", "httpx", "scripts.infrastructure"}
    for mod in mods:
        module = sys.modules[mod]
        tree = ast.parse(inspect.getsource(module))
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    roots.add(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    roots.add(node.module.split(".")[0])
        leak = roots & forbidden_roots
        assert not leak, f"{mod} imports forbidden layer: {leak}"
