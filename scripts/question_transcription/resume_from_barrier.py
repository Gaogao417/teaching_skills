#!/usr/bin/env python3
"""Resume a terminal E-class run past the page-text barrier to staging.

An E-class run died at ``page_barrier`` (a handful of pages hit transient OCR
errors) and reached END. After :mod:`retry_page_text` fills the missing pages and
clears ``state.json``, the run is fully unblocked at the page-text layer but has
*never* run the downstream stages — there is no whole-paper transcription, no
source paper, no draft, and no staging.

This command replays the downstream node chain manually, reading the run's
LangGraph checkpoint for the frozen pre-barrier state (``extracted_source``,
``page_text_jobs``, ``image_attribution``) and merging in the page-text extracts
committed by :mod:`retry_page_text`. It then drives the node chain directly:

    transcribe_whole_paper -> build_source_paper -> build_draft ->
    complete_evidence -> split -> build_assets -> audit -> refresh_review_ui

Nodes are plain functions that take a state dict and return an update dict, so the
chain avoids both the append-only ``terminal_errors`` reducer (which would
otherwise keep the stale page-extraction error) and the final-review interrupt
(which would pause a normal graph run). A source-review interrupt
(``review_state == waiting_for_source_review``) still surfaces as ``blocked``:
that gate is a real human-in-the-loop checkpoint and is not bypassed.

Unlike :mod:`recover_failed_runs` (which only replays build_draft onward and
needs an existing source paper), this command starts at whole-paper
transcription and therefore calls the whole-paper LLM agent
(``--agent-host opencode|claude-code``).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from scripts.question_transcription.workflow.bootstrap.composition import (
    bind,
    build_run_layout,
)
from scripts.question_transcription.workflow.bootstrap.config import (
    RuntimeAdapterConfig,
)
from scripts.question_transcription.workflow.bootstrap.dependencies import (
    WorkflowDependencies,
)
from scripts.question_transcription.workflow.checkpoint import (
    make_sqlite_checkpointer,
    thread_id_for,
)
from scripts.question_transcription.workflow.nodes.downstream import (
    make_audit_staging_node,
    make_build_assets_node,
    make_build_draft_node,
    make_complete_evidence_node,
    make_refresh_review_ui_node,
    make_split_into_questions_node,
)
from scripts.question_transcription.workflow.nodes.source import (
    make_build_source_paper_node,
)
from scripts.question_transcription.workflow.nodes.whole_paper import (
    make_transcribe_whole_paper_node,
)
from scripts.question_transcription.workflow.run_live_paper import _build_root


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNS_ROOT = REPO_ROOT / "build" / "question-ingestion"


@dataclass
class ResumeResult:
    paper_id: str
    run_id: str
    status: str
    stages: list[dict[str, Any]] = field(default_factory=list)
    detail: str | None = None


def _load_checkpoint_state(layout) -> dict[str, Any]:
    """Read the frozen pre-barrier state from the run's LangGraph checkpoint.

    The checkpoint (``<run-id>.sqlite``) holds the state as of the last node
    write before the run reached END. Its ``channel_values`` are exactly what the
    downstream nodes expect as input, minus the page-text extracts (which were
    incomplete at the time the barrier failed).
    """
    checkpoint_path = layout.root / f"{layout.run_id}.sqlite"
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"checkpoint not found: {checkpoint_path}")
    saver = make_sqlite_checkpointer(checkpoint_path)
    tup = saver.get_tuple(
        {"configurable": {"thread_id": thread_id_for(layout.run_id)}}
    )
    if tup is None or not tup.checkpoint.get("channel_values"):
        raise ValueError(f"checkpoint has no state for run {layout.run_id}")
    return dict(tup.checkpoint["channel_values"])


def _build_nodes(deps: WorkflowDependencies) -> list[tuple[str, Callable]]:
    """The downstream node chain as (name, fn) pairs."""
    return [
        ("transcribe_whole_paper", make_transcribe_whole_paper_node(deps)),
        ("build_source_paper", make_build_source_paper_node(deps)),
        ("build_draft", make_build_draft_node(deps)),
        ("complete_evidence", make_complete_evidence_node(deps)),
        ("split_into_questions", make_split_into_questions_node(deps)),
        ("build_assets", make_build_assets_node(deps)),
        ("audit_staging", make_audit_staging_node(deps)),
        ("refresh_review_ui", make_refresh_review_ui_node(deps)),
    ]


def _apply(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge a node's return value into the running state.

    ``terminal_errors`` is the terminal signal: if a node emits it, the chain
    stops. Every other key replaces the existing value (mirroring how a node
    update overwrites that channel). Page-text extracts/failures are never
    re-emitted downstream, so there is no append semantics to preserve here.
    """
    if update.get("terminal_errors"):
        state["terminal_errors"] = update["terminal_errors"]
        return state
    for key, value in update.items():
        state[key] = value
    return state


