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
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml
from langgraph.types import Command

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


# --------------------------------------------------------------------------- #
# Observability: one root observation per graph invocation (review #1/#2/#3).
# --------------------------------------------------------------------------- #
# The durable run is the Langfuse *session*; each real graph invocation
# (initial run vs. a human-triggered resume) is its own *trace* inside that
# session. A single process-internal auto-wake of an interrupt stays inside the
# ``initial`` trace — only a separate ``resume()`` entry point opens a new
# ``human-resume`` trace. This keeps ``root observation count ≈ graph invocation
# count`` instead of ``≈ node + LLM + tool call count``.
#
# The context manager opens the root ``operation`` (which propagates trace-level
# session/tags/name into the OTel context BEFORE creating the observation, so the
# nested CallbackHandler node observations and adapter generations inherit them)
# and builds the LangGraph runnable config with the CallbackHandler created
# inside that root context (review #3). ``flush()`` runs in ``finally`` so a
# mid-phase exception still exports whatever was collected.


@contextmanager
def _phase_root(*, run_id, paper_id, thread_id, phase):
    """Yield ``(config, root_obs)`` for one graph invocation's trace.

    ``config`` is a fresh LangGraph runnable config carrying the Langfuse
    ``CallbackHandler`` and phase-bound metadata; callers pass it to
    ``app.stream``/``app.get_state``. ``root_obs`` is the root observation (a
    no-op when Langfuse is disabled) the caller may ``.update(output=...)``.
    """
    base_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 200,
    }
    # Trace-level metadata attached to the CallbackHandler root observation.
    config = {
        **base_config,
        "callbacks": _lf.graph_callbacks(),
        "run_name": f"question-ingestion.{phase}:{paper_id}",
        "metadata": {
            "langfuse_session_id": run_id,
            "langfuse_tags": ["question-ingestion"],
            "paper_id": paper_id,
            "run_id": run_id,
            "phase": phase,
        },
    }
    with _lf.operation(
        f"paper-ingestion.{phase}",
        input={"paper_id": paper_id, "phase": phase},
        metadata={
            "paper_id": paper_id,
            "run_id": run_id,
            "langgraph_thread_id": thread_id,
            "phase": phase,
        },
        session_id=run_id,
        tags=["question-ingestion"],
        trace_name=f"question-ingestion:{run_id}:{phase}",
    ) as root:
        try:
            yield config, root
        finally:
            _lf.flush()


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
    answer_source: str | None = None,
) -> str:
    if final_review_mode not in {"human", "auto"}:
        raise ValueError("final_review_mode must be 'human' or 'auto'")
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
    app = build_graph(deps, checkpointer=checkpointer)

    state = initial_state(
        run_id=run_id,
        paper_id=paper_id,
        source_kind=source_kind,
        source_archive=source,
        answer_archive=answer_source,
    )
    _persist_state(layout, state)
    _log(f"START run_id={run_id} paper_id={paper_id} kind={source_kind}")
    _log(f"      source={source}")
    if answer_source:
        _log(f"      answer_source={answer_source}")
    _log(f"      layout={layout.root}")
    _log(f"      agent={agent_host} page={page_provider}")
    _log(f"      langfuse: {'enabled' if _lf.is_enabled() else 'disabled'}")

    # One root observation for the whole ``initial`` invocation: every auto-wake
    # of an interrupt inside this process stays in the same trace, and node spans
    # (CallbackHandler) + adapter generations nest under it via the shared OTel
    # context. ``_phase_root`` owns the operation, the callbacks-bearing config,
    # and ``flush()`` in ``finally`` (review #1/#2/#3).
    payload: Any = state
    final_state: dict[str, Any] = {}
    with _phase_root(
        run_id=run_id, paper_id=paper_id, thread_id=thread, phase="initial",
    ) as (lg_config, _root):
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
        # Give the root observation a meaningful output (best-practices baseline:
        # a trace's root should carry input/output so it is readable in the UI).
        # resume() sets the same shape; initial previously set none.
        _root.update(output={
            "outcome": extract_outcome(final_state) if final_state else "failed",
            "waiting_nodes": list(final.next) if final is not None else [],
            "terminal_errors": (final_state.get("terminal_errors", []) if final_state else []),
        })

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
    thread = thread_id_for(run_id)
    # Pre-check the checkpoint with a bare config (no tracing) before opening the
    # ``human-resume`` root observation — a missing state is a hard error and
    # should not produce a trace.
    probe_config = {"configurable": {"thread_id": thread}, "recursion_limit": 200}
    app = build_graph(deps, checkpointer=checkpointer)
    before = app.get_state(probe_config)
    if before is None or not before.values:
        raise ValueError(f"checkpoint has no state for run {run_id}")

    _log(f"RESUME run_id={run_id} paper_id={paper_id}")
    _log(f"      langfuse: {'enabled' if _lf.is_enabled() else 'disabled'}")
    # The human-triggered resume is its own trace inside the same session
    # (run_id) as the initial run: a separate ``human-resume`` root observation
    # so post-review node spans/generations are actually traced (previously
    # ``resume()`` had no tracing at all — review #2).
    with _phase_root(
        run_id=run_id, paper_id=paper_id, thread_id=thread, phase="human-resume",
    ) as (lg_config, root):
        # Wake the persisted final-review interrupt.  The wake ack is not an approval:
        # final_review_check re-reads items/*/review.yaml on every entry.  If reviews are
        # still pending the node interrupts again (outcome stays waiting_for_final_review);
        # only a complete fresh set of approved reviews routes on to approved_audit.
        _stream_once(app, Command(resume=_RESUME_WAKE_ACK), lg_config, "resume-final-review")
        final = app.get_state(lg_config)
        final_state = final.values if final is not None else {}
        root.update(output={
            "outcome": extract_outcome(final_state) if final_state else "failed",
            "waiting_nodes": list(final.next) if final is not None else [],
            "terminal_errors": (final_state.get("terminal_errors", []) if final_state else []),
        })
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
    p.add_argument(
        "--answer-source",
        help=(
            "optional supplementary official-answer DOCX whose rendered pages "
            "continue the paper's page numbering (for question-only exam "
            "archives such as 2020-MINHANG-YIMO)"
        ),
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
    # Langfuse tracing is configured via environment variables only
    # (LANGFUSE_BASE_URL/PUBLIC_KEY/SECRET_KEY); see AGENTS.md.
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
            answer_source=(
                str(Path(args.answer_source).resolve()) if args.answer_source else None
            ),
        )
    print(run_id)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
