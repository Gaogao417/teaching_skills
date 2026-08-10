"""Unit tests for the pure graph-edge routing functions (architecture §3.5, M4).

Routing branches on business state only (terminal errors, review state), never on
adapter/host type. These tests compile no graph — they assert each router's decision
matrix directly, including the load-bearing review-gate semantics.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.graph import END

from scripts.question_transcription.workflow.orchestration.langgraph.routing import (
    has_errors,
    route_after_audit_staging,
    route_after_build_source,
    route_after_final_review,
    route_after_page_barrier,
)


def _state(**kw) -> dict:
    base = {"terminal_errors": [], "review_state": "no_review_pending"}
    base.update(kw)
    return base


def test_has_errors_detects_terminal_errors():
    assert has_errors(_state()) is False
    assert has_errors(_state(terminal_errors=["boom"])) is True


def test_page_barrier_routes_to_transcribe_or_end():
    assert route_after_page_barrier(_state()) == "transcribe_whole_paper"
    assert route_after_page_barrier(_state(terminal_errors=["x"])) == END


def test_build_source_routes_clean_review_and_error():
    assert route_after_build_source(_state()) == "build_draft"
    assert (
        route_after_build_source(_state(review_state="waiting_for_source_review"))
        == "source_review_wait"
    )
    assert route_after_build_source(_state(terminal_errors=["x"])) == END


def test_audit_routes_to_refresh_or_end():
    assert route_after_audit_staging(_state()) == "refresh_review_ui"
    assert route_after_audit_staging(_state(terminal_errors=["x"])) == END


def test_final_review_only_approved_reaches_approved_audit():
    # approved -> approved_audit; still-pending loops back into final_review_check so its
    # next execution re-interrupts; everything else (no review state, errors) ends.
    assert route_after_final_review(_state(review_state="all_questions_approved")) == "approved_audit"
    assert (
        route_after_final_review(_state(review_state="waiting_for_final_review"))
        == "final_review_check"
    )
    assert route_after_final_review(_state(review_state="no_review_pending")) == END
    assert route_after_final_review(_state(terminal_errors=["x"])) == END


def test_routing_never_branches_on_provider_choice():
    """Routing reads only business state — it has no adapter/host discriminator."""

    import inspect

    from scripts.question_transcription.workflow.orchestration.langgraph import routing

    forbidden = {"UseOpenCode", "UseClaudeCode", "UseApi", "Host", "opencode", "claude"}
    source = inspect.getsource(routing)
    # 'opencode'/'claude' may appear only inside string literals that are not host
    # choices; assert none of the choice tokens appear as identifiers.
    import ast

    tree = ast.parse(source)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    leak = names & {"UseOpenCode", "UseClaudeCode", "UseApi", "Host"}
    assert not leak, f"routing names a provider-choice token: {leak}"
