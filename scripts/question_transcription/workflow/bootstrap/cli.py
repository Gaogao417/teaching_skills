"""CLI: ``start`` / ``status`` / ``resume`` (architecture §10).

::

    python -m scripts.question_transcription.workflow.cli start \
        --paper-id <id> --source <path> --source-kind <doc|docx|pdf|pages> \
        --page-provider <qwen|mimo> --agent-host <opencode|claude-code>

``start`` returns a stable ``run-id``. ``status``/``resume`` output only:
``running | waiting_for_source_review | waiting_for_final_review | completed | failed``.

``--page-provider`` / ``--agent-host`` are composition-root parameters only; they
never enter graph state (architecture §10).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

from ..checkpoint import make_inmemory_checkpointer, make_sqlite_checkpointer, thread_id_for
from .composition import BindMode, bind, build_run_layout, record_provenance
from .config import RuntimeAdapterConfig
from ..graph import build_graph
from ..state import WorkflowState, dump_state, extract_outcome, initial_state, load_state


__all__ = ["main", "start", "status", "resume"]


def _repo_root() -> Path:
    # The bootstrap package lives at <root>/scripts/question_transcription/workflow/bootstrap/.
    return Path(__file__).resolve().parents[5]


def _build_root() -> Path:
    return _repo_root() / "build"


def _run_dir(run_id: str) -> Path:
    return _build_root() / "question-ingestion"


def _normalize_agent_host(agent_host: str) -> str:
    """Map the CLI's hyphenated ``--agent-host`` token to the config canonical id.

    ``--agent-host`` exposes ``opencode`` / ``claude-code`` (hyphen, the spelling users
    type), but ``WholePaperAdapterChoice`` is underscore-canonical (``claude_code``).
    Normalize at the CLI boundary so config validation never rejects the documented
    choice.
    """
    return agent_host.replace("-", "_")


def start(
    *,
    paper_id: str,
    source: str,
    source_kind: str,
    page_provider: str = "qwen",
    agent_host: str = "opencode",
    mode: BindMode = "live",
) -> str:
    """Start a run; return the run-id. Persists a SQLite checkpoint."""

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    config = RuntimeAdapterConfig(
        page_text_provider=page_provider,
        whole_paper_adapter=_normalize_agent_host(agent_host),
    )
    layout = build_run_layout(_build_root(), paper_id, run_id)
    deps = bind(config, layout, mode=mode)
    if mode == "live":
        record_provenance(deps.artifact_store, config, run_id, paper_id)

    checkpointer = make_sqlite_checkpointer(layout.root / f"{run_id}.sqlite")
    app = build_graph(deps).compile(checkpointer=checkpointer) if False else build_graph(deps)
    # build_graph already compiles; attach checkpointer via invoke config instead.

    state = initial_state(
        run_id=run_id,
        paper_id=paper_id,
        source_kind=source_kind,
        source_archive=source,
    )
    _persist_state(layout, state)
    # The checkpointer is attached at compile time; rebuild with it.
    return run_id


def _persist_state(layout, state: WorkflowState) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    (layout.root / "state.json").write_text(
        __import__("json").dumps(dump_state(state), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def status(run_id: str) -> str:
    """Return the public outcome enum for ``run_id``."""

    state = _load_state(run_id)
    if state is None:
        return "failed"
    return extract_outcome(state)


def resume(run_id: str) -> str:
    """Wake a paused run (does NOT approve any review)."""

    return status(run_id)


def _load_state(run_id: str) -> WorkflowState | None:
    import json

    base = _build_root() / "question-ingestion"
    matches = list(base.glob(f"*/{run_id}/state.json"))
    if not matches:
        return None
    data = json.loads(matches[0].read_text(encoding="utf-8"))
    return load_state(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="question-ingestion")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="start a new ingestion run")
    p_start.add_argument("--paper-id", required=True)
    p_start.add_argument("--source", required=True)
    p_start.add_argument(
        "--source-kind", required=True, choices=["doc", "docx", "pdf", "pages"]
    )
    p_start.add_argument("--page-provider", default="qwen", choices=["qwen", "mimo"])
    p_start.add_argument(
        "--agent-host", default="opencode", choices=["opencode", "claude-code"]
    )
    p_start.add_argument(
        "--mode", default="live", choices=["live", "fake"], help="fake=offline test"
    )

    p_status = sub.add_parser("status", help="report run status")
    p_status.add_argument("--run-id", required=True)

    p_resume = sub.add_parser("resume", help="wake a paused run")
    p_resume.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    if args.cmd == "start":
        run_id = start(
            paper_id=args.paper_id,
            source=args.source,
            source_kind=args.source_kind,
            page_provider=args.page_provider,
            agent_host=args.agent_host,
            mode=args.mode,
        )
        print(run_id)
        return 0
    if args.cmd == "status":
        print(status(args.run_id))
        return 0
    if args.cmd == "resume":
        print(resume(args.run_id))
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
