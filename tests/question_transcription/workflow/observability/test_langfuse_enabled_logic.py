"""Enabled-path logic tests for the Langfuse observability wrapper.

These do NOT connect to a real Langfuse server. They force the wrapper into its
*enabled* state by monkeypatching the cached ``_client()`` to return a fake
client that records the observations it is asked to open. This exercises the
real bodies of ``operation`` / ``generation`` / ``cache_span`` and the
``run_live_paper._phase_root`` phase routing — the logic the offline tests
cannot reach (review #10).

What we assert (and why):
- ``generation`` opens an observation with ``as_type="generation"``; a cache hit
  must instead open ``as_type="span`` via ``cache_span`` so it is NOT counted as
  a model call (review #6).
- A failed model call marks the generation ``level="ERROR"`` before the context
  exits, so a failed OCR is not displayed as success (review #5).
- ``_phase_root`` opens one root ``operation`` per phase, with
  ``session_id == run_id`` (not ``paper_id``), ``phase`` in metadata/trace_name,
  and a CallbackHandler-bearing config; the initial run and a human resume share
  the session but get distinct trace names (review #1/#2/#3).

The fake client does not validate Langfuse semantics; it only captures the
arguments the wrapper passes so we can assert on them.
"""

from __future__ import annotations

import importlib
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Ensure the repo root is importable the same way the other workflow tests do it.
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.observability import langfuse as lf  # noqa: E402


# --------------------------------------------------------------------------- #
# Fake client: records every observation the wrapper opens.
# --------------------------------------------------------------------------- #
@dataclass
class _Opened:
    """A record of one observation the wrapper asked the client to open."""

    name: str
    as_type: str | None = None
    model: str | None = None
    input: Any = None
    metadata: Any = None
    updates: list = field(default_factory=list)


class _RecordingObs:
    """The observation object yielded by ``start_as_current_observation``.

    Mirrors the public surface business code uses: ``update(**kw)``. Records
    every update so tests can assert on level/output/usage.
    """

    def __init__(self, opened: _Opened) -> None:
        self._opened = opened

    def update(self, **kw: Any) -> None:
        self._opened.updates.append(kw)


class _FakeClient:
    """Stand-in for the Langfuse client returned by ``lf._client()``."""

    def __init__(self) -> None:
        self.opened: list[_Opened] = []

    @contextmanager
    def start_as_current_observation(
        self,
        *,
        name: str,
        as_type: str | None = None,
        model: str | None = None,
        input: Any = None,
        metadata: Any = None,
    ) -> Any:
        rec = _Opened(
            name=name,
            as_type=as_type,
            model=model,
            input=input,
            metadata=metadata,
        )
        self.opened.append(rec)
        yield _RecordingObs(rec)

    def flush(self) -> None:  # the wrapper calls this in finally
        pass


@pytest.fixture
def enabled_client(monkeypatch):
    """Force the wrapper into its enabled state with a recording fake client.

    Sets a complete LANGFUSE_* config so ``_read_config`` returns a ``_Config``,
    clears the lru_caches so the new config takes effect, then replaces the
    cached ``_client`` with one returning a :class:`_FakeClient`.
    """

    for var in ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(var, "test-value")
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    lf._read_config.cache_clear()
    lf._client.cache_clear()

    fake = _FakeClient()

    def _fake_client() -> Any:
        return fake

    monkeypatch.setattr(lf, "_client", _fake_client)
    # graph_callbacks() calls _read_config() then _client(); both now resolve to
    # the enabled path. It still tries to import CallbackHandler from langfuse,
    # which IS installed in the workflow venv, so this returns a real handler.
    yield fake

    # Only _read_config needs clearing: monkeypatch restores the original _client
    # (and its lru_cache) automatically, but _read_config saw the env change.
    lf._read_config.cache_clear()


# --------------------------------------------------------------------------- #
# observation type routing (review #5/#6)
# --------------------------------------------------------------------------- #
def test_generation_opens_generation_observation(enabled_client):
    with lf.generation("qwen-ocr", model="qwen3.5-ocr", input={"page_number": 1}):
        pass
    assert len(enabled_client.opened) == 1
    obs = enabled_client.opened[0]
    assert obs.name == "qwen-ocr"
    assert obs.as_type == "generation"
    assert obs.model == "qwen3.5-ocr"


