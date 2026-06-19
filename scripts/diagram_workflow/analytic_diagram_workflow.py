#!/usr/bin/env python3
"""Build analytic coordinate/function diagram specs with WolframClient.

This module is the non-GeometricScene route for DiagramJobRequest v2. Python
owns orchestration and renderer-spec output; WolframClient is used only for
symbolic/numeric math such as function sampling and intersections.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "geometry_diagram_workflow" / "core"))

from diagram_contracts import (  # noqa: E402
    DiagramEngine,
    DiagramJobRequest,
    DiagramJobResult,
    DiagramKind,
    GeometryRenderSpec,
)
from runtime import redact_secrets, resolve_wolfram_kernel  # noqa: E402

try:
    from wolframclient.evaluation import WolframLanguageSession
    from wolframclient.language import wlexpr
except ImportError as exc:  # pragma: no cover - depends on local env
    WolframLanguageSession = None  # type: ignore[assignment]
    wlexpr = None  # type: ignore[assignment]
    WOLFRAM_IMPORT_ERROR = exc
else:
    WOLFRAM_IMPORT_ERROR = None


SAFE_WL_PATTERN = re.compile(r"^[0-9A-Za-z_+\-*/^().,\s\[\]]+$")
FORBIDDEN_WL_TOKENS = (
    "Run",
    "RunProcess",
    "StartProcess",
    "CreateFile",
    "DeleteFile",
    "DeleteDirectory",
    "RenameFile",
    "CopyFile",
    "Import",
    "Export",
    "URL",
    "Get",
    "Put",
    "<<",
    ";",
)
ALLOWED_FUNCTIONS = {
    "Abs",
    "ArcCos",
    "ArcSin",
    "ArcTan",
    "Cos",
    "Exp",
    "Log",
    "Max",
    "Min",
    "Pi",
    "Sin",
    "Sqrt",
    "Tan",
    "x",
    "y",
}


def read_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        data = data.model_dump(mode="json", by_alias=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit_event(out_dir: Path, event: str, **fields: object) -> None:
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **fields,
    }
    with (out_dir / "workflow_events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def compact_float(value: object) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"non-finite numeric value: {value}")
    return 0.0 if abs(number) < 1e-12 else number


def wl_expr_from_latex(text: str) -> str:
    expr = str(text).strip()
    expr = re.sub(r"^\s*y\s*=", "", expr)
    replacements = {
        r"\sin": "Sin",
        r"\cos": "Cos",
        r"\tan": "Tan",
        r"\sqrt": "Sqrt",
        r"\ln": "Log",
        r"\pi": "Pi",
    }
    for src, dst in replacements.items():
        expr = expr.replace(src, dst)
    expr = expr.replace("{", "(").replace("}", ")")
    expr = expr.replace("^", "^")
    expr = re.sub(r"(\d)\s*x", r"\1*x", expr)
    expr = re.sub(r"x\s*(\d)", r"x*\1", expr)
    return expr


def sanitize_wl_expression(raw: str, variable: str = "x") -> str:
    expr = str(raw).strip()
    if not expr:
        raise ValueError("empty Wolfram expression")
    if not SAFE_WL_PATTERN.match(expr):
        raise ValueError(f"expression contains unsupported characters: {raw}")
    for token in FORBIDDEN_WL_TOKENS:
        if token in expr:
            raise ValueError(f"expression contains forbidden token: {token}")
    symbols = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
    allowed = set(ALLOWED_FUNCTIONS)
    allowed.add(variable)
    unknown = sorted(symbols - allowed)
    if unknown:
        raise ValueError(f"expression contains unsupported symbol(s): {unknown}")
    return expr


def function_expression(function_spec: dict[str, object]) -> tuple[str, str]:
    variable = str(function_spec.get("variable") or "x")
    expr = function_spec.get("expression_wl") or wl_expr_from_latex(function_spec.get("expression_latex", ""))
    return sanitize_wl_expression(str(expr), variable), variable


class WolframAnalyticKernel:
    def __init__(self, kernel_path: str | None = None):
        if WOLFRAM_IMPORT_ERROR is not None:
            raise RuntimeError(f"Missing wolframclient: {WOLFRAM_IMPORT_ERROR}")
        self.kernel_path = resolve_wolfram_kernel(kernel_path)
        self.session = None

    def __enter__(self) -> WolframAnalyticKernel:
        self.session = WolframLanguageSession(self.kernel_path)  # type: ignore[misc]
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.session is not None:
            self.session.terminate()
        self.session = None

    def evaluate(self, expression: str) -> object:
        if self.session is None:
            raise RuntimeError("Wolfram session is not open")
        return self.session.evaluate(wlexpr(expression))  # type: ignore[misc]

    def sample_function(
        self,
        expression: str,
        variable: str,
        x_min: float,
        x_max: float,
        sample_count: int,
    ) -> list[tuple[float, float]]:
        expr = sanitize_wl_expression(expression, variable)
        count = max(2, int(sample_count))
        wl_code = (
            "N[Table[{xx, Quiet[Check["
            f"({expr}) /. {variable} -> xx"
            ", Indeterminate]]}, "
            f"{{xx, {x_min:.12g}, {x_max:.12g}, ({x_max:.12g} - {x_min:.12g})/{count - 1}}}]]"
        )
        raw = self.evaluate(wl_code)
        samples: list[tuple[float, float]] = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            try:
                x_val = compact_float(item[0])
                y_val = compact_float(item[1])
            except (TypeError, ValueError):
                continue
            samples.append((x_val, y_val))
        if not samples:
            raise ValueError(f"Wolfram produced no finite samples for {expression}")
        return samples

    def solve_points(self, equations: list[str], variables: tuple[str, str] = ("x", "y")) -> list[tuple[float, float]]:
        safe_equations = [sanitize_equation(eq) for eq in equations]
        x_var, y_var = variables
        equation_text = ", ".join(safe_equations)
        wl_code = (
            f"N[{{{x_var}, {y_var}}} /. "
            f"Solve[{{{equation_text}}}, {{{x_var}, {y_var}}}, Reals]]"
        )
        raw = self.evaluate(wl_code)
        points: list[tuple[float, float]] = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                points.append((compact_float(item[0]), compact_float(item[1])))
        return points


def sanitize_equation(raw: str) -> str:
    equation = str(raw).strip()
    if "=" in equation and "==" not in equation:
        equation = equation.replace("=", "==", 1)
    if "==" not in equation:
        raise ValueError(f"equation must contain '=' or '==': {raw}")
    left, right = equation.split("==", 1)
    return f"{sanitize_wl_expression(left.strip(), 'x')} == {sanitize_wl_expression(right.strip(), 'x')}"


def viewport_bounds(analytic: dict[str, object], functions: list[dict[str, object]], objects: list[dict[str, object]]) -> dict[str, object]:
    viewport = dict(analytic.get("viewport") or {})
    x_values: list[float] = []
    y_values: list[float] = []
    for obj in objects:
        if obj.get("type") == "point":
            if "x" in obj and "y" in obj:
                x_values.append(compact_float(obj["x"]))
                y_values.append(compact_float(obj["y"]))
        if obj.get("type") == "circle":
            radius = compact_float(obj.get("radius", 1))
            cx, cy = object_center(obj)
            x_values.extend([cx - radius, cx + radius])
            y_values.extend([cy - radius, cy + radius])
    for func in functions:
        domain = func.get("domain")
        if isinstance(domain, dict):
            x_values.extend([compact_float(domain["min"]), compact_float(domain["max"])])
    x_min = viewport.get("x_min")
    x_max = viewport.get("x_max")
    y_min = viewport.get("y_min")
    y_max = viewport.get("y_max")
    if x_min is None or x_max is None:
        x_min = min(x_values) if x_values else -5
        x_max = max(x_values) if x_values else 5
    if y_min is None or y_max is None:
        y_min = min(y_values) if y_values else -5
        y_max = max(y_values) if y_values else 5
    if float(x_min) >= float(x_max):
        raise ValueError("viewport x_min must be < x_max")
    if float(y_min) >= float(y_max):
        raise ValueError("viewport y_min must be < y_max")
    viewport.update(
        {
            "x_min": compact_float(x_min),
            "x_max": compact_float(x_max),
            "y_min": compact_float(y_min),
            "y_max": compact_float(y_max),
            "preserve_aspect": bool(viewport.get("preserve_aspect", True)),
        }
    )
    return viewport


def object_center(obj: dict[str, object]) -> tuple[float, float]:
    center = obj.get("center")
    if isinstance(center, (list, tuple)) and len(center) == 2:
        return compact_float(center[0]), compact_float(center[1])
    if isinstance(center, dict):
        return compact_float(center.get("x", 0)), compact_float(center.get("y", 0))
    return compact_float(obj.get("cx", obj.get("x", 0))), compact_float(obj.get("cy", obj.get("y", 0)))


def line_equation(obj: dict[str, object]) -> str:
    equation = obj.get("equation")
    if isinstance(equation, str) and equation.strip():
        return sanitize_equation(equation)
    if {"slope", "intercept"} <= set(obj):
        m = compact_float(obj["slope"])
        b = compact_float(obj["intercept"])
        return f"y == ({m:.12g})*x + ({b:.12g})"
    raise ValueError(f"line object requires equation or slope/intercept: {obj.get('id', '')}")


def circle_equation(obj: dict[str, object]) -> str:
    cx, cy = object_center(obj)
    radius = compact_float(obj.get("radius"))
    if radius <= 0:
        raise ValueError("circle radius must be positive")
    return f"(x - ({cx:.12g}))^2 + (y - ({cy:.12g}))^2 == ({radius:.12g})^2"


def function_equation(function_spec: dict[str, object]) -> str:
    expr, variable = function_expression(function_spec)
    if variable != "x":
        raise ValueError("coordinate renderer currently supports function variable 'x'")
    return f"y == ({expr})"


def compute_intersections(
    kernel: WolframAnalyticKernel,
    functions: list[dict[str, object]],
    objects: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_id = {str(obj.get("id")): obj for obj in objects if obj.get("id")}
    by_id.update(
        {
            str(func.get("id")): {**func, "type": "function"}
            for func in functions
            if func.get("id")
        }
    )
    computed: list[dict[str, object]] = []
    for obj in objects:
        kind = obj.get("type")
        if kind not in {"intersection", "zero", "root", "x_intercept"}:
            continue

        if kind == "intersection":
            refs = [str(item) for item in obj.get("of", [])]
            if len(refs) != 2 or refs[0] not in by_id or refs[1] not in by_id:
                raise ValueError(f"intersection object requires two known refs: {refs}")
            equations = [equation_for_object(by_id[refs[0]]), equation_for_object(by_id[refs[1]])]
            prefix = str(obj.get("id") or "I")
        else:
            ref_value = obj.get("of") or obj.get("function") or obj.get("function_id")
            if isinstance(ref_value, list):
                ref_value = ref_value[0] if ref_value else ""
            ref = str(ref_value)
            if ref not in by_id:
                raise ValueError(f"{kind} object requires a known function ref: {ref}")
            refs = [ref, "x_axis"]
            equations = [equation_for_object(by_id[ref]), "y == 0"]
            prefix = str(obj.get("id") or "Z")

        points = kernel.solve_points(equations)
        for index, (x_val, y_val) in enumerate(points, start=1):
            computed.append(
                {
                    "type": "point",
                    "id": prefix if len(points) == 1 else f"{prefix}{index}",
                    "x": x_val,
                    "y": y_val,
                    "label": obj.get("label") or (prefix if len(points) == 1 else f"{prefix}_{index}"),
                    "computed": True,
                    "from": refs,
                }
            )
    return computed


COMPUTED_OBJECT_TYPES = {"intersection", "zero", "root", "x_intercept"}


def needs_wolfram(functions: list[dict[str, object]], objects: list[dict[str, object]]) -> bool:
    """Return true when the analytic route must compute data, not just pass it through."""
    if functions:
        return True
    return any(obj.get("type") in COMPUTED_OBJECT_TYPES for obj in objects)


def equation_for_object(obj: dict[str, object]) -> str:
    kind = obj.get("type")
    if kind == "function":
        return function_equation(obj)
    if kind == "line":
        return line_equation(obj)
    if kind == "circle":
        return circle_equation(obj)
    raise ValueError(f"intersection supports function/line/circle objects, not {kind}")


def build_spec(request: DiagramJobRequest, out_dir: Path) -> GeometryRenderSpec:
    analytic = request.analytic_requirements.model_dump(mode="json")
    functions = list(analytic.get("functions") or [])
    objects = [dict(obj) for obj in analytic.get("objects") or []]
    viewport = viewport_bounds(analytic, functions, objects)
    axes = analytic.get("axes") or {}
    samples: dict[str, list[tuple[float, float]]] = {}
    kernel_path = None
    if request.engine_options.engine_model_config:
        kernel_path = request.engine_options.engine_model_config.get("wl_kernel")

    emit_event(out_dir, "analytic_start", job_id=request.job_id, engine=request.engine.value, kind=request.diagram_kind.value)
    used_wolfram = needs_wolfram(functions, objects)
    if used_wolfram:
        with WolframAnalyticKernel(kernel_path) as kernel:
            emit_event(out_dir, "wolfram_kernel_ready", kernel=kernel.kernel_path)
            for func in functions:
                expr, variable = function_expression(func)
                domain = func.get("domain") or {}
                x_min = compact_float(domain.get("min", viewport["x_min"]))
                x_max = compact_float(domain.get("max", viewport["x_max"]))
                count = int(func.get("sample_count", 160))
                samples[str(func["id"])] = kernel.sample_function(expr, variable, x_min, x_max, count)
                func["expression_wl"] = expr
                emit_event(out_dir, "function_sampled", function_id=func["id"], sample_count=len(samples[str(func["id"])]))
            computed = compute_intersections(kernel, functions, objects)
            objects.extend(computed)
            if computed:
                emit_event(out_dir, "intersections_computed", count=len(computed))
    else:
        emit_event(out_dir, "wolfram_skipped", reason="explicit coordinate objects require no analytic computation")

    spec_type = request.diagram_kind.value
    if spec_type not in {DiagramKind.COORDINATE_GEOMETRY.value, DiagramKind.FUNCTION_GRAPH.value}:
        spec_type = DiagramKind.FUNCTION_GRAPH.value if functions else DiagramKind.COORDINATE_GEOMETRY.value
    spec = {
        "schema_version": "geometry-render-spec/v1",
        "job_id": request.job_id,
        "variant": request.variant.value,
        "disclosure_policy": request.disclosure_policy.value,
        "type": spec_type,
        "render_profile": request.render_profile.model_dump(mode="json"),
        "viewport": viewport,
        "axes": axes,
        "functions": functions,
        "samples": {key: [[x, y] for x, y in value] for key, value in samples.items()},
        "objects": objects,
        "teaching_focus": request.semantic_constraints.given_objects
        or request.semantic_constraints.given_constraints,
        "diagnostics": {"wolfram_used": used_wolfram},
    }
    return GeometryRenderSpec.model_validate(spec)


def run_analytic_workflow(request_path: Path, out_dir: Path) -> dict[str, object]:
    raw = read_json(request_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    request: DiagramJobRequest | None = None
    try:
        request = DiagramJobRequest(**raw)
        write_json(out_dir / "request.json", request.model_dump(mode="json"))
        if request.engine not in {
            DiagramEngine.WOLFRAM_CLIENT,
            DiagramEngine.WOLFRAM_PLOT,
            DiagramEngine.COORDINATE_RENDERER,
        }:
            raise ValueError(f"unsupported analytic engine: {request.engine.value}")
        if request.diagram_kind not in {
            DiagramKind.COORDINATE_GEOMETRY,
            DiagramKind.FUNCTION_GRAPH,
        }:
            raise ValueError(f"unsupported analytic diagram_kind: {request.diagram_kind.value}")
        spec = build_spec(request, out_dir)
        write_json(out_dir / "final_renderer_spec.json", spec)
        wolfram_used = bool(spec.diagnostics.get("wolfram_used"))
        result = DiagramJobResult.model_validate({
            "schema_version": "diagram-job-result/v2",
            "job_id": request.job_id,
            "status": "ok",
            "fail_type": "",
            "message": "",
            "request": "request.json",
            "workflow_events": "workflow_events.jsonl",
            "scene_payload": "",
            "final_renderer_spec": "final_renderer_spec.json",
            "wolfram": {"success": wolfram_used},
            "model": {"text_model_used": "", "attempts": []},
            "policy_warnings": [],
        }).model_dump(mode="json", by_alias=True)
    except Exception as exc:
        if not (out_dir / "request.json").exists():
            write_json(out_dir / "request.json", raw)
        emit_event(out_dir, "analytic_failed", error=redact_secrets(exc))
        result = DiagramJobResult.model_validate({
            "schema_version": "diagram-job-result/v2",
            "job_id": (request.job_id if request else raw.get("job_id") or raw.get("diagram_job_id", "")),
            "status": "failed",
            "fail_type": "analytic_workflow_failed",
            "message": redact_secrets(exc),
            "request": "request.json",
            "workflow_events": "workflow_events.jsonl",
            "scene_payload": "",
            "final_renderer_spec": "final_renderer_spec.json",
            "wolfram": {"success": False},
            "model": {"text_model_used": "", "attempts": []},
            "policy_warnings": [],
        }).model_dump(mode="json", by_alias=True)
    write_json(out_dir / "workflow_result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build analytic diagram renderer spec")
    parser.add_argument("request", type=Path, help="Path to DiagramJobRequest v2 JSON")
    parser.add_argument("--out", type=Path, required=True, help="Output job directory")
    args = parser.parse_args()
    result = run_analytic_workflow(args.request.resolve(), args.out.resolve())
    print(json.dumps(result, ensure_ascii=False))
    if result.get("status") != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
