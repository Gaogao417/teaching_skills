"""Source application stage helpers (architecture §3.4, M4).

Pure, framework-agnostic source-ready gate decision. The LangGraph node wrapper calls
:func:`decide_source_ready` after building the authoritative source paper.
"""

from __future__ import annotations

from ...contracts import ArtifactRef, SourceBuildResult


__all__ = ["SourceReadyDecision", "decide_source_ready"]


class SourceReadyDecision:
    CONTINUE = "continue_to_draft"
    WAIT_REVIEW = "wait_for_source_review"
    STOP = "stop_source_build"


def decide_source_ready(
    build_result: SourceBuildResult | None, issues_ref: ArtifactRef | None
) -> "tuple[str, ArtifactRef | None]":
    """Pure source-ready gate decision (ports §9).

    - no build result → ``STOP``;
    - blocking issues present → ``WAIT_REVIEW`` with the issues ref;
    - otherwise → ``CONTINUE``.
    """

    if build_result is None:
        return SourceReadyDecision.STOP, None
    if issues_ref is not None:
        return SourceReadyDecision.WAIT_REVIEW, issues_ref
    return SourceReadyDecision.CONTINUE, None
