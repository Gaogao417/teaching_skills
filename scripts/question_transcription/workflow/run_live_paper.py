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
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

from .bootstrap.composition import BindMode, bind, build_run_layout, record_provenance
from .bootstrap.config import RuntimeAdapterConfig
from .checkpoint import make_sqlite_checkpointer, thread_id_for
from .graph import build_graph
from .observability import langfuse as _lf
from .orchestration.langgraph.state import (
    WorkflowState,
    dump_state,
    extract_outcome,
    initial_state,
)


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
    """Run one stream pass and print node updates.

    Node-level tracing is produced automatically by the Langfuse
    ``CallbackHandler`` carried in ``config["callbacks"]``; we no longer wrap
    each chunk in a hand-rolled span. Per-node input/output is bounded by the
    wrapper's ``mask_otel_spans`` hook rather than projected here.
    """

    last_state: dict[str, Any] | None = None
    try:
        for chunk in app.stream(payload, config=config, stream_mode="updates"):
            # chunk is {node_name: state_delta} under stream_mode="updates".
            for node, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue
                keys = [k for k in delta.keys() if k not in ("run_id", "paper_id")]
                _log(f"  [{label}] node={node} -> {sorted(keys)}")
    except Exception as exc:  # surface real failures (adapter/model/contract)
        _log(f"  [{label}] STREAM ERROR: {type(exc).__name__}: {exc}")
        raise
    state = app.get_state(config)
    if state is not None:
        last_state = state.values or {}
    return last_state


def run(
    *,
    paper_id: str,
    source: str,
    source_kind: str,
    agent_host: str = "claude-code",
    page_provider: str = "qwen",
    max_resume_rounds: int = 6,
) -> str:
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    config = RuntimeAdapterConfig(
        page_text_provider=page_provider,
        whole_paper_adapter=agent_host.replace("-", "_"),
    )
    layout = build_run_layout(_build_root(), paper_id, run_id)
    deps = bind(config, layout, mode="live")
    record_provenance(deps.artifact_store, config, run_id, paper_id)

    checkpointer = make_sqlite_checkpointer(layout.root / f"{run_id}.sqlite")
    thread = thread_id_for(run_id)
    # Langfuse callbacks are injected here. When unconfigured (no LANGFUSE_*
    # env), graph_callbacks() returns [] and the config is identical to the
    # pre-tracing baseline. Trace-level attributes (session/tags/name) are set
    # both here (for the CallbackHandler root) and inside operation() below.
    lg_config = {
        "configurable": {"thread_id": thread},
        "recursion_limit": 200,
        "callbacks": _lf.graph_callbacks(),
        "run_name": f"question-ingestion:{paper_id}",
        "metadata": {
            "langfuse_session_id": paper_id,
            "langfuse_tags": ["question-ingestion"],
            "paper_id": paper_id,
        },
    }
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
    _log(f"      langfuse: {'enabled' if _lf.is_enabled() else 'disabled'}")

    # The whole run is one root observation; node observations created by the
    # CallbackHandler and the per-LLM generations created by adapters nest
    # under it via the shared OTel context. flush() in finally so a mid-run
    # exception still flushes whatever was collected — but a flush failure must
    # not mask the real error, so it is caught inside the wrapper.
    payload: Any = state
    try:
        with _lf.operation(
            "paper-ingestion",
            input={"paper_id": paper_id, "source_kind": source_kind},
            metadata={"paper_id": paper_id, "thread_id": thread},
            session_id=paper_id,
            tags=["question-ingestion"],
            trace_name=f"question-ingestion:{paper_id}",
        ):
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
    finally:
        _lf.flush()

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
    args = p.parse_args(argv)
    run_id = run(
        paper_id=args.paper_id,
        source=str(Path(args.source).resolve()),
        source_kind=args.source_kind,
        agent_host=args.agent_host,
        page_provider=args.page_provider,
    )
    print(run_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
