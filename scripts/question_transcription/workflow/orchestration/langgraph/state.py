"""LangGraph graph state contract (architecture §3.5, §5).

``WorkflowState`` holds only small, serializable lifecycle state and artifact
references — never page-image bytes, the full PDF, full model responses, or the
whole ``paper.source.yaml`` content (design §6). It also never carries an
adapter/provider choice (design §12.7).

LangGraph drives the graph from a ``TypedDict`` whose fields are annotated with
reducer functions (in :mod:`.reducers`). The same fields are mirrored on a Pydantic
``WorkflowStateModel`` so we can round-trip the state through JSON for snapshot tests
and run manifests. The TypedDict is the runtime graph schema; the Pydantic model is
the serializable projection.
"""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from ...contracts import (
    ArtifactRef,
    PageTextExtract,
    PageTextJob,
    ReviewStateKind,
    SourceKind,
    WorkflowOutcomeKind,
)
from ... import GRAPH_VERSION
from .reducers import (
    PageTextExtractsReducer,
    PageTextFailuresReducer,
    add_page_failure,
)


__all__ = [
    "WorkflowState",
    "WorkflowStateModel",
    "initial_state",
    "dump_state",
    "load_state",
    "extract_outcome",
]


# --------------------------------------------------------------------------- #
# Graph state (TypedDict used by StateGraph)
# --------------------------------------------------------------------------- #


class WorkflowState(TypedDict, total=False):
    """LangGraph state schema (design §5).

    All ``ArtifactRef``-typed fields are optional until the corresponding node has
    committed its artifact. ``run_id`` / ``paper_id`` / ``graph_version`` /
    ``source_kind`` / ``source_archive`` are set at ``start`` and never changed.
    """

    run_id: str
    paper_id: str
    graph_version: str
    source_kind: SourceKind
    source_archive: str

    extracted_source: Optional[ArtifactRef]
    page_text_jobs: list[PageTextJob]

    page_text_extracts: Annotated[list[PageTextExtract], PageTextExtractsReducer()]
    page_text_failures: Annotated[list[str], PageTextFailuresReducer()]

    whole_paper_transcription: Optional[ArtifactRef]
    image_attribution: Optional[ArtifactRef]
    source_paper: Optional[ArtifactRef]
    draft: Optional[ArtifactRef]
    staging_directory: Optional[str]

    review_state: ReviewStateKind
    terminal_errors: Annotated[list[str], add_page_failure]

    # Provider provenance recorded ONCE in the run manifest (not in nodes that
    # route). Kept on state purely so the run-manifest writer can read it without a
    # second channel; nodes must not read these to decide routing.
    page_adapter_provenance: Optional[dict]
    whole_paper_adapter_provenance: Optional[dict]


def initial_state(
    *,
    run_id: str,
    paper_id: str,
    source_kind: SourceKind,
    source_archive: str,
) -> WorkflowState:
    """Construct the blank state a fresh run starts from."""

    return WorkflowState(
        run_id=run_id,
        paper_id=paper_id,
        graph_version=GRAPH_VERSION,
        source_kind=source_kind,
        source_archive=source_archive,
        extracted_source=None,
        page_text_jobs=[],
        page_text_extracts=[],
        page_text_failures=[],
        whole_paper_transcription=None,
        image_attribution=None,
        source_paper=None,
        draft=None,
        staging_directory=None,
        review_state="no_review_pending",
        terminal_errors=[],
        page_adapter_provenance=None,
        whole_paper_adapter_provenance=None,
    )


# --------------------------------------------------------------------------- #
# Serializable Pydantic projection (round-trip for snapshots / manifests)
# --------------------------------------------------------------------------- #

from pydantic import BaseModel, ConfigDict, Field, field_validator  # noqa: E402


class WorkflowStateModel(BaseModel):
    """Pydantic projection of :class:`WorkflowState` for serialization/tests.

    Round-trips with :func:`dump_state` / :func:`load_state`. It intentionally mirrors
    the TypedDict fields rather than wrapping arbitrary dicts, so a field added to
    the graph state is caught here at compile time.

    The page-text-extract collection is normalized to page-number order here too,
    so snapshots/manifests are byte-stable regardless of fan-out completion order
    (design §5.1 / §6) — the graph reducer and this validator agree.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    paper_id: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    source_kind: SourceKind
    source_archive: str = Field(min_length=1)

    extracted_source: Optional[ArtifactRef] = None
    page_text_jobs: list[PageTextJob] = []
    page_text_extracts: list[PageTextExtract] = []
    page_text_failures: list[str] = []
    whole_paper_transcription: Optional[ArtifactRef] = None
    image_attribution: Optional[ArtifactRef] = None
    source_paper: Optional[ArtifactRef] = None
    draft: Optional[ArtifactRef] = None
    staging_directory: Optional[str] = None

    review_state: ReviewStateKind = "no_review_pending"
    terminal_errors: list[str] = []

    page_adapter_provenance: Optional[dict] = None
    whole_paper_adapter_provenance: Optional[dict] = None

    @field_validator("page_text_extracts")
    @classmethod
    def _sort_extracts(cls, value: list[PageTextExtract]) -> list[PageTextExtract]:
        # Deterministic normalization mirroring the graph reducer (add_page_extract).
        return sorted(value, key=lambda x: x.artifact.page_number)


def dump_state(state: WorkflowState) -> dict:
    """Validate-then-dump a graph state to a JSON-ready dict (round-trip safe)."""

    return WorkflowStateModel.model_validate(dict(state)).model_dump(mode="json")


def load_state(data: dict) -> WorkflowState:
    """Inverse of :func:`dump_state` — returns a runtime graph state."""

    validated = WorkflowStateModel.model_validate(data)
    return WorkflowState(**validated.model_dump(mode="json"))


def extract_outcome(state: WorkflowState) -> WorkflowOutcomeKind:
    """Map a graph state to the public CLI outcome enum (architecture §10).

    This is a pure projection used by ``status``/``resume``; it never mutates state.
    Routing decisions inside the graph are made by the nodes, not by this function.
    """

    errors = list(state.get("terminal_errors") or [])
    if errors:
        return "failed"
    review = state.get("review_state", "no_review_pending")
    if review == "waiting_for_source_review":
        return "waiting_for_source_review"
    if review == "waiting_for_final_review":
        return "waiting_for_final_review"
    if review == "all_questions_approved" and state.get("staging_directory"):
        return "completed"
    return "running"