def test_cache_span_opens_span_observation_not_generation(enabled_client):
    # A cache hit must NOT be a GENERATION — otherwise it pollutes model-call
    # count / latency / token / cost / success-rate metrics (review #6).
    with lf.cache_span("qwen-ocr.cache", metadata={"page_number": 1}):
        pass
    assert len(enabled_client.opened) == 1
    obs = enabled_client.opened[0]
    assert obs.name == "qwen-ocr.cache"
    assert obs.as_type == "span"
    assert obs.model is None  # spans carry no model


def test_cache_span_defaults_cache_hit_metadata(enabled_client):
    with lf.cache_span("qwen-ocr.cache", metadata={"page_number": 7}):
        pass
    obs = enabled_client.opened[0]
    assert obs.metadata["cache_hit"] is True
    assert obs.metadata["page_number"] == 7


def test_generation_failure_marked_error_before_context_exit(enabled_client):
    # Mirror the adapter pattern: open the generation, set ERROR, then exit.
    with lf.generation("qwen-ocr", model="qwen3.5-ocr") as obs:
        obs.update(level="ERROR", status_message="RuntimeError: HTTP 503")
    rec = enabled_client.opened[0]
    assert rec.updates == [{"level": "ERROR", "status_message": "RuntimeError: HTTP 503"}]


# --------------------------------------------------------------------------- #
# _phase_root routing (review #1/#2/#3)
# --------------------------------------------------------------------------- #
def _import_driver():
    """Import the driver lazily so simply collecting this test module does not
    pull in the whole LangGraph stack when langfuse is absent."""

    return importlib.import_module(
        "scripts.question_transcription.workflow.run_live_paper"
    )


def test_phase_root_initial_vs_human_resume_share_session_distinct_trace(enabled_client, monkeypatch):
    driver = _import_driver()
    run_id = "run-abcdef123456"
    paper_id = "2021-QINGPU-YIMO"
    thread_id = "thread-run-abcdef123456"

    # Stub the bits _phase_root touches beyond lf: graph_callbacks must return a
    # list (it normally imports CallbackHandler, which is fine here, but we want
    # the test independent of that import succeeding).
    monkeypatch.setattr(lf, "graph_callbacks", lambda: ["<fake-handler>"])

    opened_initial = []
    with driver._phase_root(
        run_id=run_id, paper_id=paper_id, thread_id=thread_id, phase="initial",
    ) as (config_initial, _root_initial):
        opened_initial = list(enabled_client.opened)

    with driver._phase_root(
        run_id=run_id, paper_id=paper_id, thread_id=thread_id, phase="human-resume",
    ) as (config_resume, _root_resume):
        pass

    # Two root operations opened, one per phase.
    assert len(enabled_client.opened) == 2
    init_op = enabled_client.opened[0]
    resume_op = enabled_client.opened[1]

    # Same session (run_id) for both phases ...
    assert init_op.metadata["run_id"] == run_id
    assert resume_op.metadata["run_id"] == run_id
    assert init_op.metadata["paper_id"] == paper_id
    assert resume_op.metadata["paper_id"] == paper_id
    # ... but distinct phases (and thus distinct traces).
    assert init_op.metadata["phase"] == "initial"
    assert resume_op.metadata["phase"] == "human-resume"
    # The operation name embeds the phase so the two traces are distinguishable.
    assert init_op.name != resume_op.name
    assert "initial" in init_op.name
    assert "human-resume" in resume_op.name


def test_phase_root_config_carries_callbacks_and_session_metadata(enabled_client, monkeypatch):
    driver = _import_driver()
    run_id = "run-deadbeef0000"
    paper_id = "PAPER-X"

    monkeypatch.setattr(lf, "graph_callbacks", lambda: ["<fake-handler>"])

    with driver._phase_root(
        run_id=run_id, paper_id=paper_id, thread_id="t1", phase="initial",
    ) as (config, _root):
        # The CallbackHandler is injected into the LangGraph config so node
        # observations nest under the root (review #3). Previously resume()'s
        # config had NO callbacks at all.
        assert config["callbacks"] == ["<fake-handler>"]
        assert config["configurable"]["thread_id"] == "t1"
        assert config["recursion_limit"] == 200
        # session_id is the run, not the paper (review #1).
        assert config["metadata"]["langfuse_session_id"] == run_id
        assert config["metadata"]["paper_id"] == paper_id
        assert config["metadata"]["run_id"] == run_id
        assert config["metadata"]["phase"] == "initial"
        assert config["metadata"]["langfuse_tags"] == ["question-ingestion"]
        assert config["run_name"].startswith("question-ingestion.initial:")
