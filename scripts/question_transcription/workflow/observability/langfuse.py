"""Thin Langfuse wrapper for the question-ingestion workflow.

Business code (nodes, adapters, the live driver) imports THIS module only. It
never imports ``langfuse`` or ``opentelemetry`` directly. The wrapper owns:

- **configuration**: reads ``LANGFUSE_BASE_URL`` / ``LANGFUSE_PUBLIC_KEY`` /
  ``LANGFUSE_SECRET_KEY`` (with a legacy ``LANGFUSE_HOST`` fallback at read time).
  Three-state gating (review point #8): all three env absent → disabled (info);
  some present → disabled (warning); all present but the SDK import fails →
  ``RuntimeError`` (never silent).
- **the singleton client**: ``Langfuse(base_url=..., mask_otel_spans=...)`` is
  constructed once, then the canonical client is retrieved via
  ``get_client(public_key=...)`` so ``CallbackHandler`` and manual observations
  share the same project/OTel context (review point #5).
- **attribute masking**: a single ``mask_otel_spans`` callback truncates and
  redacts the few known-large input/output + ``gen_ai.*`` attributes. We do NOT
  drop spans by size — that would orphan child generations and break the trace
  tree (review point #3).
- **a clean public surface**: ``is_enabled`` / ``graph_callbacks`` /
  ``operation`` / ``generation`` / ``flush`` / ``sanitize``. Offline (no env),
  every path is a no-op, so tests never touch Langfuse.

Design refs: Langfuse Python SDK v4 (OTel-native), ``mask_otel_spans`` added
~4.9; pinned ``langfuse==4.14.2`` in requirements.txt.
"""

from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator, Optional

__all__ = [
    "is_enabled",
    "graph_callbacks",
    "operation",
    "generation",
    "cache_span",
    "flush",
    "sanitize",
]

logger = logging.getLogger("question_ingestion.observability.langfuse")

# Attribute keys/prefixes whose string values are large enough to warrant
# masking before export. Kept narrow on purpose: ``mask_otel_spans`` runs
# synchronously on the OTel export worker thread, so it must be fast and must
# never raise (a raised mask callback drops the whole export batch).
_MASKABLE_ATTRIBUTE_KEYS = frozenset(
    {"langfuse.observation.input", "langfuse.observation.output"}
)
_MASKABLE_ATTRIBUTE_PREFIXES = (
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.input",
    "gen_ai.output",
)

# Hard cap for any single string we let into an observation attribute. Generous
# enough to keep a full error string or a page of OCR text, tight enough that a
# whole WorkflowState dump or a raw base64 image never lands in Langfuse.
_MAX_ATTRIBUTE_CHARS = 8000

# Heuristic for a bare (non-data-URI) base64 blob, e.g. inside a JSON-serialized
# message list that the adapter built before Langfuse's built-in media detector
# had a chance to see a ``data:`` prefix. Langfuse already converts true
# ``data:<ct>;base64,...`` URIs to media references; this only catches the rest.
# The match is a candidate only; :func:`_is_base64_blob` additionally requires
# enough character diversity so that a long but low-entropy string (a run of
# repeated chars, a plain long text) is NOT mistaken for base64.
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{4000,}={0,2}")
# Minimum distinct characters a real base64 run contains. Real base64 of any
# non-trivial payload mixes the alphabet heavily; a string of 5000 identical
# chars has 1 distinct char and is text, not base64.
_BASE64_MIN_DISTINCT_CHARS = 16

# Lists longer than this collapse to a count summary (``[list of N <type>]``).
# Lists at or below this length are recursed element-by-element so small
# structured payloads (e.g. an OCR prompt's role/content message list) stay
# visible in the trace. The per-string-leaf cap still bounds total attribute
# size, so this only controls structure visibility, not memory/bandwidth.
_MAX_LIST_ELEMENTS = 50


# --------------------------------------------------------------------------- #
# Configuration (three-state)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class _Config:
    base_url: str
    public_key: str
    secret_key: str


