"""LangSmith trace sink with default redaction (design §10).

M1 INVARIANT (design §10.1 / §17): the graph runs even when LangSmith is
unconfigured. Page traces must NOT upload raw page images or full page text by
default — only hashes, sizes, page numbers, tokens, latency, adapter identity and
redacted error summaries. Whether real paper content may leave the host is a
separate deployment-level decision (design §10.1 last paragraph).

This module is a thin, optional sink. Nodes call :func:`trace_event` / the context
manager; if no ``LANGSMITH_API_KEY`` is present, everything degrades to no-ops and
in-process accumulation for the trace-summary report artifact.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


__all__ = [
    "TraceEvent",
    "TraceSink",
    "NullTraceSink",
    "default_sink",
    "trace_event",
]


@dataclass
class TraceEvent:
    node: str
    metadata: dict[str, Any] = field(default_factory=dict)


class TraceSink:
    """Base class — subclasses push events to a real backend (LangSmith, …)."""

    def emit(self, event: TraceEvent) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def flush(self) -> dict[str, Any]:
        """Return a trace-summary dict for the ``reports/trace-summary.yaml`` artifact."""
        return {"backend": "null", "events": 0}


class NullTraceSink(TraceSink):
    """No-op sink used when LangSmith is not configured (M1 invariant)."""

    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self._events.append(event)

    def flush(self) -> dict[str, Any]:
        # Redact by default: never copy raw text/images. Only structural metadata.
        return {
            "backend": "null",
            "events": len(self._events),
            "nodes": sorted({e.node for e in self._events}),
        }


def default_sink() -> TraceSink:
    """Return the configured trace sink, or a :class:`NullTraceSink` if unconfigured."""

    if os.environ.get("LANGSMITH_API_KEY"):
        # LangSmith wiring is intentionally lazy: importing it here keeps the
        # offline test suite free of the langsmith client unless tracing is on.
        try:  # pragma: no cover - only exercised with LANGSMITH_API_KEY set
            return _LangSmithTraceSink()
        except Exception:  # pragma: no cover - degrade to null on any wiring failure
            pass
    return NullTraceSink()


class _LangSmithTraceSink(TraceSink):  # pragma: no cover - live only
    def __init__(self) -> None:
        from langsmith import Client

        self._client = Client()
        self._events: list[TraceEvent] = []

    def emit(self, event: TraceEvent) -> None:
        self._events.append(event)
        # Full LangSmith run tracking is layered in later (design §10.2). For the
        # first milestone we accumulate redacted metadata for the trace-summary.

    def flush(self) -> dict[str, Any]:
        return {
            "backend": "langsmith",
            "project": os.environ.get("LANGSMITH_PROJECT", "question-ingestion-dev"),
            "events": len(self._events),
            "nodes": sorted({e.node for e in self._events}),
        }


# Module-level convenience for node call-sites; thread-unsafe by design (single run).
_active: TraceSink | None = None


def _get() -> TraceSink:
    global _active
    if _active is None:
        _active = NullTraceSink()
    return _active


def reset(sink: TraceSink | None = None) -> None:
    """Replace the active sink (tests inject None to reset to a fresh null)."""

    global _active
    _active = sink


_NULL = NullTraceSink()


@contextmanager
def trace_event(node: str, **metadata: Any) -> Iterator[None]:
    """Context manager that emits one redacted trace event around a node body.

    Metadata passed here should already be redacted (hashes, counts, ids) — never
    raw page text or image bytes. The context manager swallows nothing; it only
    records the event boundary.
    """

    sink = _get()
    sink.emit(TraceEvent(node=node, metadata=metadata))
    yield
