#!/usr/bin/env python3
"""FastAPI server for explanation and assignment review UIs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from review_ui_common import (
    assert_template,
    clone_data,
    compile_tex,
    dump_assignment,
    load_assignment,
    preview_tex_path,
    public_path,
    render_data,
    reviewed_path,
    summarize_sections,
    validate_data,
    write_agent_request,
)


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR / "review_templates"
STATIC_DIR = SCRIPT_DIR / "review_static"


def create_explanation_app(yaml_path: Path) -> FastAPI:
    source = yaml_path.resolve()
    data = load_assignment(source)
    assert_template(data, "exam-zh-explanation", source)
    app = _base_app("Explanation Review")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "explanation_review.html", media_type="text/html")

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return {
            "mode": "explanation",
            "source_path": str(source),
            "reviewed_path": str(reviewed_path(source)),
            "data": clone_data(data),
            "sections": summarize_sections(data),
        }

    @app.post("/api/save")
    def save(payload: dict[str, Any]) -> dict[str, Any]:
        target_data = _required_mapping(payload, "data")
        overwrite = bool(payload.get("overwrite"))
        target = source if overwrite else reviewed_path(source)
        dump_assignment(target, target_data)
        return {"status": "saved", "path": str(target), "display_path": public_path(target)}

    @app.post("/api/validate")
    def validate(payload: dict[str, Any]) -> dict[str, Any]:
        return validate_data(_required_mapping(payload, "data"), base_dir=source.parent)

    @app.post("/api/render")
    def render(payload: dict[str, Any]) -> dict[str, Any]:
        out = preview_tex_path(source, "explanation")
        return render_data(_required_mapping(payload, "data"), source_path=source, out_path=out)

    @app.post("/api/compile")
    def compile_current(payload: dict[str, Any]) -> dict[str, Any]:
        tex_path = Path(_required_text(payload, "tex_path")).resolve()
        return compile_tex(tex_path)

    @app.post("/api/agent-request")
    def agent_request(payload: dict[str, Any]) -> dict[str, Any]:
        path = write_agent_request(
            mode="explanation",
            artifact_dir=source.parent,
            source_paths={"explanation": str(source)},
            selection=payload.get("selection") if isinstance(payload.get("selection"), dict) else {},
            instruction=_required_text(payload, "instruction"),
        )
        return {"status": "saved", "path": str(path), "display_path": public_path(path)}

    return app


def create_assignment_app(student_path: Path, teacher_path: Path | None = None) -> FastAPI:
    student_source = student_path.resolve()
    teacher_source = teacher_path.resolve() if teacher_path else None
    student_data = load_assignment(student_source)
    assert_template(student_data, "exam-zh-practice", student_source)
    teacher_data = None
    if teacher_source:
        teacher_data = load_assignment(teacher_source)
        assert_template(teacher_data, "exam-zh-practice", teacher_source)

    app = _base_app("Assignment Review")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(TEMPLATE_DIR / "assignment_review.html", media_type="text/html")

    @app.get("/api/state")
    def state() -> dict[str, Any]:
        return {
            "mode": "assignment",
            "student_path": str(student_source),
            "teacher_path": str(teacher_source) if teacher_source else "",
            "student_reviewed_path": str(reviewed_path(student_source)),
            "teacher_reviewed_path": str(reviewed_path(teacher_source)) if teacher_source else "",
            "student": clone_data(student_data),
            "teacher": clone_data(teacher_data) if teacher_data else None,
            "student_sections": summarize_sections(student_data),
            "teacher_sections": summarize_sections(teacher_data) if teacher_data else [],
        }

    @app.post("/api/save")
    def save(payload: dict[str, Any]) -> dict[str, Any]:
        saved = []
        overwrite = bool(payload.get("overwrite"))
        if isinstance(payload.get("student"), dict):
            target = student_source if overwrite else reviewed_path(student_source)
            dump_assignment(target, payload["student"])
            saved.append({"role": "student", "path": str(target), "display_path": public_path(target)})
        if teacher_source and isinstance(payload.get("teacher"), dict):
            target = teacher_source if overwrite else reviewed_path(teacher_source)
            dump_assignment(target, payload["teacher"])
            saved.append({"role": "teacher", "path": str(target), "display_path": public_path(target)})
        return {"status": "saved", "files": saved}

    @app.post("/api/validate")
    def validate(payload: dict[str, Any]) -> dict[str, Any]:
        results = {}
        if isinstance(payload.get("student"), dict):
            results["student"] = validate_data(payload["student"], base_dir=student_source.parent)
        if teacher_source and isinstance(payload.get("teacher"), dict):
            results["teacher"] = validate_data(payload["teacher"], base_dir=teacher_source.parent)
        return {"status": "validated", "results": results}

    @app.post("/api/render")
    def render(payload: dict[str, Any]) -> dict[str, Any]:
        results = {}
        if isinstance(payload.get("student"), dict):
            results["student"] = render_data(
                payload["student"],
                source_path=student_source,
                out_path=preview_tex_path(student_source, "student"),
            )
        if teacher_source and isinstance(payload.get("teacher"), dict):
            results["teacher"] = render_data(
                payload["teacher"],
                source_path=teacher_source,
                out_path=preview_tex_path(teacher_source, "teacher"),
            )
        return {"status": "rendered", "results": results}

    @app.post("/api/compile")
    def compile_current(payload: dict[str, Any]) -> dict[str, Any]:
        tex_path = Path(_required_text(payload, "tex_path")).resolve()
        return compile_tex(tex_path)

    @app.post("/api/agent-request")
    def agent_request(payload: dict[str, Any]) -> dict[str, Any]:
        source_paths = {"student": str(student_source)}
        if teacher_source:
            source_paths["teacher"] = str(teacher_source)
        path = write_agent_request(
            mode="assignment",
            artifact_dir=student_source.parent,
            source_paths=source_paths,
            selection=payload.get("selection") if isinstance(payload.get("selection"), dict) else {},
            instruction=_required_text(payload, "instruction"),
        )
        return {"status": "saved", "path": str(path), "display_path": public_path(path)}

    return app


def run_explanation_server(yaml_path: Path, host: str, port: int) -> None:
    uvicorn.run(create_explanation_app(yaml_path), host=host, port=port, log_level="info")


def run_assignment_server(student_path: Path, teacher_path: Path | None, host: str, port: int) -> None:
    uvicorn.run(create_assignment_app(student_path, teacher_path), host=host, port=port, log_level="info")


def _base_app(title: str) -> FastAPI:
    app = FastAPI(title=title, version="0.1.0")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/healthz")
    def healthz() -> dict[str, bool]:
        return {"ok": True}

    return app


def _required_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{key} must be an object")
    return value


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{key} is required")
    return value.strip()
