"""Workflow domain contracts — small, serializable lifecycle types and artifact refs.

These types are the current implementation of the lifecycle/artifact contracts in
``docs/question-ingestion-architecture.md`` §3.3 and §6. They are the cross-cutting
domain vocabulary shared by :mod:`.state`, :mod:`.ports`, :mod:`.nodes` and
:mod:`.adapters`.

INVARIANT (design §16.13): these types never carry a provider/host choice. Only
:mod:`.config` (``RuntimeAdapterConfig``) and :mod:`.composition` may reference
``UseQwen / UseMimo / UseOpenCode / UseClaudeCode``; ``WorkflowState``, graph
nodes and subgraphs must not import :mod:`.config` and must not branch on adapter type.

The domain-layer home for the stable lifecycle/artifact types is
:mod:`.domain` (``domain/lifecycle.py``, ``domain/artifacts.py``). This module
re-exports those so existing import paths keep working, and adds the request/result
wrapper types that sit closer to the ports.

Re-use rule: the authoritative Pydantic schemas — ``SourcePaper``
(``math_exam_source_paper/v2``), ``QuestionTranscriptionBundle`` /
``ImageAttributionBundle`` (v1), and ``ReviewIssuesBundle`` /
``ReviewResolutionsBundle`` — already live in
:mod:`scripts.question_transcription.{source_contracts,contracts,
review_issue_contracts}`. This module does **not** redefine them; it only adds the
thin lifecycle/artifact-reference layer that sits on top.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# Domain-layer home for the stable lifecycle/artifact types (architecture §3.3).
from .domain.artifacts import ArtifactRef  # noqa: F401  (canonical re-export)
from .domain.lifecycle import (  # noqa: F401  (canonical re-export)
    ReviewStateKind,
    WorkflowOutcomeKind,
)

# NOTE: the authoritative Pydantic schemas (SourcePaper, QuestionTranscriptionBundle,
# ImageAttributionBundle, ReviewIssuesBundle, ReviewResolutionsBundle) are NOT
# re-exported here — import them directly from
# scripts.question_transcription.{source_contracts,contracts,review_issue_contracts}.

__all__ = [
    "ArtifactRef",
    "SourceKind",
    "SourceInput",
    "ExtractedSource",
    "PageTextJob",
    "ExecutionProvenance",
    "PageTextFailureKind",
    "PageTextFailure",
    "PageTextArtifact",
    "PageTextExtract",
    "WholePaperFailureKind",
    "WholePaperFailure",
    "WholePaperTranscription",
    "ImageAttributionResult",
    "SourceBuildResult",
    "ReviewStateKind",
    "WorkflowOutcomeKind",
]


class _Strict(BaseModel):
    """Frozen base mirroring the existing contract modules.

    - ``extra="forbid"`` catches typo'd field names at the boundary.
    - ``populate_by_name=True`` lets code construct with either the Python attribute
      name (``schema_=...``) or the on-disk alias (``schema=...``).
    - ``serialize_by_alias=True`` makes ``model_dump()`` emit the on-disk alias
      (``schema``), so round-trips are byte-stable without per-call ``by_alias``.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


# ``ArtifactRef`` is now defined in ``.domain.artifacts``; the strict base there is the
# canonical one. ``_Strict`` is retained only as the base for the request/result types
# below that are not yet promoted to the domain layer.


SourceKind = Literal["doc", "docx", "pdf", "pages"]
"""Source kind discriminator. Routed purely by :mod:`.ports.source`."""


class SourceInput(_Strict):
    """Frozen description of the input to be ingested (design ports §2).

    ``answer_archive`` (optional, Phase 2) points at a supplementary official
    answer document whose rendered pages continue the paper's page numbering.
    Used when the exam archive itself carries questions only (e.g. the Minhang
    2020 docx) and the reference answers live in a separate original file.
    """

    paper_id: str = Field(min_length=1)
    source_kind: SourceKind
    source_path: str = Field(min_length=1)
    source_archive: str = Field(min_length=1)
    answer_archive: Optional[str] = None


class ExtractedSource(_Strict):
    """Result of :class:`.ports.source.SourceExtractor.Extract` (ports §2).

    ``manifest`` is the source manifest (DOCX ``word-source.yaml`` or PDF source
    manifest); ``pages`` are the rendered page-image refs; ``media_directory`` is the
    DOCX original-media directory (absent for PDF); ``source_sha256`` freezes the
    input fingerprint.
    """

    manifest: ArtifactRef
    pages: list[ArtifactRef] = Field(min_length=1)
    media_directory: Optional[str] = None
    source_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    non_question_pages: list[NonQuestionPageDecl] = Field(default_factory=list)
    page_plan: Optional[ArtifactRef] = None
    answer_source: Optional[str] = None
    answer_sha256: Optional[str] = None


