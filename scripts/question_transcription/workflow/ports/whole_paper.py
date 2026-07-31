"""Whole-paper transcription port (architecture §3.4 and §7).

A bound ``WholePaperTranscriber`` reads the ordered per-page text files plus the
source manifest and produces a full :class:`QuestionTranscriptionBundle`
(questions, answers, solution steps) and optional review issues.

INVARIANT (ports §7.1): the port carries **no** ``Host`` property and **no**
``UseOpenCode / UseClaudeCode`` parameter. Business nodes can only call
``Transcribe`` / ``RepairStructuredOutput``; they cannot ask or match the host
type. The composition root (:mod:`..composition`) is the sole place that selects
the concrete adapter (currently OpenCode/GLM-5.2 or Claude Code) and wraps
it with retry/cache/rate-limit decorators.

Real adapters:

- :class:`~..adapters.whole_paper.opencode.OpencodeGlmTranscriber` -> OpenCode glm-5.2
- :class:`~..adapters.whole_paper.claude_code.ClaudeCodeTranscriber` -> Claude Code

Both implement this same contract.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..contracts import (
    ArtifactRef,
    PageTextExtract,
    WholePaperFailure,
    WholePaperTranscription,
)


__all__ = ["AgentWorkspace", "WholePaperRequest", "WholePaperTranscriber"]


class AgentWorkspace(Protocol):
    """Read-only working directory contract handed to a coding-agent adapter.

    Current coding-agent adapters receive these paths so the model can read the
    page text files and write the output artifact.
    """

    @property
    def root(self) -> str: ...

    @property
    def readable_artifacts(self) -> list[ArtifactRef]: ...

    @property
    def writable_output_directory(self) -> str: ...


class WholePaperRequest(Protocol):
    """Input to :meth:`WholePaperTranscriber.transcribe`.

    ``ordered_page_texts`` MUST be sorted by page number; the node enforces exact
    coverage before calling the port (ports §6.4). ``idempotency_key`` is the
    cache key seed (ordered page-text sha256 + manifest sha + adapter/version).

    For a **separated** paper (题卷/答案分文件, architecture §7.4), ``solution_page_texts``
    carries the answer/solution pages and ``ordered_page_texts`` carries the
    question-only pages; the adapter then uses the separated prompt layout. When
    ``solution_page_texts`` is empty/None the paper is interleaved and
    ``ordered_page_texts`` covers the whole paper.
    """

    @property
    def run_id(self) -> str: ...

    @property
    def paper_id(self) -> str: ...

    @property
    def workspace(self) -> AgentWorkspace: ...

    @property
    def ordered_page_texts(self) -> list[PageTextExtract]: ...

    @property
    def source_manifest(self) -> ArtifactRef: ...

    @property
    def paper_metadata(self) -> ArtifactRef: ...

    @property
    def prompt_version(self) -> str: ...

    @property
    def output_schema(self) -> ArtifactRef: ...

    @property
    def idempotency_key(self) -> str: ...

    @property
    def solution_page_texts(self) -> list[PageTextExtract]:
        """Solution/answer pages for a separated paper (empty for interleaved)."""
        ...

    @property
    def prompt_mode(self) -> str:
        """``"interleaved"`` (default) or ``"separated"``."""
        ...


@runtime_checkable
class WholePaperTranscriber(Protocol):
    """Transcribe the whole paper from ordered page text into structured output."""

    def transcribe(
        self, request: WholePaperRequest
    ) -> "tuple[WholePaperTranscription | None, WholePaperFailure | None]":
        """Transcribe ``request``.

        Returns ``(transcription, None)`` on success or ``(None, failure)`` after
        the bound retry decorator is exhausted. The adapter must NOT read page
        images, NOT guess Word/PDF media attribution, and NOT write staging — it
        only produces the structured transcription + optional issues.
        """

    def repair_structured_output(
        self,
        previous_execution_id: str,
        validation_errors: list[str],
    ) -> "tuple[WholePaperTranscription | None, WholePaperFailure | None]":
        """Ask the same bound adapter/session to repair invalid structured output.

        This is a node-visible business action (triggered by output-contract
        validation), distinct from invisible transport retry. Reuses the same
        adapter instance — no host switch.
        """
