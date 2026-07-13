#!/usr/bin/env python3
"""Thin wrapper around the local agentic GeometricScene workflow.

This keeps the teaching pipeline on a local JSON + subprocess boundary.  The
wrapper normalizes the teaching-side request to the workflow CLI contract
without introducing an MCP server or any long-lived service.  The default
workflow lives inside this repository.  A custom workflow root can be supplied
only for local experiments, not as the production path.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from diagram_contracts import DiagramJobRequest, DiagramJobResult, GeometryRenderSpec
from progress_subprocess import run_subprocess_streaming


SUPPORTED_GSB_TYPES = {"synthetic_geometry"}
SUPPORTED_ANALYTIC_TYPES = {"coordinate_geometry", "function_graph"}
SUPPORTED_ANALYTIC_ENGINES = {"wolfram_client", "wolfram_plot", "coordinate_renderer"}
SUPPORTED_SPATIAL_TYPES = {"spatial_geometry"}
SUPPORTED_SPATIAL_ENGINES = {"spatial_renderer"}


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("diagram request must be a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_gsb_root() -> Path:
    return Path(__file__).resolve().parent / "geometry_diagram_workflow"


def skipped_result(out_dir: Path, request: dict[str, Any], reason: str) -> dict[str, Any]:
    result = {
        "status": "skipped",
        "reason": reason,
        "out_dir": str(out_dir),
        "fallback": request.get("fallback", "textual_diagram_description"),
    }
    write_json(out_dir / "workflow_result.json", result)
    return result


def request_diagram_type(request: dict[str, Any]) -> str:
    return str(
        request.get("diagram_kind")
        or request.get("diagram_type")
        or "synthetic_geometry"
    )


def request_engine(request: dict[str, Any]) -> str:
    return str(request.get("engine") or "geometric_scene")


def run_analytic_workflow(
    request_path: Path,
    out_dir: Path,
    python_executable: str,
) -> dict[str, Any]:
    script = Path(__file__).resolve().parent / "analytic_diagram_workflow.py"
    cmd = [
        python_executable,
        str(script),
        str(request_path),
        "--out",
        str(out_dir),
    ]
    completed = run_subprocess_streaming(cmd)
    (out_dir / "wrapper_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (out_dir / "wrapper_stderr.txt").write_text(completed.stderr, encoding="utf-8")
    result_path = out_dir / "workflow_result.json"
    if result_path.exists():
        result = read_json(result_path)
        result["teaching_request"] = "teaching_request.json"
        write_json(result_path, result)
    else:
        result = {
            "status": "failed",
            "error": "analytic workflow did not produce workflow_result.json",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "out_dir": str(out_dir),
        }
        write_json(result_path, result)
    print(json.dumps(result, ensure_ascii=False))
    if completed.returncode != 0:
        sys.exit(completed.returncode)
    return result


def run_spatial_workflow(
    request_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    from spatial_diagram_workflow import run_spatial_workflow as _run_spatial_workflow

    result = _run_spatial_workflow(request_path, out_dir)
    print(json.dumps(result, ensure_ascii=False))
    return result


def _safe_renderer_spec_payload(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        raise ValueError("engine_options.renderer_spec must be a non-empty object")
    forbidden = {"tikz", "tikz_code", "tikz_fragment", "tex", "tex_source"}
    present = sorted(forbidden & set(value))
    if present:
        raise ValueError(f"renderer_spec engine accepts GeometryRenderSpec only; forbidden key(s): {present}")
    return dict(value)


def run_renderer_spec_workflow(
    request: dict[str, Any],
    out_dir: Path,
    *,
    emit_result: bool = True,
) -> dict[str, Any]:
    """Deterministic workflow route for tests and precomputed renderer specs.

    ``emit_result`` controls whether the result JSON is echoed to stdout. The
    CLI path keeps it on; the in-process batch runner passes ``emit_result=False``
    so the per-job print does not interleave with the batch report on stdout.
    """
    try:
        request_model = DiagramJobRequest(**request)
        write_json(out_dir / "request.json", request_model.model_dump(mode="json", by_alias=True))
        spec_payload = _safe_renderer_spec_payload(request_model.engine_options.renderer_spec)
        spec_payload.update(
            {
                "schema_version": "geometry-render-spec/v1",
                "job_id": request_model.job_id,
                "variant": request_model.variant.value,
                "disclosure_policy": request_model.disclosure_policy.value,
                "type": request_model.diagram_kind.value,
                "render_profile": request_model.render_profile.model_dump(mode="json"),
            }
        )
        spec = GeometryRenderSpec.model_validate(spec_payload)
        write_json(out_dir / "final_renderer_spec.json", spec.model_dump(mode="json", by_alias=True))
        result = DiagramJobResult.model_validate(
            {
                "schema_version": "diagram-job-result/v2",
                "job_id": request_model.job_id,
                "status": "ok",
                "fail_type": "",
                "message": "",
                "request": "request.json",
                "workflow_events": "",
                "scene_payload": "",
                "final_renderer_spec": "final_renderer_spec.json",
                "final_tikz_fragment_path": "",
                "wolfram": {"success": False},
                "model": {"text_model_used": "", "attempts": []},
                "policy_warnings": [],
            }
        ).model_dump(mode="json", by_alias=True)
    except Exception as exc:
        result = DiagramJobResult.model_validate(
            {
                "schema_version": "diagram-job-result/v2",
                "job_id": request.get("job_id") or request.get("diagram_job_id", ""),
                "status": "failed",
                "fail_type": "renderer_spec_workflow_failed",
                "message": str(exc),
                "request": "request.json",
                "workflow_events": "",
                "scene_payload": "",
                "final_renderer_spec": "final_renderer_spec.json",
                "wolfram": {"success": False},
                "model": {"text_model_used": "", "attempts": []},
                "policy_warnings": [],
            }
        ).model_dump(mode="json", by_alias=True)
        if not (out_dir / "request.json").exists():
            write_json(out_dir / "request.json", request)
    write_json(out_dir / "workflow_result.json", result)
    if emit_result:
        print(json.dumps(result, ensure_ascii=False))
    return result


def normalize_for_gsb(request: dict[str, Any]) -> dict[str, Any]:
    if request.get("schema_version") == "diagram-job-request/v2":
        normalized = dict(request)
        normalized.setdefault("engine_options", {})
        return normalized

    diagram_type = request.get("diagram_type") or "synthetic_geometry"
    normalized = dict(request)
    normalized["teaching_diagram_intent"] = request.get("diagram_intent", "student_explanation")
    # Current GSB workflow.py reads `diagram_intent` as the GeometricScene type.
    normalized["diagram_intent"] = diagram_type
    # Teaching-side rendering consumes the solved renderer spec, so this adapter
    # does not require Wolfram's frontend-backed Graphics -> PNG export path.
    normalized.setdefault("wolfram_render_image", False)
    return normalized


def _segment_key(segment: Any) -> tuple[str, str] | None:
    if not isinstance(segment, (list, tuple)) or len(segment) != 2:
        return None
    a, b = str(segment[0]), str(segment[1])
    return tuple(sorted((a, b)))


def sanitize_clean_prompt_spec(out_dir: Path, request: dict[str, Any], result: dict[str, Any]) -> list[str]:
    """Enforce source-side diagram policy after GSB generation.

    GSB is allowed to reason with derived facts, but student prompt diagrams
    must not display solution-only hints such as BH=HD ticks, midpoint labels,
    or teaching_focus text that states the answer.
    """
    if request.get("disclosure_policy") != "clean":
        return []
    renderer_spec_rel = result.get("final_renderer_spec") or "final_renderer_spec.json"
    spec_path = out_dir / renderer_spec_rel
    if not spec_path.exists():
        return []
    spec = read_json(spec_path)
    problem_text = str(request.get("problem_text", ""))
    allowed_equal_ticks: set[tuple[str, str]] = set()
    if "AD=AB" in problem_text or "AB=AD" in problem_text:
        allowed_equal_ticks.update({("A", "B"), ("A", "D")})

    changes: list[str] = []
    clean_markers = []
    for marker in spec.get("markers") or []:
        if not isinstance(marker, dict):
            continue
        if marker.get("type") == "right_angle":
            clean_markers.append(marker)
            continue
        if marker.get("type") == "equal_ticks":
            segments = marker.get("segments") or []
            keys = {_segment_key(seg) for seg in segments}
            keys.discard(None)
            if keys and keys <= allowed_equal_ticks:
                clean_markers.append(marker)
            else:
                changes.append(f"removed equal_ticks {segments}")
            continue
        changes.append(f"removed marker {marker.get('type', 'unknown')}")
    if clean_markers != spec.get("markers"):
        spec["markers"] = clean_markers

    if spec.get("teaching_focus"):
        spec["teaching_focus"] = ["读清题干给定对象"]
        changes.append("reset teaching_focus")

    # Avoid shaded/focused solution triangles in source-side figures.
    if spec.get("polygons"):
        spec["polygons"] = []
        changes.append("removed polygons")

    if changes:
        write_json(spec_path, spec)
    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local agentic GeometricScene workflow")
    parser.add_argument("request", type=Path, help="Path to DiagramJobRequest v2 JSON")
    parser.add_argument("--out", type=Path, help="Output directory; defaults to <request-dir>/diagram")
    parser.add_argument("--job-id", help="Diagram job id; defaults to request.job_id when present")
    parser.add_argument(
        "--gsb-root",
        type=Path,
        default=default_gsb_root(),
        help="Path to local geometry workflow root for local experiments",
    )
    parser.add_argument("--python", default=sys.executable, help="Python executable for GSB workflow")
    parser.add_argument(
        "--allow-unsupported",
        action="store_true",
        help="Pass non-synthetic diagram types to GSB anyway",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when GSB completes but no usable diagram is produced",
    )
    args = parser.parse_args()

    request_path = args.request.resolve()
    request = read_json(request_path)
    job_id = args.job_id or request.get("job_id") or request.get("diagram_job_id")
    out_dir = (args.out or (request_path.parent / "diagram")).resolve()
    if job_id and out_dir.name != job_id:
        out_dir = out_dir / "jobs" / str(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    if job_id:
        request["job_id"] = str(job_id)
    write_json(out_dir / "teaching_request.json", request)

    if not request.get("needs_diagram", True):
        result = skipped_result(out_dir, request, "needs_diagram is false")
        print(json.dumps(result, ensure_ascii=False))
        return

    diagram_type = request_diagram_type(request)
    engine = request_engine(request)
    if engine == "renderer_spec":
        result = run_renderer_spec_workflow(request, out_dir)
        if args.strict and result.get("status") != "ok":
            sys.exit(1)
        return
    if diagram_type in SUPPORTED_ANALYTIC_TYPES or engine in SUPPORTED_ANALYTIC_ENGINES:
        result = run_analytic_workflow(request_path, out_dir, args.python)
        if args.strict and result.get("status") != "ok":
            sys.exit(1)
        return
    if diagram_type in SUPPORTED_SPATIAL_TYPES or engine in SUPPORTED_SPATIAL_ENGINES:
        result = run_spatial_workflow(request_path, out_dir)
        if args.strict and result.get("status") != "ok":
            sys.exit(1)
        return

    if diagram_type not in SUPPORTED_GSB_TYPES and not args.allow_unsupported:
        result = skipped_result(
            out_dir,
            request,
            f"diagram_type '{diagram_type}' is not routed to the local GeometricScene workflow yet",
        )
        print(json.dumps(result, ensure_ascii=False))
        return

    workflow_path = args.gsb_root.resolve() / "core" / "workflow.py"
    if not workflow_path.exists():
        result = {
            "status": "failed",
            "error": f"GSB workflow not found: {workflow_path}",
            "out_dir": str(out_dir),
        }
        write_json(out_dir / "workflow_result.json", result)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    gsb_request_path = out_dir / "request.gsb.json"
    write_json(gsb_request_path, normalize_for_gsb(request))

    cmd = [
        args.python,
        str(workflow_path),
        "--action",
        "run",
        "--request",
        str(gsb_request_path),
        "--out",
        str(out_dir),
    ]
    completed = run_subprocess_streaming(
        cmd,
        event_context={"job_id": str(job_id or request.get("job_id") or "")},
    )
    (out_dir / "wrapper_stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (out_dir / "wrapper_stderr.txt").write_text(completed.stderr, encoding="utf-8")

    result_path = out_dir / "workflow_result.json"
    if result_path.exists():
        result = read_json(result_path)
        result["teaching_request"] = "teaching_request.json"
        result["gsb_request"] = "request.gsb.json"
        changes = sanitize_clean_prompt_spec(out_dir, request, result)
        if changes:
            result["clean_prompt_sanitization"] = changes
        write_json(result_path, result)
    else:
        result = {
            "status": "failed",
            "error": "GSB did not produce workflow_result.json",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "out_dir": str(out_dir),
        }
        write_json(result_path, result)

    print(json.dumps(result, ensure_ascii=False))
    if completed.returncode != 0:
        sys.exit(completed.returncode)
    if args.strict and result.get("status") not in {"ok", "skipped"}:
        sys.exit(1)


if __name__ == "__main__":
    main()
