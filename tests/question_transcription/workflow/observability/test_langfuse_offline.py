"""Offline tests for the Langfuse observability wrapper.

These run with NO ``LANGFUSE_*`` env vars set, so the wrapper is in its disabled
no-op path: ``is_enabled()`` is False, ``graph_callbacks()`` is ``[]``, and the
``operation``/``generation`` context managers yield a no-op object whose
``update`` is silently ignored. They also unit-test ``sanitize`` and the OTel
attribute mask helper directly.

A small probe test documents the current pydantic-ai ``RunUsage`` field names so
the whole-paper adapter's ``usage_details`` mapping stays honest.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable the same way the other workflow tests do it.
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.observability import langfuse as lf  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures: force the disabled path regardless of the ambient environment.
# --------------------------------------------------------------------------- #
_LANGFUSE_ENV = (
    "LANGFUSE_BASE_URL",
    "LANGFUSE_HOST",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def _no_langfuse_env(monkeypatch):
    """Strip every Langfuse env var and reset the wrapper's caches per test."""

    for var in _LANGFUSE_ENV:
        monkeypatch.delenv(var, raising=False)
    lf._read_config.cache_clear()
    lf._client.cache_clear()
    yield
    lf._read_config.cache_clear()
    lf._client.cache_clear()


# --------------------------------------------------------------------------- #
# Disabled-path behaviour
# --------------------------------------------------------------------------- #
def test_is_enabled_false_without_env():
    assert lf.is_enabled() is False


def test_graph_callbacks_empty_when_disabled():
    assert lf.graph_callbacks() == []


def test_operation_is_noop_when_disabled():
    with lf.operation("paper-ingestion", input={"paper_id": "x"}, session_id="s") as obs:
        assert obs.__class__.__name__ == "_NoopObs"
        obs.update(output="anything", usage_details={"input": 1, "output": 2})  # must not raise


def test_generation_is_noop_when_disabled():
    with lf.generation("qwen-ocr", model="qwen3.5-ocr", input={"page_number": 1}) as obs:
        assert obs.__class__.__name__ == "_NoopObs"
        obs.update(output="text", usage_details={"input": 0, "output": 0})


def test_flush_is_noop_when_disabled():
    lf.flush()  # must not raise


def test_partial_config_disables_without_raising(caplog):
    """Only some LANGFUSE_* vars set → disabled, with a warning, never an error."""

    os.environ["LANGFUSE_BASE_URL"] = "http://localhost:3000"
    os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-x"
    # secret key intentionally missing
    lf._read_config.cache_clear()
    try:
        assert lf.is_enabled() is False
        assert lf.graph_callbacks() == []
    finally:
        os.environ.pop("LANGFUSE_BASE_URL", None)
        os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        lf._read_config.cache_clear()


# --------------------------------------------------------------------------- #
# sanitize()
# --------------------------------------------------------------------------- #
def test_sanitize_truncates_long_string():
    long = "x" * 50000
    out = lf.sanitize(long)
    assert isinstance(out, str)
    assert len(out) <= lf._MAX_ATTRIBUTE_CHARS
    assert "…<+" in out


def test_sanitize_redacts_bare_base64_blob():
    # A realistic base64 run mixes the alphabet; build one with full diversity.
    import base64

    blob = base64.b64encode(os.urandom(3000)).decode()  # ~4000+ chars, high entropy
    out = lf.sanitize(blob)
    assert out == "<base64 blob redacted>"


def test_sanitize_does_not_mistake_repeated_text_for_base64():
    # A long run of identical chars is NOT base64; it must be truncated, not
    # redacted. Use a length over the cap so truncation actually happens.
    out = lf.sanitize("q" * 20000)
    assert out != "<base64 blob redacted>"
    assert "…<+" in out
    assert len(out) <= lf._MAX_ATTRIBUTE_CHARS


def test_sanitize_leaves_short_string_intact():
    assert lf.sanitize("hello world") == "hello world"


def test_sanitize_collapses_list_of_dict():
    assert lf.sanitize([{"a": 1}, {"b": 2}]) == "[list of 2 dict]"


def test_simplify_artifact_ref_shape():
    ref = {"path": "a/b.yaml", "sha256": "abc", "schema": "v1", "blob": "x" * 9000}
    assert lf.sanitize(ref) == "ref:a/b.yaml(v1)"


def test_sanitize_nested_dict_kept_to_depth():
    out = lf.sanitize({"outer": {"inner": {"deep": {"x": 1}}}})
    assert isinstance(out, dict)
    assert "outer" in out


