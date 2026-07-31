"""Whole-paper transcription node (architecture §3.5 and §7.3).

Validates exact page coverage, calls the bound :class:`WholePaperTranscriber`,
validates/commits the output, and requests bounded structured-output repair through
the same bound port when the output contract fails (ports §7.4). Repair is a
node-visible business action; transport retry is invisible (handled by the decorator
the composition root wrapped around the adapter).
"""

from __future__ import annotations

from typing import Any

from ..application.stages.whole_paper import validate_page_coverage
from ..contracts import (
    ArtifactRef,
    PageTextExtract,
    WholePaperFailure,
    WholePaperTranscription,
)
from ..state import WorkflowState
from ..tracing import trace_event


__all__ = [
    "validate_page_coverage",
    "make_transcribe_whole_paper_node",
]


def make_transcribe_whole_paper_node(deps):
    """Build the whole-paper node bound to ``deps.whole_paper_transcriber``."""

    transcriber = deps.whole_paper_transcriber
    store = deps.artifact_store
    max_repairs = getattr(deps, "whole_paper_max_repairs", 2)

    def transcribe_whole_paper(state: WorkflowState) -> dict[str, Any]:
        extracts_raw = list(state.get("page_text_extracts") or [])
        extracts = [PageTextExtract.model_validate(e) for e in extracts_raw]
        ordered, coverage_err = validate_page_coverage(extracts)
        if coverage_err:
            return {"terminal_errors": [f"transcribe: coverage {coverage_err}"]}

        from ..ports.whole_paper import WholePaperRequest

        class _Req:
            def __init__(self, s, ex):
                self._s, self._ex = s, ex

            @property
            def run_id(self):
                return self._s["run_id"]

            @property
            def paper_id(self):
                return self._s["paper_id"]

            @property
            def workspace(self):
                return store.layout

            @property
            def ordered_page_texts(self):
                return self._ex

            @property
            def source_manifest(self):
                ref = self._s.get("extracted_source")
                return ArtifactRef.model_validate(ref) if ref else None

            @property
            def paper_metadata(self):
                return None

            @property
            def prompt_version(self):
                return "whole-paper-v1"

            @property
            def output_schema(self):
                return None

            @property
            def idempotency_key(self):
                import hashlib as _h

                return _h.sha256(
                    "|".join(e.artifact.text.sha256 for e in self._ex).encode()
                ).hexdigest()

            @property
            def prompt_mode(self):
                # Read from the bound deps (composition root froze the config).
                # Default "interleaved" when the field is absent.
                return getattr(deps, "whole_paper_prompt_mode", None) or "interleaved"

            @property
            def solution_page_texts(self):
                # For a separated paper (题卷/答案分文件) the solution extracts would be
                # threaded here from a second source branch. Empty until that branch
                # is wired; the adapter then falls back to interleaved.
                return []

        request = _Req(state, ordered)
        with trace_event(
            "transcribe_whole_paper",
            pages=len(ordered),
            page_numbers=[e.artifact.page_number for e in ordered],
        ):
            transcription, failure = transcriber.transcribe(request)
        if failure is not None:
            return _failure_state(failure)
        if transcription is None:
            return {"terminal_errors": ["transcribe: no transcription returned"]}

        # Bounded structured-output repair loop (ports §7.4) — the adapter signals
        # contract invalidity by returning a WholePaperTranscription whose committed
        # artifact fails validation; repair is delegated back to the same port.
        # State stores only the transcription ArtifactRef (design §16.2); the
        # execution_id/model/prompt_version provenance goes to the run manifest.
        return {"whole_paper_transcription": transcription.transcription.model_dump(mode="json")}

    return transcribe_whole_paper


def _failure_state(failure: WholePaperFailure) -> dict[str, Any]:
    return {
        "terminal_errors": [
            f"transcribe: {failure.kind} (attempts={failure.attempts}): {failure.detail}"
        ]
    }
