"""Page-text nodes: dispatch (fan-out), single-page extract, barrier (ports §6).

- :func:`plan_page_text_extraction` reads the frozen source manifest and emits one
  LangGraph :class:`Send` per page (design §8.1).
- :func:`extract_page_text` calls the bound :class:`PageTextExtractor`, verifies the
  non-blank post-condition, commits ``page-NNN.txt`` + sidecar, returns one
  :class:`PageTextExtract` (ports §5.2).
- :func:`page_barrier` enforces exact coverage: no missing, no duplicate, no failure;
  only ``ReadyForWholePaperTranscription`` proceeds (ports §6.4).
"""

from __future__ import annotations

from typing import Any

from langgraph.types import Send

from ..application.stages.page_text import PageBarrierDecision, decide_page_barrier
from ..contracts import (
    ArtifactRef,
    ExecutionProvenance,
    PageTextArtifact,
    PageTextExtract,
    PageTextJob,
)
from ..orchestration.langgraph.state import WorkflowState
from ..tracing import trace_event


__all__ = [
    "PageBarrierDecision",
    "decide_page_barrier",
    "plan_page_text_dispatch",
    "make_extract_page_text_node",
    "page_barrier",
]


# --------------------------------------------------------------------------- #
# Dispatch (fan-out)
# --------------------------------------------------------------------------- #


def plan_page_text_dispatch(state: WorkflowState) -> list[Send]:
    """Routing function for the source->text fan-out edge.

    Reads frozen ``page_text_jobs`` and returns one :class:`Send` per page (plus we
    also start the image branch from a separate edge). LangGraph consumes the
    returned ``Send`` list and spawns parallel ``extract_page_text`` invocations
    (design §8.1). State values are plain dicts after serialization; re-validate.

    This is a *routing function* (passed to ``add_conditional_edges``), not a node —
    LangGraph fan-out requires ``Send`` objects to come from the edge router, not
    from node state output.

    Returns an empty list (no Sends) when upstream already set ``terminal_errors``
    or when there are no pages, so a failed source extraction never schedules
    dead ``extract_page_text`` work.
    """

    # On upstream failure (extract_source set terminal_errors) or a degenerate
    # empty page set, do not fan out: emit zero Sends. The graph already carries
    # the terminal errors and the parallel image branch reaches END on its own,
    # so the run resolves to failed instead of scheduling N dead page extracts.
    if state.get("terminal_errors"):
        return []
    raw_jobs = list(state.get("page_text_jobs") or [])
    jobs = [
        PageTextJob.model_validate(j if isinstance(j, dict) else j.model_dump())
        for j in raw_jobs
    ]
    if not jobs:
        return []
    jobs = sorted(jobs, key=lambda j: j.page_number)
    return [Send("extract_page_text", {"job": j.model_dump(mode="json")}) for j in jobs]


# --------------------------------------------------------------------------- #
# Single-page extract
# --------------------------------------------------------------------------- #


def make_extract_page_text_node(deps):
    """Build the per-page node bound to ``deps.page_text_extractor``.

    The node function is invoked by LangGraph once per ``Send``; it receives a dict
    with the serialized :class:`PageTextJob`. It commits the text + sidecar and
    appends a :class:`PageTextExtract` to state via the reducer.
    """

    extractor = deps.page_text_extractor
    store = deps.artifact_store
    layout = deps.run_layout

    def extract_page_text(payload: dict) -> dict[str, Any]:
        job = PageTextJob.model_validate(payload["job"])
        with trace_event(
            "extract_page_text",
            page_number=job.page_number,
            input_fingerprint=job.input_fingerprint,
        ):
            extract, failure = extractor.extract(job)
        if failure is not None:
            return {
                "page_text_failures": [
                    f"page {job.page_number}: {failure.kind} ({failure.detail})"
                ]
            }
        if extract is None:
            return {
                "page_text_failures": [f"page {job.page_number}: no extract returned"]
            }
        # Post-condition (ports §2.1): non-blank text.
        text = store.read_text(extract.artifact.text)
        if not text.strip():
            return {
                "page_text_failures": [
                    f"page {job.page_number}: blank text (contract failure)"
                ]
            }
        return {"page_text_extracts": [extract.model_dump(mode="json")]}

    return extract_page_text


# --------------------------------------------------------------------------- #
# Barrier
# --------------------------------------------------------------------------- #


def page_barrier(state: WorkflowState) -> dict[str, Any]:
    """Evaluate the barrier and route (called as a graph node before transcribe).

    On STOP we surface terminal errors; on WAIT we stay (more Sends are in flight);
    on READY we fall through to the whole-paper node via the graph edge.
    """

    jobs_raw = list(state.get("page_text_jobs") or [])
    jobs = [
        PageTextJob.model_validate(j if isinstance(j, dict) else j.model_dump())
        for j in jobs_raw
    ]
    expected = sorted(j.page_number for j in jobs)
    extracts_raw = list(state.get("page_text_extracts") or [])
    completed = [PageTextExtract.model_validate(e) for e in extracts_raw]
    failures = list(state.get("page_text_failures") or [])

    decision, detail = decide_page_barrier(expected, completed, failures)
    if decision == PageBarrierDecision.STOP_FAILURES:
        return {"terminal_errors": [f"page extraction failed: {failures}"]}
    if decision == PageBarrierDecision.STOP_COVERAGE:
        return {"terminal_errors": [f"page coverage violation: {detail}"]}
    # READY or WAIT — READY proceeds via the graph edge; WAIT is a no-op until more
    # extracts land. We do not transcribe here; the edge condition does the routing.
    return {}
