"""Claude Code whole-paper transcriber — port stub for this milestone.

Implements :class:`WholePaperTranscriber` but is not wired to the live Claude Code
runner yet (design §11 freeze: Claude Code non-interactive exec protocol + output
protocol undecided). Bound only when explicitly selected; returns
``routing_unverified`` until implemented.
"""

from __future__ import annotations

from .._common_paths import repo_root  # noqa: F401
from ...contracts import WholePaperFailure


ADAPTER_ID = "claude-code"


class ClaudeCodeTranscriber:
    """:class:`WholePaperTranscriber` stub (not yet implemented)."""

    def __init__(self, *, store, **_kwargs) -> None:
        self.store = store

    def transcribe(self, request):
        return None, WholePaperFailure(
            adapter_id=ADAPTER_ID,
            kind="routing_unverified",
            attempts=1,
            detail="Claude Code adapter is a port stub; use opencode or api",
        )

    def repair_structured_output(self, previous_execution_id, validation_errors):
        return None, WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="routing_unverified",
            attempts=1, execution_id=previous_execution_id,
            detail="Claude Code adapter is a port stub",
        )