def test_sanitize_passthrough_primitives():
    assert lf.sanitize(42) == 42
    assert lf.sanitize(3.14) == 3.14
    assert lf.sanitize(True) is True
    assert lf.sanitize(None) is None


# --------------------------------------------------------------------------- #
# _sanitize_attribute_string() — used by mask_otel_spans on serialized attrs
# --------------------------------------------------------------------------- #
def test_sanitize_attribute_string_keeps_valid_json_string():
    import json

    original = json.dumps({"page_number": 1, "text": "x" * 20000})
    out = lf._sanitize_attribute_string(original)
    assert isinstance(out, str)
    # Still valid JSON after masking.
    parsed = json.loads(out)
    assert parsed["page_number"] == 1
    assert "…<+" in parsed["text"]


def test_sanitize_attribute_string_handles_non_json_string():
    out = lf._sanitize_attribute_string("just a plain string, no json here")
    assert isinstance(out, str)
    assert "plain string" in out


def test_sanitize_attribute_string_always_returns_str():
    # Even weird input must yield a str so the OTel attribute contract holds.
    assert isinstance(lf._sanitize_attribute_string(""), str)
    assert isinstance(lf._sanitize_attribute_string("{not json"), str)


# --------------------------------------------------------------------------- #
# _mask_otel_spans() — never raises, never drops a span
# --------------------------------------------------------------------------- #
def test_mask_returns_none_when_nothing_maskable():
    params = _FakeParams({"span-1": _FakeSpan({"service.name": "x"})})
    assert lf._mask_otel_spans(params) is None


def test_mask_truncates_maskable_large_attribute():
    big = "q" * 20000
    params = _FakeParams({"span-1": _FakeSpan({"langfuse.observation.output": big})})
    result = lf._mask_otel_spans(params)
    assert result is not None
    patch = result.span_patches[_FakeId("span-1")]
    masked = patch.set_attributes["langfuse.observation.output"]
    assert len(masked) <= lf._MAX_ATTRIBUTE_CHARS
    assert "…<+" in masked


def test_mask_touches_gen_ai_prefixes():
    big = "p" * 20000
    params = _FakeParams({"span-1": _FakeSpan({"gen_ai.prompt.0.content": big})})
    result = lf._mask_otel_spans(params)
    assert result is not None
    assert "gen_ai.prompt.0.content" in result.span_patches[_FakeId("span-1")].set_attributes


def test_mask_never_raises_on_bad_input():
    # Even if a span has no .attributes, the mask must not raise.
    class _BadSpan:
        attributes = None

    class _BadParams:
        spans = {_FakeId("bad"): _BadSpan()}

    # Should swallow and return None, not propagate.
    assert lf._mask_otel_spans(_BadParams()) is None


# --------------------------------------------------------------------------- #
# pydantic-ai RunUsage field-name probe (documents the adapter's usage mapping)
# --------------------------------------------------------------------------- #
def test_run_usage_has_input_output_token_fields():
    """Pin the field names the whole-paper adapter maps into usage_details.

    If pydantic-ai renames these, this test fails loudly so the adapter's
    ``getattr(usage, "input_tokens", 0)`` mapping gets revisited.
    """

    usage_mod = importlib.import_module("pydantic_ai.usage")
    RunUsage = usage_mod.RunUsage
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(RunUsage)}
    assert "input_tokens" in field_names, "RunUsage no longer has input_tokens"
    assert "output_tokens" in field_names, "RunUsage no longer has output_tokens"


# --------------------------------------------------------------------------- #
# Test doubles for the OTel mask params
# --------------------------------------------------------------------------- #
class _FakeId:
    """Hashable stand-in for OtelSpanIdentifier keyed on a string."""

    __slots__ = ("_k",)

    def __init__(self, key: str) -> None:
        self._k = key

    def __eq__(self, other):  # noqa: D401
        return isinstance(other, _FakeId) and other._k == self._k

    def __hash__(self):  # noqa: D401
        return hash(self._k)


class _FakeSpan:
    __slots__ = ("attributes",)

    def __init__(self, attributes: dict) -> None:
        self.attributes = attributes


class _FakeParams:
    __slots__ = ("spans",)

    def __init__(self, spans: dict) -> None:
        # Re-key on _FakeId so the mask's `params.spans.items()` iteration works.
        self.spans = {_FakeId(k): v for k, v in spans.items()}
