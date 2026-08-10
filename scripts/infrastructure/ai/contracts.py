"""Provider-neutral AI model failure and structured-model boundary (architecture §3.2).

This module is the SOLE place that defines how shared infrastructure reports a model
call failure to its caller. It is deliberately provider- and domain-agnostic:

- It does NOT mention ``WholePaperFailure``, ``QuestionTranscriptionBundle`` or any
  question-ingestion type. Callers (e.g. the ingestion whole-paper transcriber) map
  :class:`ModelFailure` into their own domain failure.
- It does NOT select a provider or read an API key. Transport selection happens at
  bootstrap; the structured-model abstraction just receives a bound transport.

The ``ModelFailure`` kinds cover the cross-provider failure surface that a caller
needs to react to (retry at transport level, surface to the user, or treat as a
structured-output problem):

============  ==========================================================
Kind          Meaning
============  ==========================================================
authentication  the provider rejected credentials / no credential resolved
rate_limited    the provider returned a rate/quota limit response
unavailable     the provider endpoint could not be reached / 5xx
timed_out       the request exceeded its timeout
protocol        the provider answered but the response was unusable
============  ==========================================================

A PydanticAI ``Model.request()`` (see :mod:`.opencode.pydantic_model`,
:mod:`.claude_code.pydantic_model`) raises :class:`ModelFailureError` carrying a
:class:`ModelFailure` instead of a domain exception; the surrounding Agent / adapter
catches it and translates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


__all__ = [
    "ModelFailureKind",
    "ModelFailure",
    "ModelFailureError",
    "StructuredModelResponse",
]


ModelFailureKind = Literal[
    "authentication",
    "rate_limited",
    "unavailable",
    "timed_out",
    "protocol",
]
"""Provider-neutral discriminator for :class:`ModelFailure`.

These cover the transport/protocol surface a caller may want to retry over (rate
limited / unavailable / timed out), surface as a hard auth error (authentication), or
treat as a structured-output problem (protocol: empty body, unparseable JSON, ...).
"""


@dataclass(frozen=True)
class ModelFailure:
    """A provider-neutral model call failure.

    ``provider`` is an *identity* tag (e.g. ``"opencode"``, ``"claude-code"``) carried
    for observability/provenance only; callers MUST NOT branch on it for behaviour
    (architecture §7.1 provider isolation).
    """

    kind: ModelFailureKind
    detail: str
    provider: str
    attempts: int = 1


class ModelFailureError(Exception):
    """Control-flow exception carrying a :class:`ModelFailure`.

    Raised by the PydanticAI model bridges inside ``request()`` so the adapter /
    Agent loop can surface a structured failure instead of a domain exception. This
    keeps shared infrastructure free of any domain failure type.
    """

    def __init__(self, failure: ModelFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure


@dataclass(frozen=True)
class StructuredModelResponse:
    """The text + usage returned by one model turn.

    Mirrors what a PydanticAI ``ModelResponse`` carries, expressed domain-free so the
    transport boundary (client) does not need to import pydantic-ai. The
    PydanticAI bridge wraps this into a ``ModelResponse``.
    """

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
