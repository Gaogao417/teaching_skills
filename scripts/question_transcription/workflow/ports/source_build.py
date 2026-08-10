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
    """Build the authoritative ``paper.source.yaml`` from transcription + images.

    ``extracted_source_ref`` is the source manifest (DOCX ``word-source.yaml`` or
    PDF detection). It is the ONLY source of vector-asset evidence
    (``ole_binding`` / ``emf_class`` / dimensions / PNG rendition availability):
    the v1 ``ImageAttributionBundle`` is a frozen compatibility contract that
    cannot carry these fields, so the builder MUST join the manifest to recover
    them. Passing ``None`` is allowed only for non-docx sources that have no
    manifest; the builder then projects a minimal v2 (the legacy path).
    """

    def build(
        self,
        transcription_ref: ArtifactRef,
        images_ref: ArtifactRef | None,
        extracted_source_ref: ArtifactRef | None,
        resolutions_ref: ArtifactRef | None,
    ) -> "tuple[SourceBuildResult | None, SourceBuildFailure | None, str | None]":
        """Build the source paper.

        Returns ``(result, None, None)`` on success. The caller (the
        ``CheckSourceReady`` decision) inspects ``result.issues`` for unresolved
        blocking issues to decide whether to continue to draft or interrupt for
        source review. On hard failure returns ``(None, failure, detail)``.
        """
