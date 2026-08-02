#!/usr/bin/env python3
"""Live end-to-end driver for the LangGraph question-ingestion workflow.

Runs ONE real paper through the compiled graph with real adapters:

- page text: qwen3.5-ocr (DASHSCOPE_API_KEY from environment)
- whole paper: claude-code glm-5.2 (claude CLI + GLM anthropic gateway)

Why this script exists: ``bootstrap.cli.start`` only persists ``state.json``; it never
invokes the graph. To verify the LangGraph workflow on a real paper we must compile
the graph with a checkpointer, ``stream`` it, and drive the two human-in-the-loop
interrupts (source review + final review) to completion.

Auto-approval policy (only when explicitly requested for verification):
- source review: write ``review/review-resolutions.yaml`` acknowledging all issues;
- final review: ``--final-review-mode auto`` writes a complete, hash-bound
  ``items/*/review.yaml`` for every question.  The default is ``human``: stop at
  the final-review interrupt after refreshing the Review UI catalog.

Resume semantics (langgraph 0.2.76): an interrupt can only be woken by streaming
``Command(resume=<value>)``; the ``<value>`` is what the interrupted node's
``interrupt()`` call returns.  This driver resumes with the constant
:data:`_RESUME_WAKE_ACK` — a pure wake signal that carries **no approval
decision**.  Every gate re-reads its on-disk artifact on resume
(``review-resolutions.yaml`` for source review, ``items/*/review.yaml`` for final
review), so a wake can never approve anything by itself.

Usage::

    source ~/.zshrc 2>/dev/null
    ./.venv/bin/python -m scripts.question_transcription.workflow.run_live_paper \
        --paper-id 2021-QINGPU-YIMO \
        --source <abs path to .doc/.docx/.pdf> \
        --source-kind doc

Output lands under ``build/question-ingestion/<paper-id>/<run-id>/``.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
from langgraph.types import Command

from .bootstrap.composition import BindMode, bind, build_run_layout, record_provenance
from .bootstrap.config import RuntimeAdapterConfig
from .checkpoint import make_sqlite_checkpointer, thread_id_for
from .graph import build_graph
from .orchestration.langgraph.state import (
    WorkflowState,
    dump_state,
    extract_outcome,
    initial_state,
)

# --------------------------------------------------------------------------- #
# OpenTelemetry -> Langfuse tracing
# --------------------------------------------------------------------------- #
# Two independent trace sources converge on the same Langfuse project:
#   1. Claude Code SDK: the `claude` CLI subprocess emits OTLP when we set the
#      CLAUDE_CODE_*_TELEMETRY env vars on os.environ (inherited by the child).
#   2. This driver: we wrap each graph node stream in an OTel span so the LangGraph
#      node-level execution tree is visible alongside the LLM calls.
# Langfuse self-hosted OTLP HTTP endpoint is /api/public/otel with Basic Auth.
_TRACER = None


def setup_otel(
    *,
    langfuse_host: str,
    langfuse_public_key: str,
    langfuse_secret_key: str,
    service_name: str,
) -> bool:
    """Initialize OTel TracerProvider exporting to Langfuse over OTLP/HTTP.

    Returns False (and degrades to no-op tracing) if the OTLP exporter is missing or
    Langfuse is unreachable; the run continues regardless so tracing never blocks the
    workflow verification.
    """

    global _TRACER
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:  # opentelemetry-sdk not installed
        _log(f"OTEL disabled (sdk missing): {exc}")
        return False

    import base64

    auth = base64.b64encode(
        f"{langfuse_public_key}:{langfuse_secret_key}".encode()
    ).decode()
    resource = Resource.create(
        {"service.name": service_name, "langfuse.project.key": langfuse_public_key}
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(
        endpoint=f"{langfuse_host}/api/public/otel/v1/traces",
        headers={
            "Authorization": f"Basic {auth}",
            "x-langfuse-ingestion-version": "4",
        },
        timeout=10,
    )
    provider.add_span_processor(
        BatchSpanProcessor(exporter, export_timeout_millis=10000)
    )
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer("question-ingestion")

    # Tell the Claude Code CLI subprocess to emit its own OTLP trace/metrics/logs to
    # the same Langfuse endpoint (docs: agent-sdk/observability).
    import os

    os.environ.setdefault("CLAUDE_CODE_ENABLE_TELEMETRY", "1")
    os.environ.setdefault("CLAUDE_CODE_ENHANCED_TELEMETRY_BETA", "1")
    os.environ.setdefault("OTEL_TRACES_EXPORTER", "otlp")
    os.environ.setdefault("OTEL_METRICS_EXPORTER", "otlp")
    os.environ.setdefault("OTEL_LOGS_EXPORTER", "otlp")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
    os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", f"{langfuse_host}/api/public/otel")
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_HEADERS",
        f"Authorization=Basic {auth},x-langfuse-ingestion-version=4",
    )
    # Short export intervals so short-lived runs flush before the process exits.
    os.environ.setdefault("OTEL_TRACES_EXPORT_INTERVAL", "1000")
    _log(f"OTEL enabled -> {langfuse_host}/api/public/otel (service={service_name})")
    return True


class _NodeSpan:
    """Context manager exposing the live Span so callers can set IO attributes.

    When OTEL is disabled (offline / no Langfuse), ``span`` is None and all set
    calls become no-ops, so node code never has to branch on tracing.
    """

    __slots__ = ("_tracer", "_name", "_attrs", "_cm", "span")

    def __init__(self, tracer, name: str, attrs: dict) -> None:
        self._tracer = tracer
        self._name = name
        self._attrs = attrs
        self._cm = None
        self.span = None

    def __enter__(self):
        if self._tracer is None:
            return None
        self._cm = self._tracer.start_as_current_span(self._name)
        self.span = self._cm.__enter__()
        for k, v in self._attrs.items():
            try:
                self.span.set_attribute(k, v)
            except Exception:
                pass
        return self.span

    def __exit__(self, *exc):
        if self._cm is not None:
            if exc[0] is not None and self.span is not None:
                try:
                    self.span.record_exception(exc[1])
                    self.span.set_status(_span_status_error())
                except Exception:
                    pass
            return self._cm.__exit__(*exc)
        return False


def _span_status_error():
    from opentelemetry.trace import Status, StatusCode

    return Status(StatusCode.ERROR)


def _span(name: str, **attrs) -> _NodeSpan:
    """Return a context manager wrapping a node span; no-op if OTEL is disabled."""

    return _NodeSpan(_TRACER, name, attrs)


def _repo_root() -> Path:
    # Must agree with adapters/_common_paths.repo_root() so build artifacts and the
    # materialize step's repo_root resolve to the same directory. Hard-coding
    # parents[N] is fragile (off-by layers between worktree layouts), so reuse the
    # adapter's canonical resolver.
    from .adapters._common_paths import repo_root

    return repo_root()


def _build_root() -> Path:
    return _repo_root() / "build"


def _ts() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


# Value handed to ``Command(resume=...)`` to wake a paused interrupt.  It is a pure
# wake signal — the approval gates ignore it and re-read their on-disk artifacts on
# resume (design §16.8).  It must be non-None: in langgraph 0.2.76 ``Command(resume=None)``
# raises ``EmptyInputError`` and ``stream(None, config)`` re-fires the interrupt instead
# of resuming, so a falsy wake cannot complete a human-in-the-loop step.
_RESUME_WAKE_ACK: dict[str, Any] = {"resume": True}


def _approve_source_review(layout) -> bool:
    """Write a review-resolutions.yaml that acknowledges every issue as accepted.

    Returns True if a resolution file was written (issues existed), False otherwise.
    """

    issues_path = layout.review_issues_path
    if not issues_path.exists():
        return False
    issues_doc = yaml.safe_load(issues_path.read_text(encoding="utf-8")) or {}
    issues = issues_doc.get("issues") or []
    resolutions = []
    for it in issues:
        issue_id = it.get("id") or it.get("issue_id") or it.get("ref")
        resolutions.append(
            {
                "id": issue_id,
                "decision": "accept",
                "reason": "auto-approved by live verification driver",
            }
        )
    out = {
        "schema": "math_transcription_review_resolutions/v1",
        "paper_id": issues_doc.get("paper_id", "unknown"),
        "resolutions": resolutions,
    }
    layout.review_resolutions_path.parent.mkdir(parents=True, exist_ok=True)
    layout.review_resolutions_path.write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    _log(f"  source review: wrote {len(resolutions)} resolution(s) -> {layout.review_resolutions_path}")
    return True


def _approve_final_review(staging_directory: str) -> int:
    """Write complete, hash-bound approved reviews; return the item count.

    ``review.yaml`` is an :class:`ExamItemReview`, not a status sidecar.  Its
    ``source_key`` and ``content_hash`` must be copied from the materialized
    ``source.yaml`` or the approved audit correctly rejects it as malformed/stale.
    """

    staging = Path(staging_directory)
    items_dir = staging / "items"
    if not items_dir.is_dir():
        return 0
    n = 0
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    for item_dir in sorted(items_dir.iterdir()):
        if not item_dir.is_dir():
            continue
        source_path = item_dir / "source.yaml"
        if not source_path.is_file():
            raise ValueError(f"{item_dir.name}: source.yaml missing before final review")
        source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
        source_key = source.get("source_key")
        content_hash = source.get("content_hash")
        source_item_id = source.get("item_id")
        if source_item_id != item_dir.name:
            raise ValueError(
                f"{item_dir.name}: source.yaml item_id is {source_item_id!r}"
            )
        if not isinstance(source_key, str) or not source_key:
            raise ValueError(f"{item_dir.name}: source.yaml source_key missing")
        if not isinstance(content_hash, str) or not content_hash:
            raise ValueError(f"{item_dir.name}: source.yaml content_hash missing")
        review = item_dir / "review.yaml"
        previous: dict[str, Any] = {}
        if review.exists():
            previous = yaml.safe_load(review.read_text(encoding="utf-8")) or {}
        notes = previous.get("notes")
        if not isinstance(notes, list):
            notes = []
        doc = {
            "schema": "math_exam_item_review/v1",
            "item_id": source_item_id,
            "source_key": source_key,
            "content_hash": content_hash,
            "status": "approved",
            "reviewer": "live-verification-driver",
            "reviewed_at": now,
            "notes": notes,
        }
        review.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        n += 1
    _log(f"  final review: approved {n} item(s) under {items_dir}")
    return n


def _stream_once(app, payload, config, label, run_root=None) -> dict[str, Any] | None:
    """Run one stream pass; print node updates; record a span per node.

    Each node gets one OTel span whose attributes carry the output state delta and
    (for the first node of a round) the relevant input state. Langfuse renders these
    as the top-level node execution tree; LLM-call spans (qwen OCR / claude-code)
    nest under whichever node invoked them via the OTel parent context.
    """

    last_state: dict[str, Any] | None = None
    prev_state: dict[str, Any] = {}
    try:
        for chunk in app.stream(payload, config=config, stream_mode="updates"):
            # chunk is {node_name: state_delta} under stream_mode="updates".
            for node, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue
                keys = [k for k in delta.keys() if k not in ("run_id", "paper_id")]
                _log(f"  [{label}] node={node} -> {sorted(keys)}")
                with _span(
                    f"node.{node}", node=node, round=label
                ) as span:
                    if span is not None:
                        span.set_attribute("output.keys", ",".join(sorted(keys)))
                        _attach_state(span, "output", delta, run_root=run_root)
                        # The input is the state before this node ran.
                        _attach_state(span, "input", _input_view(prev_state), run_root=run_root)
    except Exception as exc:  # surface real failures (adapter/model/contract)
        _log(f"  [{label}] STREAM ERROR: {type(exc).__name__}: {exc}")
        raise
    state = app.get_state(config)
    if state is not None:
        last_state = state.values or {}
        prev_state = dict(last_state)
    return last_state


def _input_view(state: dict[str, Any]) -> dict[str, Any]:
    """Project the large/rich state down to the fields nodes actually consume."""

    keep = {}
    for k in (
        "source_kind",
        "source_archive",
        "extracted_source",
        "page_text_jobs",
        "page_text_extracts",
        "page_text_failures",
        "whole_paper_transcription",
        "image_attribution",
        "source_paper",
        "draft",
        "staging_directory",
        "review_state",
        "terminal_errors",
    ):
        if k in state:
            keep[k] = state[k]
    return keep


def _attach_state(span, prefix: str, state: dict[str, Any], *, run_root=None) -> None:
    """Attach a redacted, size-bounded state projection to a span.

    Langfuse renders an observation's INPUT/OUTPUT from specific attributes
    (``langfuse.observation.input`` / ``langfuse.observation.output``), not from
    arbitrary ``prefix.key`` attributes. So we serialize the whole projection to one
    JSON string and set it on the recognized attribute, so the node's input state
    and output delta are visible in the UI's Input/Output panels.

    Field projection is content-aware (see :func:`_project_field`): the high-value
    node outputs (transcription question refs + evidence page numbers, page-text
    extracts, terminal errors) are expanded so they're readable in the UI instead
    of collapsed to ``[list of N dict]``. Only genuinely large blobs (raw page
    text bodies) stay folded. ``run_root`` lets the transcription ref be resolved
    to a per-question summary inline.
    """

    if span is None or not state:
        return
    attr = (
        "langfuse.observation.input" if prefix == "input" else "langfuse.observation.output"
    )
    projection = {k: _project_field(k, v, run_root=run_root) for k, v in state.items()}
    try:
        import json

        span.set_attribute(attr, _truncate(json.dumps(projection, ensure_ascii=False)))
    except Exception:
        pass


def _project_field(key: str, value: Any, *, run_root=None) -> Any:
    """Project one state field into a readable, size-bounded trace value.

    The high-value fields get content-aware expansion so a node's Input/Output is
    actually readable in Langfuse (question refs + evidence page numbers, error
    text, page-text page numbers + text length). Everything else falls back to the
    generic :func:`_simplify` count-summary so span attributes stay bounded.
    """

    if key == "whole_paper_transcription":
        # An ArtifactRef to structured/transcription.yaml. Resolve and inline a
        # compact per-question summary (ref + evidence page numbers) so the node's
        # Output shows what was transcribed, not just the path.
        ref = _simplify(value) if isinstance(value, dict) else str(value)
        return {"ref": ref, "questions": _summarize_transcription(value, run_root)}
    if key == "terminal_errors":
        # Always show full error text — these are the thing you open the trace to read.
        return value if isinstance(value, list) else [str(value)]
    if key == "page_text_extracts" and isinstance(value, list):
        # One entry per page: surface the page number + text length, fold the body.
        out = []
        for item in value:
            if isinstance(item, dict):
                art = item.get("artifact") or {}
                page = art.get("page_number")
                txt = art.get("text") or {}
                body = txt.get("text") if isinstance(txt, dict) else None
                out.append({
                    "page_number": page,
                    "text_chars": len(body) if isinstance(body, str) else None,
                    "ref": _simplify(txt) if isinstance(txt, dict) else None,
                })
            else:
                out.append(_simplify(item))
        return out
    if key in ("draft", "source_paper", "extracted_source", "image_attribution") and isinstance(value, dict):
        # ArtifactRef-shaped: keep path + schema.
        return _simplify(value)
    return _simplify(value)


def _summarize_transcription(ref: Any, run_root) -> list[dict[str, Any]]:
    """Resolve a transcription ArtifactRef to a per-question evidence summary.

    Returns ``[{"ref": "1", "type": "choice", "question_pages": [1],
    "solution_pages": [7]}, ...]`` so a transcription node's Output shows the
    page→question mapping directly, without opening the file. Folds to ``[]`` on
    any resolution/parse failure (never raises — tracing must not break the run).
    """

    try:
        if not isinstance(ref, dict) or not run_root:
            return []
        path = ref.get("path")
        if not isinstance(path, str):
            return []
        from pathlib import Path

        import yaml as _yaml

        yaml_path = (Path(run_root) / path) if not Path(path).is_absolute() else Path(path)
        if not yaml_path.exists():
            return []
        data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        out = []
        for section in data.get("sections") or []:
            for q in section.get("questions") or []:
                ev = q.get("evidence") or {}
                qp = [p["page_number"] for p in (ev.get("question") or [])
                      if isinstance(p, dict) and "page_number" in p]
                sp = [p["page_number"] for p in (ev.get("solution") or [])
                      if isinstance(p, dict) and "page_number" in p]
                out.append({
                    "ref": q.get("question_ref"),
                    "type": q.get("question_type"),
                    "question_pages": qp,
                    "solution_pages": sp,
                })
        return out
    except Exception:
        return []


def _simplify(v: Any) -> Any:
    """Collapse lists/dicts to counts + short summaries to keep span attrs small."""

    if isinstance(v, list):
        if not v:
            return "[]"
        first = v[0]
        if isinstance(first, dict):
            return f"[list of {len(v)} dict]"
        return f"[list of {len(v)} {type(first).__name__}]"
    if isinstance(v, dict):
        # ArtifactRef-shaped dicts: keep path + schema.
        if "path" in v and "sha256" in v:
            return f"ref:{v.get('path')}({v.get('schema', '?')})"
        return f"{{dict {len(v)} keys: {','.join(sorted(v))[:120]}}}"
    if isinstance(v, str):
        return v
    return str(v)


def _truncate(s: str, n: int = 20000) -> str:
    return s if len(s) <= n else s[:n] + f"…<+{len(s) - n} chars>"


def _main_repo_root() -> Path:
    """The main worktree's root (where the shared ``.venv`` web stack lives).

    In a linked worktree ``_repo_root()`` returns the worktree root, but the
    FastAPI/uvicorn venv is typically provisioned once in the main worktree.  We resolve
    it via ``git rev-parse --git-common-dir`` (the shared ``.git`` lives at the main
    root); on any failure we fall back to the worktree root itself.
    """

    try:
        common = subprocess.run(
            ["git", "rev-parse", "--git-common-dir"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root()),
            timeout=10,
        )
        if common.returncode == 0 and common.stdout.strip():
            return Path(common.stdout.strip()).resolve().parent
    except (OSError, subprocess.SubprocessError):
        pass
    return _repo_root()


def _select_review_ui_python() -> str:
    """Return an interpreter path whose site-packages expose fastapi + uvicorn.

    The Review UI server (``open_question_bank_review.py``) imports ``uvicorn`` and the
    FastAPI app at module load, so the launching interpreter must already have both
    importable.  A worktree-local ``.venv`` is provisioned for the workflow (langgraph,
    pydantic, …) but is *not* guaranteed to carry the Review UI's web stack, so we probe
    candidates in order and pick the first that can ``import fastapi, uvicorn``:

    1. the worktree-local ``./.venv/bin/python`` (preferred when present);
    2. the main-repo ``.venv/bin/python`` (shared web-stack venv);
    3. the ``python3`` on ``PATH`` as a last resort.

    The chosen path is echoed exactly as it will be executed, so the printed command is
    runnable as-is rather than just documented.
    """

    root = _repo_root()
    candidates = [
        root / ".venv/bin/python",
        _main_repo_root() / ".venv/bin/python",
        Path(os.environ.get("PYTHON", "python3")),
    ]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    probe_order: list[Path] = []
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            resolved = cand
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        probe_order.append(cand)
    for cand in probe_order:
        if not cand.exists():
            continue
        try:
            proc = subprocess.run(
                [str(cand), "-c", "import fastapi, uvicorn"],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode == 0:
            return str(cand)
    # Nothing probed cleanly — surface the first existing candidate so the failure is
    # an explicit ImportError at run time instead of a silently wrong interpreter.
    for cand in probe_order:
        if cand.exists():
            return str(cand)
    return "python3"


def _review_ui_command(layout) -> str:
    review_script = (
        _repo_root()
        / ".codex/skills/math-topic-question-bank/scripts/open_question_bank_review.py"
    )
    python_bin = _select_review_ui_python()
    bank_root = layout.root / "review-catalog"
    return f"{python_bin} {review_script} --bank-root {bank_root}"


def run(
    *,
    paper_id: str,
    source: str,
    source_kind: str,
    agent_host: str = "claude-code",
    page_provider: str = "qwen",
    final_review_mode: str = "human",
    max_resume_rounds: int = 6,
    langfuse_host: str | None = None,
    langfuse_public_key: str | None = None,
    langfuse_secret_key: str | None = None,
) -> str:
    if final_review_mode not in {"human", "auto"}:
        raise ValueError("final_review_mode must be 'human' or 'auto'")
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    if langfuse_host and langfuse_public_key and langfuse_secret_key:
        setup_otel(
            langfuse_host=langfuse_host,
            langfuse_public_key=langfuse_public_key,
            langfuse_secret_key=langfuse_secret_key,
            service_name=f"question-ingestion:{paper_id}",
        )
    config = RuntimeAdapterConfig(
        page_text_provider=page_provider,
        whole_paper_adapter=agent_host.replace("-", "_"),
    )
    layout = build_run_layout(_build_root(), paper_id, run_id)
    deps = bind(config, layout, mode="live")
    record_provenance(deps.artifact_store, config, run_id, paper_id)

    checkpointer = make_sqlite_checkpointer(layout.root / f"{run_id}.sqlite")
    thread = thread_id_for(run_id)
    lg_config = {"configurable": {"thread_id": thread}, "recursion_limit": 200}
    app = build_graph(deps, checkpointer=checkpointer)

    state = initial_state(
        run_id=run_id,
        paper_id=paper_id,
        source_kind=source_kind,
        source_archive=source,
    )
    _persist_state(layout, state)
    _log(f"START run_id={run_id} paper_id={paper_id} kind={source_kind}")
    _log(f"      source={source}")
    _log(f"      layout={layout.root}")
    _log(f"      agent={agent_host} page={page_provider}")

    payload: Any = state
    for rnd in range(max_resume_rounds):
        t0 = time.time()
        result = _stream_once(app, payload, lg_config, f"round{rnd}", run_root=layout.root)
        elapsed = time.time() - t0
        gs = app.get_state(lg_config)
        outcome = extract_outcome(gs.values or {}) if gs and gs.values else "running"
        next_interrupts = gs.next if gs is not None else ()
        _log(
            f"  round{rnd} done in {elapsed:.1f}s -> outcome={outcome} next={list(next_interrupts)}"
        )
        if outcome in ("completed", "failed"):
            break
        # Handle interrupts: write the approval artifacts, then resume.  Resume only
        # WAKES the paused node via Command(resume=_RESUME_WAKE_ACK); approval lives on
        # disk and is re-read by the gate on resume (design §16.8).
        resumed_something = False
        waiting_for_human_review = False
        if gs and getattr(gs, "tasks", None):
            for task in gs.tasks:
                interrupts = getattr(task, "interrupts", ()) or ()
                if not interrupts:
                    continue
                kind = interrupts[0].value.get("kind") if interrupts else None
                _log(f"  INTERRUPT kind={kind}")
                if kind == "waiting_for_source_review":
                    _approve_source_review(layout)
                    resumed_something = True
                elif kind == "waiting_for_final_review":
                    staging = (gs.values or {}).get("staging_directory")
                    if final_review_mode == "auto" and staging:
                        _approve_final_review(staging)
                        resumed_something = True
                    else:
                        _log("  final review is ready for Review UI; leaving graph interrupted")
                        if staging:
                            _log(f"  staging={staging}")
                            _log(f"  open Review UI: {_review_ui_command(layout)}")
                            _log(
                                f"  after review: {sys.executable} -m "
                                "scripts.question_transcription.workflow.run_live_paper "
                                f"--paper-id {paper_id} --resume-run-id {run_id}"
                            )
                        waiting_for_human_review = True
        if waiting_for_human_review:
            break
        if not resumed_something and outcome == "running" and not next_interrupts:
            _log("  no interrupt to resume and graph idle; stopping.")
            break
        # Wake the paused interrupt.  In langgraph 0.2.76 only a non-None Command
        # resume value advances past the interrupt; the wake ack carries no decision.
        payload = Command(resume=_RESUME_WAKE_ACK)

    final = app.get_state(lg_config)
    final_state = final.values if final is not None else {}
    _persist_state(layout, final_state)
    outcome = extract_outcome(final_state) if final_state else "failed"
    errors = final_state.get("terminal_errors") or []
    _log(f"FINAL outcome={outcome}")
    if errors:
        _log("terminal_errors:")
        for e in errors:
            _log(f"  - {e}")
    _log(f"layout={layout.root}")
    return run_id


def resume(
    *,
    paper_id: str,
    run_id: str,
    agent_host: str = "claude-code",
    page_provider: str = "qwen",
) -> str:
    """Resume one persisted final-review interrupt and run the approved audit.

    The resume value carries no approval decision.  ``final_review_check`` re-reads
    the on-disk Review UI artifacts; pending reviews interrupt again, while only a
    complete set of fresh approved reviews can route to ``approved_audit``.
    """

    layout = build_run_layout(_build_root(), paper_id, run_id)
    checkpoint_path = layout.root / f"{run_id}.sqlite"
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")
    config = RuntimeAdapterConfig(
        page_text_provider=page_provider,
        whole_paper_adapter=agent_host.replace("-", "_"),
    )
    deps = bind(config, layout, mode="live")
    checkpointer = make_sqlite_checkpointer(checkpoint_path)
    lg_config = {
        "configurable": {"thread_id": thread_id_for(run_id)},
        "recursion_limit": 200,
    }
    app = build_graph(deps, checkpointer=checkpointer)
    before = app.get_state(lg_config)
    if before is None or not before.values:
        raise ValueError(f"checkpoint has no state for run {run_id}")

    _log(f"RESUME run_id={run_id} paper_id={paper_id}")
    # Wake the persisted final-review interrupt.  The wake ack is not an approval:
    # final_review_check re-reads items/*/review.yaml on every entry.  If reviews are
    # still pending the node interrupts again (outcome stays waiting_for_final_review);
    # only a complete fresh set of approved reviews routes on to approved_audit.
    _stream_once(app, Command(resume=_RESUME_WAKE_ACK), lg_config, "resume-final-review")
    final = app.get_state(lg_config)
    final_state = final.values if final is not None else {}
    _persist_state(layout, final_state)
    outcome = extract_outcome(final_state) if final_state else "failed"
    _log(f"FINAL outcome={outcome}")
    errors = final_state.get("terminal_errors") or []
    for error in errors:
        _log(f"  - {error}")
    if outcome in ("waiting_for_final_review", "running"):
        still_pending = bool(final and final.next)
        if still_pending:
            _log("  final review still pending — complete Review UI approvals and resume again")
        _log(f"  Review UI: {_review_ui_command(layout)}")
        _log(
            f"  resume again: {sys.executable} -m "
            "scripts.question_transcription.workflow.run_live_paper "
            f"--paper-id {paper_id} --resume-run-id {run_id}"
        )
    _log(f"layout={layout.root}")
    return run_id


def _persist_state(layout, state: WorkflowState) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    (layout.root / "state.json").write_text(
        __import__("json").dumps(dump_state(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run-live-paper")
    p.add_argument("--paper-id", required=True)
    p.add_argument("--source")
    p.add_argument(
        "--source-kind", choices=["doc", "docx", "pdf", "pages"]
    )
    p.add_argument(
        "--resume-run-id",
        help="resume an existing final-review checkpoint; --source is then omitted",
    )
    p.add_argument("--agent-host", default="claude-code", choices=["opencode", "claude-code"])
    p.add_argument("--page-provider", default="qwen", choices=["qwen", "mimo"])
    p.add_argument(
        "--final-review-mode",
        default="human",
        choices=["human", "auto"],
        help=(
            "human: stop after refreshing Review UI (default); "
            "auto: write complete approved review.yaml files for E2E verification"
        ),
    )
    # Langfuse tracing (optional). When all three are set, OTLP traces are exported
    # to the local/self-hosted Langfuse and the Claude Code CLI subprocess inherits
    # the same OTLP env so its LLM calls appear in the same trace tree.
    p.add_argument("--langfuse-host", default="http://localhost:3000")
    p.add_argument("--langfuse-public-key", default=None)
    p.add_argument("--langfuse-secret-key", default=None)
    args = p.parse_args(argv)
    if args.resume_run_id:
        if args.source or args.source_kind:
            p.error("--resume-run-id cannot be combined with --source/--source-kind")
        run_id = resume(
            paper_id=args.paper_id,
            run_id=args.resume_run_id,
            agent_host=args.agent_host,
            page_provider=args.page_provider,
        )
    else:
        if not args.source or not args.source_kind:
            p.error("a new run requires --source and --source-kind")
        run_id = run(
            paper_id=args.paper_id,
            source=str(Path(args.source).resolve()),
            source_kind=args.source_kind,
            agent_host=args.agent_host,
            page_provider=args.page_provider,
            final_review_mode=args.final_review_mode,
            langfuse_host=args.langfuse_host,
            langfuse_public_key=args.langfuse_public_key,
            langfuse_secret_key=args.langfuse_secret_key,
        )
    print(run_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
