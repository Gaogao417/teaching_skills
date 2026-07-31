"""Authoritative source-paper build port (architecture §3.4 and §5.2).

Joins the whole-paper transcription with the deterministic image attribution into
the authoritative ``paper.source.yaml`` (:class:`SourcePaper`,
``math_exam_source_paper/v2``), then runs the source review gate.

The gate (design §9.1) is deterministic: unresolved blocking issues interrupt the
graph for human source review; resume only wakes the graph and must re-read the
resolution artifact (it cannot be bypassed by a boolean).
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..contracts import ArtifactRef, SourceBuildResult


__all__ = ["SourceBuildFailure", "SourcePaperBuilder"]


SourceBuildFailure = Literal[
    "transcription_invalid",
    "image_bundle_invalid",
    "cross_reference_invalid",
    "resolution_invalid",
    "artifact_write_failed",
]


@runtime_checkable
class SourcePaperBuilder(Protocol):
    """Build the authoritative ``paper.source.yaml`` from transcription + images."""

    def build(
        self,
        transcription_ref: ArtifactRef,
        images_ref: ArtifactRef | None,
        resolutions_ref: ArtifactRef | None,
    ) -> "tuple[SourceBuildResult | None, SourceBuildFailure | None, str | None]":
        """Build the source paper.

        Returns ``(result, None, None)`` on success. The caller (the
        ``CheckSourceReady`` decision) inspects ``result.issues`` for unresolved
        blocking issues to decide whether to continue to draft or interrupt for
        source review. On hard failure returns ``(None, failure, detail)``.
        """