class NonQuestionPageDecl(_Strict):
    """One explicitly claimed non-question page (fail-closed audit exemption).

    A page is only exempt from the whole-paper coverage invariant through this
    human-authored declaration, stored next to the original source files as
    ``non-question-pages.yaml`` and carried through extraction into the staging
    ``paper.yaml``. Roles mirror the docx skill's ``NON_QUESTION_ROLES``.
    """

    page_number: int = Field(ge=1)
    role: Literal[
        "cover", "instructions", "answer_only", "qr_code", "blank", "other"
    ]
    note: Optional[str] = None
    claimed_by: Optional[str] = None


class PageTextJob(_Strict):
    """One page-text extraction task dispatched via LangGraph ``Send`` (ports §2)."""

    run_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    image: ArtifactRef
    input_fingerprint: str = Field(min_length=1)


class ExecutionProvenance(_Strict):
    """Adapter identity folded into artifacts and cache keys (identity only —
    business nodes must not branch on these values; design §16.13)."""

    adapter_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


PageTextFailureKind = Literal[
    "authentication_failure",
    "rate_limited",
    "provider_unavailable",
    "request_timed_out",
    "invalid_response",
    "empty_text",
    "source_hash_mismatch",
    "cache_corrupt",
]
"""Discriminator for :class:`PageTextFailure` (ports §2)."""


class PageTextFailure(_Strict):
    """Structured page-text failure (ports §2)."""

    adapter_id: Optional[str] = None
    kind: PageTextFailureKind
    attempts: int = Field(ge=1)
    detail: str = Field(min_length=1)


class PageTextArtifact(_Strict):
    """One page's OCR-style text + sidecar (design §2.1 / §5)."""

    page_number: int = Field(ge=1)
    text: ArtifactRef
    metadata: ArtifactRef
    provenance: ExecutionProvenance


class PageTextExtract(_Strict):
    """Wrapper around :class:`PageTextArtifact` (design §5).

    INVARIANT (ports §2.1): ``text`` references a UTF-8 ``.txt`` whose content is only
    the page's visible words + LaTeX formulae. It must NOT contain ``question_ref``,
    question type, ``answer``, ``solution_steps``, image attribution, or
    ``SourceQuestion``. The barrier reducer rejects blank/whitespace-only text as a
    contract failure.
    """

    artifact: PageTextArtifact


WholePaperFailureKind = Literal[
    "page_coverage_invalid",
    "transcriber_unavailable",
    "execution_creation_failed",
    "routing_unverified",
    "execution_timed_out",
    "token_budget_exceeded",
    "invalid_structured_output",
    "output_artifact_missing",
    "permission_violation",
]
"""Discriminator for :class:`WholePaperFailure` (ports §7.1)."""


class WholePaperFailure(_Strict):
    """Structured whole-paper transcription failure (ports §7.1)."""

    adapter_id: Optional[str] = None
    kind: WholePaperFailureKind
    attempts: int = Field(ge=1)
    execution_id: Optional[str] = None
    detail: str = Field(min_length=1)


class WholePaperTranscription(_Strict):
    """Result of :class:`.ports.whole_paper.WholePaperTranscriber.Transcribe` (ports §2)."""

    transcription: ArtifactRef
    issues: Optional[ArtifactRef] = None
    execution_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class ImageAttributionResult(_Strict):
    """Result of the deterministic image-attribution branch (ports §2 / §8).

    ``structure_status == "failed"`` is not "no images on this paper": it means image
    attribution could not produce a usable bundle. The source join may then save the
    text transcription but must emit a blocking issue (ports §8).
    """

    bundle: Optional[ArtifactRef] = None
    issues: Optional[ArtifactRef] = None
    structure_status: str = Field(min_length=1)


class SourceBuildResult(_Strict):
    """Result of building the authoritative ``paper.source.yaml`` (ports §9)."""

    source_paper: ArtifactRef
    issues: Optional[ArtifactRef] = None


# ``ReviewStateKind`` and ``WorkflowOutcomeKind`` are defined in ``.domain.lifecycle``
# and re-exported at the top of this module.