@lru_cache(maxsize=1)
def _read_config() -> Optional[_Config]:
    """Return the Langfuse config, or None when tracing is intentionally off.

    Three states (review #8):
      - all three env vars absent → None (disabled, info)
      - some present → None (disabled, warning that config is incomplete)
      - all present → _Config (caller still has to import the SDK)
    """

    base_url = os.getenv("LANGFUSE_BASE_URL") or os.getenv("LANGFUSE_HOST")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    present = [bool(base_url), bool(public_key), bool(secret_key)]
    if not any(present):
        return None  # cleanly disabled
    if not all(present):
        logger.warning(
            "Langfuse tracing disabled: configuration incomplete "
            "(set LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY "
            "together; currently base_url=%s public_key=%s secret_key=%s).",
            "set" if base_url else "missing",
            "set" if public_key else "missing",
            "set" if secret_key else "missing",
        )
        return None
    return _Config(base_url=base_url, public_key=public_key, secret_key=secret_key)


def is_enabled() -> bool:
    """True only when Langfuse config is fully present."""

    return _read_config() is not None


# --------------------------------------------------------------------------- #
# Client singleton
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _client() -> Any:
    """Initialize the Langfuse singleton once and return the canonical client.

    Constructs ``Langfuse(...)`` explicitly so we can register the
    ``mask_otel_spans`` hook (the ``get_client()`` singleton cannot inject it),
    then returns ``get_client(public_key=...)`` so ``CallbackHandler()`` and
    manual observations share the same project. We deliberately do NOT pass
    ``should_export_span``: dropping a node span by size would orphan its child
    generations (review #3). The default v4 exporter filter already keeps only
    Langfuse-SDK / ``gen_ai.*`` / known-LLM-instrumentor spans.
    """

    config = _read_config()
    if config is None:
        return None
    try:
        from langfuse import Langfuse, get_client
    except ImportError as exc:  # configured but broken install → never silent
        raise RuntimeError(
            "Langfuse is configured (LANGFUSE_* env vars present) but the "
            "`langfuse` package could not be imported. Install it with "
            "`pip install langfuse` or unset the LANGFUSE_* variables."
        ) from exc
    # Register the mask hook exactly once by constructing the client explicitly.
    # ``environment`` (development/production) keeps local smoke runs out of prod
    # metrics; defaults to LANGFUSE_TRACING_ENVIRONMENT then "development".
    Langfuse(
        base_url=config.base_url,
        public_key=config.public_key,
        secret_key=config.secret_key,
        environment=os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "development"),
        mask_otel_spans=_mask_otel_spans,
    )
    return get_client(public_key=config.public_key)


def graph_callbacks() -> list:
    """Return the LangGraph/LangChain callback list for ``config["callbacks"]``.

    Empty list when disabled, so the driver's ``config`` stays valid offline.
    Ensures the singleton client is initialized first so ``CallbackHandler``
    inherits the configured OTel context.
    """

    if _read_config() is None:
        return []
    client = _client()  # initializes singleton + mask hook
    if client is None:
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except ImportError:
        logger.exception("langfuse configured but CallbackHandler unavailable; tracing disabled.")
        return []


def flush() -> None:
    """Block until the background export queue drains. No-op when disabled.

    Safe to call from a ``finally`` block; failures here must not mask a real
    workflow/model exception, so the caller wraps this in its own try/except.
    """

    client = _client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # pragma: no cover - network/export failure, never fatal
        logger.exception("Langfuse flush failed; trace data may be incomplete.")


# --------------------------------------------------------------------------- #
# Public observation context managers
# --------------------------------------------------------------------------- #
class _NoopObs:
    """Returned observation when Langfuse is disabled; ``update`` is a no-op."""

    def update(self, **_: Any) -> None:  # noqa: D401 - trivial passthrough
        """No-op update for the disabled path."""


