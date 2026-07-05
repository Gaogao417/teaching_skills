#!/usr/bin/env python3
"""Validate a SkillTraceDraft and open the local review UI."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import uuid
import webbrowser
from pathlib import Path
from typing import Any

from pydantic import ValidationError

try:
    from .contracts import SkillTraceDraft, prune_deprecated_step_fields
    from .review_server import run_server
except ImportError:  # pragma: no cover - supports direct script execution.
    from contracts import SkillTraceDraft, prune_deprecated_step_fields
    from review_server import run_server


MANUAL_THREAD_PREFIX = "manual_"
MANUAL_THREAD_WARNING = "非真实 Codex thread id：当前 codex_thread_id 由本地工具生成。"


def prepare_review(
    *,
    draft_path: Path,
    codex_thread_id: str | None = None,
    db_path: str | Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> dict[str, Any]:
    draft, is_manual_thread_id = load_review_draft(draft_path=draft_path, codex_thread_id=codex_thread_id)
    review_url = f"http://{host}:{port}/review/{draft.draft_id}"
    result = {
        "status": "review_ui_ready",
        "review_url": review_url,
        "codex_thread_id": draft.codex_thread_id,
        "draft_id": draft.draft_id,
    }
    if is_manual_thread_id:
        result["warnings"] = [MANUAL_THREAD_WARNING]
    return result


def load_review_draft(*, draft_path: Path, codex_thread_id: str | None = None) -> tuple[SkillTraceDraft, bool]:
    payload = _load_json_file(draft_path)
    resolved_thread_id, is_manual_thread_id = _resolve_codex_thread_id(payload, codex_thread_id)
    payload["codex_thread_id"] = resolved_thread_id
    payload = prune_deprecated_step_fields(payload)
    draft = SkillTraceDraft.model_validate(payload)
    return draft, is_manual_thread_id


def _resolve_codex_thread_id(payload: dict[str, Any], codex_thread_id: str | None) -> tuple[str, bool]:
    if codex_thread_id and codex_thread_id.strip():
        return codex_thread_id.strip(), False

    payload_thread_id = payload.get("codex_thread_id")
    if isinstance(payload_thread_id, str) and payload_thread_id.strip():
        return payload_thread_id.strip(), payload_thread_id.strip().startswith(MANUAL_THREAD_PREFIX)

    return f"{MANUAL_THREAD_PREFIX}{uuid.uuid4().hex[:12]}", True


def _load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--codex-thread-id", default=None)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Validate the draft without starting the server")
    args = parser.parse_args(argv)

    try:
        draft, is_manual_thread_id = load_review_draft(draft_path=args.draft, codex_thread_id=args.codex_thread_id)
    except (OSError, ValueError, ValidationError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1

    result = {
        "status": "review_ui_ready",
        "review_url": f"http://{args.host}:{args.port}/review/{draft.draft_id}",
        "codex_thread_id": draft.codex_thread_id,
        "draft_id": draft.draft_id,
    }
    if is_manual_thread_id:
        result["warnings"] = [MANUAL_THREAD_WARNING]

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()

    if args.prepare_only:
        return 0

    if not args.no_browser:
        threading.Timer(0.2, webbrowser.open, args=(result["review_url"],)).start()

    try:
        run_server(
            host=args.host,
            port=args.port,
            db_path=args.db,
            draft_payloads={draft.draft_id: draft.model_dump(mode="json")},
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
