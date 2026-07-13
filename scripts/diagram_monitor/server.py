#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from .human_review import HumanReviewService, ReviewConflict, RevisionRunner
    from .scanner import DiagramArtifactScanner
except ImportError:  # pragma: no cover - direct script execution
    from human_review import HumanReviewService, ReviewConflict, RevisionRunner
    from scanner import DiagramArtifactScanner


PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"


class HumanReviewSubmission(BaseModel):
    folder: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    decision: Literal["accepted", "changes_requested"]
    feedback: str = ""
    base_round: int | None = Field(default=None, ge=0)


def create_app(
    artifacts_root: str | Path | None = None,
    revision_runner: RevisionRunner | None = None,
) -> FastAPI:
    resolved_root = Path(artifacts_root or REPO_ROOT / "artifacts").expanduser().resolve()
    scanner = DiagramArtifactScanner(resolved_root)
    review_service = HumanReviewService(resolved_root, REPO_ROOT, runner=revision_runner)
    app = FastAPI(title="Diagram Pipeline Monitor", version="0.1.0")
    app.state.artifacts_root = resolved_root
    app.state.scanner = scanner
    app.state.review_service = review_service
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def monitor_page() -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "index.html", media_type="text/html")

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"ok": True, "artifacts_root": str(resolved_root)}

    @app.get("/api/folders")
    def list_folders(
        query: str = "",
        status: str = "",
        problems_only: bool = False,
        limit: int = Query(default=80, ge=1, le=250),
    ) -> dict[str, Any]:
        items = scanner.search(query, status=status, problems_only=problems_only, limit=limit)
        return {"items": items, "count": len(items), "artifacts_root": str(resolved_root)}

    @app.get("/api/folder")
    def folder_detail(path: str) -> dict[str, Any]:
        try:
            return scanner.folder_detail(path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/job")
    def job_detail(folder: str, job_id: str) -> dict[str, Any]:
        try:
            detail = scanner.job_detail(folder, job_id)
            detail["human_review"] = review_service.current(scanner.resolve_job_dir(folder, job_id))
            return detail
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/human-review", status_code=202)
    def submit_human_review(
        submission: HumanReviewSubmission,
        background_tasks: BackgroundTasks,
        response: Response,
    ) -> dict[str, Any]:
        try:
            record, replayed, request_path, request = review_service.submit(
                folder=submission.folder,
                job_id=submission.job_id,
                action_id=submission.action_id,
                decision=submission.decision,
                feedback=submission.feedback,
                base_round=submission.base_round,
            )
            if submission.decision == "accepted" or replayed:
                response.status_code = 200
            if request_path is not None and request is not None:
                background_tasks.add_task(
                    review_service.run_revision,
                    job_dir=scanner.resolve_job_dir(submission.folder, submission.job_id),
                    request_path=request_path,
                    request=request,
                    review_id=record["review_id"],
                )
            return record
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ReviewConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            message = str(exc)
            raise HTTPException(status_code=422 if "修改建议" in message else 400, detail=message) from exc

    @app.get("/api/content")
    def artifact_content(folder: str, path: str) -> dict[str, Any]:
        try:
            return scanner.read_text(folder, path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/file")
    def artifact_file(folder: str, path: str) -> FileResponse:
        try:
            resolved = scanner.resolve_file(folder, path)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse(resolved)

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local diagram pipeline review and monitor console")
    parser.add_argument("--artifacts-root", type=Path, default=REPO_ROOT / "artifacts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args(argv)
    uvicorn.run(create_app(args.artifacts_root), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