@contextmanager
def operation(
    name: str,
    *,
    input: Any = None,
    metadata: Optional[dict] = None,
    session_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    trace_name: Optional[str] = None,
) -> Iterator[Any]:
    """A root-level span observation wrapping a whole run.

    Propagates trace-level attributes (session/tags/trace name) into the OTel
    context BEFORE creating the observation, so both the manual root span and
    the nested ``CallbackHandler`` observations inherit them. Used by the live
    driver to wrap the graph stream.
    """

    client = _client()
    if client is None:
        yield _NoopObs()
        return
    try:
        from langfuse import propagate_attributes

        propa = propagate_attributes(
            session_id=session_id,
            tags=tags,
            trace_name=trace_name or name,
            metadata=metadata,
        )
    except ImportError:  # pragma: no cover - propagate_attributes is top-level in v4
        import contextlib

        propa = contextlib.nullcontext()
    with propa:
        with client.start_as_current_observation(
            name=name,
            as_type="span",
            input=sanitize(input),
            metadata=sanitize(metadata),
        ) as obs:
            yield obs


@contextmanager
def generation(
    name: str,
    *,
    model: str,
    input: Any = None,
    metadata: Optional[dict] = None,
) -> Iterator[Any]:
    """A nested ``generation`` observation around one native model call.

    Callers (qwen/mimo/structured-transcriber) wrap a single LLM request and
    then call ``obs.update(output=..., usage_details={...})``.
    """

    client = _client()
    if client is None:
        yield _NoopObs()
        return
    with client.start_as_current_observation(
        name=name,
        as_type="generation",
        model=model,
        input=sanitize(input),
        metadata=sanitize(metadata),
    ) as obs:
        yield obs


@contextmanager
def cache_span(
    name: str,
    *,
    metadata: Optional[dict] = None,
) -> Iterator[Any]:
    """A ``span`` observation for a cache hit that served a would-be model call.

    A cache hit must NOT be recorded as a ``GENERATION``: it is not a real model
    invocation, so counting it would pollute model-call count / latency / token /
    cost / success-rate metrics. Adapters call this instead of :func:`generation`
    once they learn a request was served from cache. Carries ``cache_hit=True`` in
    metadata so a dashboard can still attribute cache-served work if desired.
    """

    client = _client()
    if client is None:
        yield _NoopObs()
        return
    meta = dict(metadata or {})
    meta.setdefault("cache_hit", True)
    with client.start_as_current_observation(
        name=name,
        as_type="span",
        metadata=sanitize(meta),
    ) as obs:
        yield obs


# --------------------------------------------------------------------------- #
# Sanitization (public + internal)
# --------------------------------------------------------------------------- #
def sanitize(value: Any) -> Any:
    """Project a value to a JSON-safe, size-bounded form for trace input/output.

    Recursively collapses large lists/dicts to count summaries, replaces bare
    base64 blobs with a placeholder, and truncates long strings. Returns objects
    that are safe to attach as a Langfuse observation ``input``/``output``.
    Business code may also call this directly (e.g. ``input=sanitize(prompt)``).
    """

    return _sanitize_value(value, depth=0)


