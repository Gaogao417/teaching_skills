"""Whole-paper transcription port (architecture §3.4 and §7).

A bound ``WholePaperTranscriber`` reads the ordered per-page text files plus the
source manifest and produces a full :class:`QuestionTranscriptionBundle`
(questions, answers, solution steps) and optional review issues.

INVARIANT (ports §7.1): the port carries **no** ``Host`` property and **no**
``UseOpenCode / UseClaudeCode`` parameter. Business nodes can only call
``Transcribe`` / ``RepairStructuredOutput``; they cannot ask or match the host
type. The composition root (:mod:`..composition`) is the sole place that selects
the infrastructure ``Model`` (OpenCode/GLM-5.2 or Claude Code) and feeds it to the
single provider-neutral
:class:`~..adapters.whole_paper.structured_transcriber.StructuredWholePaperTranscriber`,
then wraps it with retry/cache/rate-limit decorators.
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

    The paper's layout (questions+solutions interleaved, or questions-first/
    answers-after) is not a request field: all ordered page text is fed to the
    transcriber in one stream and the agent judges the layout itself.
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
