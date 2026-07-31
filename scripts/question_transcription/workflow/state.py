"""Workflow graph state contract (design §5).

``WorkflowState`` holds only small, serializable lifecycle state and artifact
references — never page-image bytes, the full PDF, full model responses, or the
whole ``paper.source.yaml`` content (design §16.2). It also never carries an
adapter/provider choice (design §16.13).

LangGraph drives the graph from a ``TypedDict`` whose fields are annotated with
reducer functions. The same fields are mirrored on a Pydantic ``WorkflowStateModel``
so we can round-trip the state through JSON for snapshot tests and run manifests.
The TypedDict is the runtime graph schema; the Pydantic model is the serializable
projection.

Reducer rules (design §5.1):

- ``page_text_extracts`` uses :func:`add_page_extract`, which sorts by page number,
  de-duplicates by page number (last writer wins is forbidden — a duplicate is a
  coverage violation caught by the barrier), and is order-independent.
- Optional singletons (``extracted_source``, ``whole_paper_transcription`` …) use a
  ``last_value``-style reducer that replaces the previous value.
- ``terminal_errors`` appends.
"""

from __future__ import annotations

from typing import Annotated, Optional, TypedDict

from .contracts import (
    ArtifactRef,
    PageTextExtract,
    PageTextJob,
    ReviewStateKind,
    SourceKind,
    WorkflowOutcomeKind,
)
from . import GRAPH_VERSION


__all__ = [
    "PageTextExtractsReducer",
    "add_page_extract",
    "PageTextFailuresReducer",
    "add_page_failure",
    "WorkflowState",
    "WorkflowStateModel",
    "extract_outcome",
]


# --------------------------------------------------------------------------- #
# Reducers
# --------------------------------------------------------------------------- #


def add_page_extract(
    left: list[PageTextExtract], right: Optional[list[PageTextExtract] | PageTextExtract]
) -> list[PageTextExtract]:
    """Order-independent page-extract reducer (design §5.1).

    Merge incoming extracts with the accumulated list, keyed by page number. The
    barrier node (:mod:`.nodes.page_text`) is responsible for the *exact-coverage*
    post-condition (no missing, no duplicate, no failure) — this reducer only keeps
    the collection deterministic across arbitrary fan-out completion orders.

    Inputs may be plain dicts (node outputs and checkpoint state are JSON-dumped);
    we re-validate each into :class:`PageTextExtract` here.
    """

    def _coerce(x) -> PageTextExtract:
        if isinstance(x, PageTextExtract):
            return x
        return PageTextExtract.model_validate(x)

    if right is None:
        return [_coerce(x) for x in left]
    incoming_raw = right if isinstance(right, list) else [right]
    incoming = [_coerce(x) for x in incoming_raw]
    merged: dict[int, PageTextExtract] = {
        _coerce(x).artifact.page_number: _coerce(x) for x in left
    }
    for extract in incoming:
        # Note: a duplicate page_number OVERWRITES here only so the reducer stays
        # total; the barrier treats any duplicate as a coverage violation and
        # refuses to proceed. We do not silently accept two extracts for one page.
        merged[extract.artifact.page_number] = extract
    return [merged[n] for n in sorted(merged)]


class PageTextExtractsReducer:
    """Callable wrapper for :func:`add_page_extract` (LangGraph annotation helper)."""

    def __call__(
        self,
        left: list[PageTextExtract],
        right: Optional[list[PageTextExtract] | PageTextExtract],
    ) -> list[PageTextExtract]:
        return add_page_extract(left, right)


def add_page_failure(
    left: list[str], right: Optional[list[str] | str]
) -> list[str]:
    """Append-only reducer for page-level failure descriptors."""

    if right is None:
        return list(left)
    incoming = right if isinstance(right, list) else [right]
    return [*left, *incoming]


class PageTextFailuresReducer:
    def __call__(self, left: list[str], right: Optional[list[str] | str]) -> list[str]:
        return add_page_failure(left, right)


def _replace(left, right):
    return right if right is not None else left


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
    (design §5.1 / §16.3) — the graph reducer and this validator agree.
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
    """Map a graph state to the public CLI outcome enum (design §12).

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
