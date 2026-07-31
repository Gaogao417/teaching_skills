"""Workflow domain contracts — small, serializable lifecycle types and artifact refs.

These types mirror the F# declarations in
``docs/question-ingestion-langgraph-design.md`` §5 and
``docs/question-ingestion-langgraph-ports-design.md`` §2. They are the cross-cutting
domain vocabulary shared by :mod:`.state`, :mod:`.ports`, :mod:`.nodes` and
:mod:`.adapters`.

INVARIANT (design §16.13): these types never carry a provider/host choice. Only
:mod:`.config` (``RuntimeAdapterConfig``) and :mod:`.composition` may reference
``UseQwen / UseMimo / UseOpenCode / UseClaudeCode / UseApi``; ``WorkflowState``, graph
nodes and subgraphs must not import :mod:`.config` and must not branch on adapter type.

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

# Re-export the authoritative schemas so node/adapter code has a single import path.
# (Importing here does not couple state to provider choice — these are pure data
# contracts shared by every adapter, fake or real.)
from scripts.question_transcription.contracts import (  # noqa: F401  (re-export)
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)
from scripts.question_transcription.review_issue_contracts import (  # noqa: F401
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
)
from scripts.question_transcription.source_contracts import (  # noqa: F401
    SourcePaper,
)

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
    # Re-exported authoritative schemas:
    "SourcePaper",
    "QuestionTranscriptionBundle",
    "ImageAttributionBundle",
    "ReviewIssuesBundle",
    "ReviewResolutionsBundle",
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


class ArtifactRef(_Strict):
    """A path + sha256 + schema-name reference to a committed file artifact.

    The graph state only ever holds ``ArtifactRef`` to large objects (page images,
    page text, model responses, the full ``paper.source.yaml``); the bytes themselves
    never enter the checkpoint (design §16.2).

    The on-disk YAML key is ``schema`` (mirroring the existing
    ``source_contracts``/``contracts`` convention); the Python attribute is
    ``schema_`` to avoid shadowing the (deprecated) Pydantic v1 ``BaseModel.schema``
    method.
    """

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    schema_: str = Field(default=..., alias="schema", min_length=1)


SourceKind = Literal["doc", "docx", "pdf", "pages"]
"""Source kind discriminator. Routed purely by :mod:`.ports.source`."""


class SourceInput(_Strict):
    """Frozen description of the input to be ingested (design ports §2)."""

    paper_id: str = Field(min_length=1)
    source_kind: SourceKind
    source_path: str = Field(min_length=1)
    source_archive: str = Field(min_length=1)


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


ReviewStateKind = Literal[
    "no_review_pending",
    "waiting_for_source_review",
    "source_review_resolved",
    "waiting_for_final_review",
    "all_questions_approved",
]
"""Discriminator for the source-review / final-review lifecycle (design §5)."""


WorkflowOutcomeKind = Literal[
    "running",
    "waiting_for_source_review",
    "waiting_for_final_review",
    "completed",
    "failed",
]
"""The only values ``status``/``resume`` may return (design §12)."""
