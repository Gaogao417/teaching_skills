"""Downstream staging nodes (ports-design §10): the serial deterministic pipeline.

project -> evidence -> expand -> materialize -> audit (structural) -> notify.

Each stage depends on the previous stage's actual files, so they are strictly serial
(design §12). Failures stop the pipeline and surface terminal errors with the stage
report (ports §10).
"""

from __future__ import annotations

from typing import Any

from ..contracts import ArtifactRef
from ..state import WorkflowState
from ..tracing import trace_event


__all__ = [
    "make_build_draft_node",
    "make_complete_evidence_node",
    "make_split_into_questions_node",
    "make_build_assets_node",
    "make_audit_staging_node",
    "make_refresh_review_ui_node",
]


def _ref(value) -> ArtifactRef | None:
    if value is None:
        return None
    if isinstance(value, ArtifactRef):
        return value
    return ArtifactRef.model_validate(value)


def make_build_draft_node(deps):
    projector = deps.deterministic.draft_projector

    def build_draft(state: WorkflowState) -> dict[str, Any]:
        source_ref = _ref(state.get("source_paper"))
        if source_ref is None:
            return {"terminal_errors": ["build_draft: source paper missing"]}
        with trace_event("build_compatible_draft"):
            draft_ref, failure, detail = projector.project(source_ref)
        if failure is not None:
            return {"terminal_errors": [f"build_draft: {failure}: {detail}"]}
        return {"draft": draft_ref.model_dump(mode="json") if hasattr(draft_ref, "model_dump") else draft_ref}

    return build_draft


def make_complete_evidence_node(deps):
    completer = deps.deterministic.evidence_completer

    def complete_evidence(state: WorkflowState) -> dict[str, Any]:
        draft_ref = _ref(state.get("draft"))
        if draft_ref is None:
            return {"terminal_errors": ["complete_evidence: draft missing"]}
        with trace_event("complete_source_evidence"):
            completed_ref, failure, detail = completer.complete(
                draft_ref, state["source_kind"]
            )
        if failure is not None:
            return {"terminal_errors": [f"complete_evidence: {failure}: {detail}"]}
        return {"draft": completed_ref.model_dump(mode="json") if hasattr(completed_ref, "model_dump") else completed_ref}

    return complete_evidence


def make_split_into_questions_node(deps):
    expander = deps.deterministic.staging_expander

    def split_into_questions(state: WorkflowState) -> dict[str, Any]:
        draft_ref = _ref(state.get("draft"))
        if draft_ref is None:
            return {"terminal_errors": ["split: draft missing"]}
        with trace_event("split_paper_into_questions"):
            staging_dir, failure, detail = expander.expand(draft_ref)
        if failure is not None:
            return {"terminal_errors": [f"split: {failure}: {detail}"]}
        return {"staging_directory": staging_dir}

    return split_into_questions


def make_build_assets_node(deps):
    materializer = deps.deterministic.asset_materializer

    def build_assets(state: WorkflowState) -> dict[str, Any]:
        staging = state.get("staging_directory")
        if staging is None:
            return {"terminal_errors": ["build_assets: staging directory missing"]}
        with trace_event("build_question_assets"):
            _, failure, detail = materializer.materialize(staging)
        if failure is not None:
            return {"terminal_errors": [f"build_assets: {failure}: {detail}"]}
        return {}

    return build_assets


def make_audit_staging_node(deps):
    auditor = deps.deterministic.staging_auditor

    def audit_staging(state: WorkflowState) -> dict[str, Any]:
        staging = state.get("staging_directory")
        if staging is None:
            return {"terminal_errors": ["audit: staging directory missing"]}
        with trace_event("validate_generated_staging"):
            _, failure, detail = auditor.audit(staging, require_approved_review=False)
        if failure is not None:
            return {"terminal_errors": [f"audit: {failure}: {detail}"]}
        return {}

    return audit_staging


def make_refresh_review_ui_node(deps):
    notifier = deps.deterministic.catalog_notifier

    def refresh_review_ui(state: WorkflowState) -> dict[str, Any]:
        staging = state.get("staging_directory")
        if staging is None:
            return {"terminal_errors": ["notify: staging directory missing"]}
        with trace_event("refresh_review_ui"):
            _, failure, detail = notifier.refresh(staging)
        if failure is not None:
            return {"terminal_errors": [f"notify: {failure}: {detail}"]}
        return {"review_state": "waiting_for_final_review"}

    return refresh_review_ui
