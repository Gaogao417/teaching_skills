"""Review nodes — the two human-in-the-loop interrupts (design §9, ports §11).

Source review (§9.1) and final review (§9.2) both use LangGraph ``interrupt``. Resume
only WAKES the graph — it never equals approval (design §16.8). On resume each node
re-reads the actual review artifact and re-validates; a boolean in the resume payload
cannot bypass the gate.

Final approval gates ``End``: ``RunApprovedAudit`` calls
``audit_staging --require-approved-review``; only its success reaches ``End``
(design §16.10).
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt

from ..orchestration.langgraph.state import WorkflowState
from ..tracing import trace_event


__all__ = [
    "make_source_review_wait_node",
    "make_final_review_check_node",
    "make_approved_audit_node",
]


def make_source_review_wait_node(deps):
    """Interrupt until a fresh ``review-resolutions.yaml`` is written and valid.

    On resume the ``build_source_paper`` node re-reads the resolution artifact and
    re-runs the gate (design §9.1); this node only pauses for the human.
    """

    def source_review_wait(state: WorkflowState) -> dict[str, Any]:
        issues_ref = state.get("source_paper")  # source paper carries the issues
        interrupt({"kind": "waiting_for_source_review", "run_id": state["run_id"]})
        # After resume, fall through to rebuild. Routing back to build_source_paper
        # is handled by the graph edge, not here.
        return {}

    return source_review_wait


def make_final_review_check_node(deps):
    """Read staging review state; interrupt when pending, stop when rejected."""

    reader = deps.deterministic.final_review_reader

    def final_review_check(state: WorkflowState) -> dict[str, Any]:
        staging = state.get("staging_directory")
        if staging is None:
            return {"terminal_errors": ["final_review: staging directory missing"]}
        with trace_event("check_all_questions_approved"):
            status, failure, detail, item_ids = reader.read_status(staging)
        if failure is not None:
            return {"terminal_errors": [f"final_review: {failure}: {detail}"]}
        if status == "rejected":
            return {
                "terminal_errors": [
                    f"final_review: rejected items {item_ids or []}"
                ]
            }
        if status == "pending":
            interrupt(
                {
                    "kind": "waiting_for_final_review",
                    "run_id": state["run_id"],
                    "pending": item_ids or [],
                }
            )
            # Resume reached: a Command(resume=...) woke the interrupt.  The wake value
            # is NOT an approval (design §16.8), so re-read the on-disk reviews and route
            # by what they actually say.  Still-pending -> self-loop back into this node
            # (which re-interrupts on the next execution); approved -> approved_audit.
            with trace_event("recheck_after_final_review_resume"):
                status2, failure2, detail2, item_ids2 = reader.read_status(staging)
            if failure2 is not None:
                return {"terminal_errors": [f"final_review: {failure2}: {detail2}"]}
            if status2 == "rejected":
                return {
                    "terminal_errors": [
                        f"final_review: rejected items {item_ids2 or []}"
                    ]
                }
            if status2 == "approved":
                return {"review_state": "all_questions_approved"}
            # still pending: re-interrupt by looping back (graph self-loop edge).
            return {"review_state": "waiting_for_final_review"}
        # status == "approved" -> proceed to approved audit (graph edge).
        return {"review_state": "all_questions_approved"}

    return final_review_check


def make_approved_audit_node(deps):
    """Run ``audit_staging --require-approved-review``; only its success gates End."""

    auditor = deps.deterministic.staging_auditor

    def approved_audit(state: WorkflowState) -> dict[str, Any]:
        staging = state.get("staging_directory")
        if staging is None:
            return {"terminal_errors": ["approved_audit: staging directory missing"]}
        with trace_event("validate_all_approved"):
            _, failure, detail = auditor.audit(staging, require_approved_review=True)
        if failure is not None:
            return {"terminal_errors": [f"approved_audit: {failure}: {detail}"]}
        # Reaching here means the approved audit returned 0 errors -> End.
        return {"review_state": "all_questions_approved"}

    return approved_audit