def resume_one(
    layout,
    *,
    agent_host: str,
    page_provider: str,
    apply: bool,
    mode: str = "live",
) -> ResumeResult:
    result = ResumeResult(
        paper_id=layout.paper_id, run_id=layout.run_id, status="running"
    )

    # Merge checkpoint state with the page-text extracts that retry_page_text
    # committed to state.json (the checkpoint still holds the incomplete set).
    try:
        state = _load_checkpoint_state(layout)
    except (FileNotFoundError, ValueError) as exc:
        result.status = "blocked"
        result.detail = f"checkpoint: {exc}"
        return result
    state_path = layout.root / "state.json"
    if not state_path.is_file():
        result.status = "blocked"
        result.detail = "state.json missing (run retry_page_text first)"
        return result
    state_json = json.loads(state_path.read_text(encoding="utf-8"))
    state["page_text_extracts"] = state_json.get("page_text_extracts") or []
    state["page_text_failures"] = []
    state["terminal_errors"] = []

    config = RuntimeAdapterConfig(
        page_text_provider=page_provider,
        whole_paper_adapter=agent_host.replace("-", "_"),
    )
    deps = bind(config, layout, mode=mode)
    nodes = _build_nodes(deps)

    if not apply:
        for name, _fn in nodes:
            result.stages.append({"node": name, "status": "planned"})
        result.status = "dry-run"
        return result

    for name, node in nodes:
        try:
            update = node(state)
        except Exception as exc:  # surface the failing node, not a stack trace
            result.stages.append(
                {"node": name, "status": "failed", "failure": f"{type(exc).__name__}: {exc}"}
            )
            result.status = "blocked"
            result.detail = f"{name}: {type(exc).__name__}: {exc}"
            return result
        state = _apply(state, update)
        if state.get("terminal_errors"):
            err = state["terminal_errors"][0]
            result.stages.append({"node": name, "status": "failed", "failure": err})
            result.status = "blocked"
            result.detail = f"{name}: {err}"
            return result
        # A source-paper review interrupt is a real human gate; stop and report.
        if state.get("review_state") == "waiting_for_source_review":
            result.stages.append(
                {"node": name, "status": "waiting_for_source_review"}
            )
            result.status = "blocked"
            result.detail = (
                f"{name}: source paper has review issues; resolve them in the "
                "Review UI and re-run"
            )
            return result
        result.stages.append({"node": name, "status": "passed"})

    result.status = "resumed"
    return result


def _run_inventory(runs_root: Path) -> list[tuple[str, str, Path]]:
    """E-class runs whose page-text barrier is now clear (state.json has no errors)."""
    out: list[tuple[str, str, Path]] = []
    for state_path in sorted(runs_root.glob("*/*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not state.get("page_text_jobs"):
            continue
        if state.get("terminal_errors"):
            continue  # still failing (retry_page_text not run / incomplete)
        run_dir = state_path.parent
        out.append(
            (
                str(state.get("paper_id") or run_dir.parent.name),
                str(state.get("run_id") or run_dir.name),
                run_dir,
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--agent-host",
        choices=("opencode", "claude-code"),
        default="claude-code",
        help="whole-paper transcription agent (claude-code=glm-5.2 via claude CLI default, opencode=glm-5.2 via opencode server)",
    )
    parser.add_argument(
        "--page-provider",
        choices=("qwen", "mimo"),
        default="mimo",
        help="page-text provider label recorded for provenance (no re-OCR happens here)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="drive the node chain; without it, only list eligible runs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="concurrent run workers (each drives an independent claude-code agent session)",
    )
    args = parser.parse_args(argv)

    runs_root = args.runs_root.resolve()
    build_root = runs_root.parent
    candidates = _run_inventory(runs_root)
    if args.paper_id:
        wanted = set(args.paper_id)
        candidates = [c for c in candidates if c[0] in wanted]
    if args.limit is not None:
        candidates = candidates[: args.limit]

    if not args.apply:
        for paper_id, run_id, run_dir in candidates:
            ckpt = run_dir / f"{run_id}.sqlite"
            print(
                f"DRY-RUN {paper_id} {run_id} checkpoint={'yes' if ckpt.is_file() else 'NO'}"
            )
        print(f"SUMMARY eligible={len(candidates)} (pass --apply to resume)")
        return 0

    from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: PLC0415

    def _run(candidate):
        paper_id, run_id, _run_dir = candidate
        layout = build_run_layout(build_root, paper_id, run_id)
        return resume_one(
            layout,
            agent_host=args.agent_host,
            page_provider=args.page_provider,
            apply=True,
        )

    resumed = blocked = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_run, c): c for c in candidates}
        for future in as_completed(futures):
            candidate = futures[future]
            paper_id, run_id, _run_dir = candidate
            result = future.result()
            if result.status == "resumed":
                resumed += 1
            else:
                blocked += 1
            detail = f" :: {result.detail}" if result.detail else ""
            print(f"{result.status.upper()} {paper_id} {run_id}{detail}", flush=True)
            for stage in result.stages:
                mark = {"passed": "OK", "failed": "XX", "planned": ".."}.get(
                    stage["status"], stage["status"][:2]
                )
                extra = f" :: {stage.get('failure')}" if stage.get("failure") else ""
                print(f"  [{mark}] {stage['node']}{extra}", flush=True)

    print(
        f"SUMMARY resumed={resumed} blocked={blocked} agent={args.agent_host} "
        f"workers={args.workers}"
    )
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
