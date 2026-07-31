"""Pure graph-edge routing functions (architecture §3.5).

These functions branch on *business state only* (terminal errors, review state) — never
on adapter/host type (design §12.7). They are the conditional-edge routers passed to
``add_conditional_edges``. Keeping them pure and isolated makes the topology easy to
test without compiling a graph.
"""

from __future__ import annotations

from langgraph.graph import END

from .state import WorkflowState


__all__ = [
    "has_errors",
    "route_after_page_barrier",
    "route_after_build_source",
    "route_after_audit_staging",
    "route_after_final_review",
]


def has_errors(state: WorkflowState) -> bool:
    return bool(state.get("terminal_errors"))


def route_after_page_barrier(state: WorkflowState) -> str:
    """barrier -> transcribe_whole_paper; on error END."""

    return END if has_errors(state) else "transcribe_whole_paper"


def route_after_build_source(state: WorkflowState) -> str:
    """clean -> build_draft; needs_review -> source_review_wait; error -> END."""

    if has_errors(state):
        return END
    if state.get("review_state") == "waiting_for_source_review":
        return "source_review_wait"
    return "build_draft"


def route_after_audit_staging(state: WorkflowState) -> str:
    """audit -> refresh_review_ui; on error END."""

    return END if has_errors(state) else "refresh_review_ui"


def route_after_final_review(state: WorkflowState) -> str:
    """approved -> approved_audit; else END (pending loops back, rejected/errors end)."""

    if state.get("review_state") == "all_questions_approved":
        return "approved_audit"
    return END
