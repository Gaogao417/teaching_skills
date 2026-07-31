"""Downstream deterministic ports (ports-design §10).

These stages wrap the existing deterministic scripts (projector / evidence /
expand / materialize / audit / notify). They run strictly serially — each depends
on the previous stage's actual files, so they are not parallelised in the graph
(design §12).

Adapter implementations import the existing Python functions directly
(``project_source_to_draft`` / ``expand_draft`` / ``materialize_item`` /
``audit_staging`` / ``notify_catalog_version``) rather than shelling out, except
where no stable function entry exists.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from ..contracts import ArtifactRef, SourceKind


__all__ = [
    "StageFailure",
    "DraftProjector",
    "EvidenceCompleter",
    "StagingExpander",
    "AssetMaterializer",
    "StagingAuditor",
    "CatalogNotifier",
]


StageFailure = Literal[
    "project_failed",
    "evidence_failed",
    "expand_failed",
    "materialize_failed",
    "audit_failed",
    "notify_failed",
    "subprocess_failed",
    "io_failed",
    "validation_failed",
]


class _StageFailureDetail(Protocol):
    """Structured failure detail returned alongside a ``StageFailure`` kind."""

    @property
    def stage(self) -> str: ...

    @property
    def exit_code(self) -> int | None: ...

    @property
    def retryable(self) -> bool: ...

    @property
    def report(self) -> ArtifactRef | None: ...

    @property
    def detail(self) -> str: ...


@runtime_checkable
class DraftProjector(Protocol):
    """Project the authoritative source paper to the v1-compatible draft."""

    def project(
        self, source_paper_ref: ArtifactRef
    ) -> "tuple[ArtifactRef | None, StageFailure | None, str | None]": ...


@runtime_checkable
class EvidenceCompleter(Protocol):
    """Complete/verify per-question stem and official-solution evidence pages."""

    def complete(
        self, draft_ref: ArtifactRef, source_kind: SourceKind
    ) -> "tuple[ArtifactRef | None, StageFailure | None, str | None]": ...


@runtime_checkable
class StagingExpander(Protocol):
    """Expand the draft into per-question staging directories."""

    def expand(
        self, draft_ref: ArtifactRef
    ) -> "tuple[str | None, StageFailure | None, str | None]":
        """Returns ``(staging_directory, None, None)`` on success."""


@runtime_checkable
class AssetMaterializer(Protocol):
    """Crop images, refresh hashes, derive student/teacher assignments."""

    def materialize(
        self, staging_directory: str
    ) -> "tuple[ArtifactRef | None, StageFailure | None, str | None]": ...


@runtime_checkable
class StagingAuditor(Protocol):
    """Audit staging for schema/files/images/answer-isolation/review sidecars."""

    def audit(
        self, staging_directory: str, require_approved_review: bool
    ) -> "tuple[ArtifactRef | None, StageFailure | None, str | None]": ...


@runtime_checkable
class CatalogNotifier(Protocol):
    """Bump ``.catalog-version`` so the Review UI rebuilds its read model."""

    def refresh(
        self, staging_directory: str
    ) -> "tuple[None, StageFailure | None, str | None]": ...
