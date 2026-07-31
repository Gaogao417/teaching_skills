#!/usr/bin/env python3
"""Live end-to-end driver for the LangGraph question-ingestion workflow.

Runs ONE real paper through the compiled graph with real adapters:

- page text: qwen3.5-ocr (DASHSCOPE_API_KEY from environment)
- whole paper: claude-code glm-5.2 (claude CLI + GLM anthropic gateway)

Why this script exists: ``bootstrap.cli.start`` only persists ``state.json``; it never
invokes the graph. To verify the LangGraph workflow on a real paper we must compile
the graph with a checkpointer, ``stream`` it, and drive the two human-in-the-loop
interrupts (source review + final review) to completion.

Auto-approval policy (for this verification run only):
- source review: write ``review/review-resolutions.yaml`` acknowledging all issues;
- final review: write ``status: approved`` into every ``items/*/review.yaml``.

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
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

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
    return Path(__file__).resolve().parents[5]


def _build_root() -> Path:
    return _repo_root() / "build"


def _ts() -> str:
    return _dt.datetime.now().strftime("%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


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
    """Write status: approved into every items/*/review.yaml; return count."""

    staging = Path(staging_directory)
    items_dir = staging / "items"
    if not items_dir.is_dir():
        return 0
    n = 0
    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    for item_dir in sorted(items_dir.iterdir()):
        if not item_dir.is_dir():
            continue
        review = item_dir / "review.yaml"
        doc: dict[str, Any] = {}
        if review.exists():
            doc = yaml.safe_load(review.read_text(encoding="utf-8")) or {}
        doc.setdefault("schema", "math_exam_item_review/v1")
        doc.setdefault("item_id", item_dir.name)
        doc["status"] = "approved"
        doc.setdefault("reviewer", "live-verification-driver")
        doc["reviewed_at"] = now
        review.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        n += 1
    _log(f"  final review: approved {n} item(s) under {items_dir}")
    return n


def _stream_once(app, payload, config, label) -> dict[str, Any] | None:
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
                        _attach_state(span, "output", delta)
                        # The input is the state before this node ran.
                        _attach_state(span, "input", _input_view(prev_state))
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


def _attach_state(span, prefix: str, state: dict[str, Any]) -> None:
    """Attach a redacted, size-bounded state projection to a span.

    Langfuse renders an observation's INPUT/OUTPUT from specific attributes
    (``langfuse.observation.input`` / ``langfuse.observation.output``), not from
    arbitrary ``prefix.key`` attributes. So we serialize the whole projection to one
    JSON string and set it on the recognized attribute, so the node's input state
    and output delta are visible in the UI's Input/Output panels.
    """

    if span is None or not state:
        return
    attr = (
        "langfuse.observation.input" if prefix == "input" else "langfuse.observation.output"
    )
    projection = {k: _simplify(v) for k, v in state.items()}
    try:
        import json

        span.set_attribute(attr, _truncate(json.dumps(projection, ensure_ascii=False)))
    except Exception:
        pass


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


def _truncate(s: str, n: int = 2000) -> str:
    return s if len(s) <= n else s[:n] + f"…<+{len(s) - n} chars>"


def run(
    *,
    paper_id: str,
    source: str,
    source_kind: str,
    agent_host: str = "claude-code",
    page_provider: str = "qwen",
    max_resume_rounds: int = 6,
    langfuse_host: str | None = None,
    langfuse_public_key: str | None = None,
    langfuse_secret_key: str | None = None,
) -> str:
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
        result = _stream_once(app, payload, lg_config, f"round{rnd}")
        elapsed = time.time() - t0
        gs = app.get_state(lg_config)
        outcome = extract_outcome(gs.values or {}) if gs and gs.values else "running"
        next_interrupts = gs.next if gs is not None else ()
        _log(
            f"  round{rnd} done in {elapsed:.1f}s -> outcome={outcome} next={list(next_interrupts)}"
        )
        if outcome in ("completed", "failed"):
            break
        # Handle interrupts: write the approval artifacts, then resume with None
        # (resume only WAKES; approval is already on disk per design §16.8).
        resumed_something = False
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
                    if staging:
                        _approve_final_review(staging)
                    resumed_something = True
        if not resumed_something and outcome == "running" and not next_interrupts:
            _log("  no interrupt to resume and graph idle; stopping.")
            break
        payload = None  # subsequent passes resume the existing thread

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


def _persist_state(layout, state: WorkflowState) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    (layout.root / "state.json").write_text(
        __import__("json").dumps(dump_state(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="run-live-paper")
    p.add_argument("--paper-id", required=True)
    p.add_argument("--source", required=True)
    p.add_argument(
        "--source-kind", required=True, choices=["doc", "docx", "pdf", "pages"]
    )
    p.add_argument("--agent-host", default="claude-code", choices=["opencode", "claude-code"])
    p.add_argument("--page-provider", default="qwen", choices=["qwen", "mimo"])
    # Langfuse tracing (optional). When all three are set, OTLP traces are exported
    # to the local/self-hosted Langfuse and the Claude Code CLI subprocess inherits
    # the same OTLP env so its LLM calls appear in the same trace tree.
    p.add_argument("--langfuse-host", default="http://localhost:3000")
    p.add_argument("--langfuse-public-key", default=None)
    p.add_argument("--langfuse-secret-key", default=None)
    args = p.parse_args(argv)
    run_id = run(
        paper_id=args.paper_id,
        source=str(Path(args.source).resolve()),
        source_kind=args.source_kind,
        agent_host=args.agent_host,
        page_provider=args.page_provider,
        langfuse_host=args.langfuse_host,
        langfuse_public_key=args.langfuse_public_key,
        langfuse_secret_key=args.langfuse_secret_key,
    )
    print(run_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