def _sanitize_value(value: Any, *, depth: int) -> Any:
    # Depth guard: avoid unbounded recursion on cyclic/huge nested structures.
    if depth > 6:
        return "<truncated: max depth>"
    if isinstance(value, str):
        return _sanitize_plain_string(value)
    if isinstance(value, list):
        if not value:
            return []
        # Only collapse LARGE lists to a count summary. Small lists (e.g. an OCR
        # prompt's handful of role/content messages) are recursed element-by-
        # element so their structure stays visible in the trace; large lists
        # (e.g. a whole WorkflowState page list) still collapse to a count. The
        # per-string-leaf cap (_MAX_ATTRIBUTE_CHARS) still bounds total size, so
        # expanding a small list cannot blow the attribute budget.
        if len(value) > _MAX_LIST_ELEMENTS:
            first = value[0]
            return f"[list of {len(value)} {type(first).__name__}]"
        return [_sanitize_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        # ArtifactRef-shaped dicts: keep path + schema, drop the heavy payload.
        if "path" in value and "sha256" in value:
            return f"ref:{value.get('path')}({value.get('schema', '?')})"
        if depth >= 3:
            return f"{{dict {len(value)} keys}}"
        return {k: _sanitize_value(v, depth=depth + 1) for k, v in value.items()}
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _sanitize_plain_string(str(value))


def _is_base64_blob(candidate: str) -> bool:
    """True if a regex candidate looks like a real base64 run, not plain text.

    A genuine base64 blob mixes the alphabet heavily; require a minimum number
    of distinct characters so that long-but-low-entropy strings (e.g. ``"q"*20000``
    or a normal sentence) are not redacted as base64.
    """

    return len(set(candidate.rstrip("="))) >= _BASE64_MIN_DISTINCT_CHARS


def _sanitize_plain_string(value: str) -> str:
    """Redact bare base64 blobs, then truncate to the attribute cap."""

    def _repl(match: re.Match) -> str:
        return "<base64 blob redacted>" if _is_base64_blob(match.group(0)) else match.group(0)

    redacted = _BASE64_BLOB.sub(_repl, value)
    return _truncate(redacted, _MAX_ATTRIBUTE_CHARS)


def _truncate(s: str, n: int) -> str:
    """Truncate to at most ``n`` chars *including* the truncation marker.

    The marker counts against the budget so an over-long string never produces an
    attribute whose serialized length still exceeds the cap.
    """

    if len(s) <= n:
        return s
    marker = f"…<+{len(s) - n} chars>"
    return s[: max(0, n - len(marker))] + marker


def _sanitize_attribute_string(value: str) -> str:
    """Mask an already-serialized OTel string attribute.

    ``mask_otel_spans`` operates on attributes that are already JSON-serialized
    strings (e.g. ``langfuse.observation.input``). Parse → run the public
    sanitizer → re-serialize so the attribute stays a valid OTel string. If it
    is not JSON, sanitize it as a plain string. Always returns a ``str`` so the
    OTel attribute type contract is never violated (review #4).
    """

    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return _sanitize_plain_string(value)
    sanitized = sanitize(parsed)
    try:
        return json.dumps(sanitized, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return _sanitize_plain_string(value)


# --------------------------------------------------------------------------- #
# mask_otel_spans hook
# --------------------------------------------------------------------------- #
def _mask_otel_spans(params: Any) -> Any:
    """Export-stage OTel span masking callback registered on the client.

    Runs on the OTel batch-processor worker thread. Must be fast, deterministic,
    and never raise (a raise drops the whole export batch). We only touch the
    handful of attributes that carry potentially-huge payloads; everything else
    passes through untouched. We never drop a span here — that would orphan
    child observations (review #3); use ``should_export_span`` for that, which
    we intentionally do not set.
    """

    try:
        from langfuse.types import MaskOtelSpansResult, OtelSpanPatch
    except ImportError:
        return None  # SDK missing — nothing to do
    try:
        patches = {}
        for identifier, span in params.spans.items():
            replacements = {}
            attrs = getattr(span, "attributes", None) or {}
            for key, value in attrs.items():
                if not _is_maskable(key) or not isinstance(value, str):
                    continue
                masked = _sanitize_attribute_string(value)
                if masked != value:
                    replacements[key] = masked
            if replacements:
                patches[identifier] = OtelSpanPatch(set_attributes=replacements)
        if not patches:
            return None
        return MaskOtelSpansResult(span_patches=patches)
    except Exception:
        # Never raise from a mask callback: returning None leaves the batch
        # unchanged, which is strictly safer than dropping it. Log so it is not
        # silent.
        logger.warning("mask_otel_spans failed; batch exported unmasked.", exc_info=True)
        return None


def _is_maskable(key: str) -> bool:
    if key in _MASKABLE_ATTRIBUTE_KEYS:
        return True
    return any(key.startswith(prefix) for prefix in _MASKABLE_ATTRIBUTE_PREFIXES)
