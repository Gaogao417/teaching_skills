#!/usr/bin/env python3
"""FastAPI review service for SkillTraceDraft JSON."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError

try:
    from .db import get_draft, get_review, insert_review, resolve_db_path
except ImportError:  # pragma: no cover - supports direct script execution.
    from db import get_draft, get_review, insert_review, resolve_db_path


PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    codex_thread_id: str
    reviewed_json: dict[str, Any]
    reviewer_note: str = ""


def create_app(
    db_path: str | Path | None = None,
    draft_payloads: dict[str, dict[str, Any]] | None = None,
) -> FastAPI:
    resolved_db_path = resolve_db_path(db_path)
    in_memory_drafts = draft_payloads or {}
    app = FastAPI(title="Skill Trace Review", version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/review/{draft_id}")
    def review_page(draft_id: str) -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "review.html", media_type="text/html")

    @app.get("/api/drafts/{draft_id}")
    def api_get_draft(draft_id: str) -> dict[str, Any]:
        if draft_id in in_memory_drafts:
            draft_json = in_memory_drafts[draft_id]
            return {
                "draft_id": draft_id,
                "problem_case_id": f"case_{draft_id}",
                "codex_thread_id": draft_json["codex_thread_id"],
                "created_at": "",
                "draft_json": draft_json,
                "source": "memory",
            }
        try:
            return get_draft(draft_id, db_path=resolved_db_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, sqlite3.Error) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/reviews")
    def api_submit_review(submission: ReviewSubmission) -> dict[str, Any]:
        try:
            return submit_review_payload(
                submission.model_dump(),
                db_path=resolved_db_path,
                original_draft_json=in_memory_drafts.get(submission.draft_id),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, ValidationError, sqlite3.Error) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/reviews/{reviewed_trace_id}")
    def api_get_review(reviewed_trace_id: str) -> dict[str, Any]:
        try:
            return get_review(reviewed_trace_id, db_path=resolved_db_path)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, sqlite3.Error) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def submit_review_payload(
    payload: dict[str, Any],
    db_path: str | Path | None = None,
    original_draft_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    draft_id = _required_text(payload, "draft_id")
    codex_thread_id = _required_text(payload, "codex_thread_id")
    reviewed_json = payload.get("reviewed_json")
    if not isinstance(reviewed_json, dict):
        raise ValueError("reviewed_json must be an object")
    if reviewed_json.get("draft_id") != draft_id:
        raise ValueError("reviewed_json.draft_id must match draft_id")
    if reviewed_json.get("codex_thread_id") != codex_thread_id:
        raise ValueError("reviewed_json.codex_thread_id must match codex_thread_id")

    reviewer_note = payload.get("reviewer_note", "")
    if reviewer_note is None:
        reviewer_note = ""
    if not isinstance(reviewer_note, str):
        raise ValueError("reviewer_note must be a string")

    return insert_review(
        draft_id=draft_id,
        reviewed_json=reviewed_json,
        original_draft_json=original_draft_json,
        reviewer_note=reviewer_note,
        db_path=db_path,
    )


def run_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: str | Path | None = None,
    draft_payloads: dict[str, dict[str, Any]] | None = None,
) -> None:
    uvicorn.run(create_app(db_path=db_path, draft_payloads=draft_payloads), host=host, port=port, log_level="info")


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)

    run_server(host=args.host, port=args.port, db_path=args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
