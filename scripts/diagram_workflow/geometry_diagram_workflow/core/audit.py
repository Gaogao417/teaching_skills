from __future__ import annotations

import re
import math
from pathlib import Path
from typing import Dict, List

from diagram_contracts import GeometryRendererResult, GeometryRenderSpec
from runtime import redact_secrets
from tools import _read_json, _relative_path, _validate_scene_code, _write_json


def _bad_label_text(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("text", "")
    text = str(value)
    forbidden = ["ref", "GeometricPoint", "[[", "]]", "C[\"", "Centroid"]
    if any(item in text for item in forbidden):
        return f"bad serialized label text: {text[:80]}"
    if len(text) > 24:
        return f"label text too long: {text[:80]}"
    return ""


def _normalized_segment(value: object) -> tuple[str, str]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return ("", "")
    return tuple(sorted((str(value[0]), str(value[1]))))


def _marker_signature(value: object) -> tuple[object, ...]:
    if not isinstance(value, dict):
        return ("invalid",)
    marker_type = str(value.get("type") or "")
    aliases = {
        "equal_tick": "equal_ticks",
        "equal_segment": "equal_ticks",
        "equal_segments": "equal_ticks",
        "parallel_mark": "parallel",
        "parallel_marks": "parallel",
    }
    marker_type = aliases.get(marker_type, marker_type)
    if marker_type in {"equal_ticks", "parallel"}:
        segments = value.get("segments") if isinstance(value.get("segments"), list) else []
        return (marker_type, tuple(sorted(_normalized_segment(item) for item in segments)))
    arms = value.get("arms") if isinstance(value.get("arms"), list) else []
    return (marker_type, str(value.get("vertex") or ""), tuple(sorted(str(item) for item in arms)))


def _text_signature(value: object) -> tuple[object, ...]:
    if not isinstance(value, dict):
        return ("invalid",)
    target = value.get("target") if isinstance(value.get("target"), list) else []
    return (str(value.get("text") or ""), tuple(str(item) for item in target))


def _visible_requirements(request: Dict[str, object]) -> tuple[list[object], list[object]]:
    visual = request.get("visual_requirements")
    if not isinstance(visual, dict):
        return [], []
    required = visual.get("required_visible_annotations")
    if not isinstance(required, dict):
        return [], []
    markers = required.get("markers") if isinstance(required.get("markers"), list) else []
    texts = required.get("texts") if isinstance(required.get("texts"), list) else []
    return markers, texts


def _audit_degenerate_geometry(
    renderer_spec: Dict[str, object],
    issues: List[str],
    warnings: List[str],
) -> None:
    raw_points = renderer_spec.get("points")
    if not isinstance(raw_points, dict) or len(raw_points) < 2:
        return
    points: dict[str, tuple[float, float]] = {}
    for name, value in raw_points.items():
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            points[str(name)] = (float(value[0]), float(value[1]))
    if len(points) < 2:
        return
    xs = [point[0] for point in points.values()]
    ys = [point[1] for point in points.values()]
    diagonal = max(math.hypot(max(xs) - min(xs), max(ys) - min(ys)), 1e-9)
    names = list(points)
    for index, first_name in enumerate(names):
        for second_name in names[index + 1 :]:
            distance = math.dist(points[first_name], points[second_name])
            if distance <= 1e-8:
                issues.append(f"degenerate_coincident_points:{first_name}:{second_name}")
            elif distance / diagonal < 0.012:
                warnings.append(f"near_coincident_points:{first_name}:{second_name}")
    polygons = renderer_spec.get("polygons")
    if not isinstance(polygons, list):
        return
    bbox_area = max((max(xs) - min(xs)) * (max(ys) - min(ys)), 1e-9)
    for index, polygon in enumerate(polygons):
        if not isinstance(polygon, dict) or not isinstance(polygon.get("points"), list):
            continue
        vertices = [points[name] for name in polygon["points"] if name in points]
        if len(vertices) < 3:
            continue
        area2 = abs(
            sum(
                vertices[item][0] * vertices[(item + 1) % len(vertices)][1]
                - vertices[(item + 1) % len(vertices)][0] * vertices[item][1]
                for item in range(len(vertices))
            )
        )
        if area2 / 2 / bbox_area < 0.003:
            issues.append(f"degenerate_polygon:{index}")


def audit_diagram_action(
    request: Dict[str, object],
    scene_payload_path: Path,
    render_result_path: Path,
    renderer_spec_path: Path,
    renderer_result_path: Path,
    out_dir: Path,
    round_index: int,
) -> Dict[str, object]:
    issues: List[str] = []
    warnings: List[str] = []
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    scene_payload = _read_json(scene_payload_path)
    render_result = _read_json(render_result_path)
    renderer_spec = _read_json(renderer_spec_path)
    renderer_result = _read_json(renderer_result_path)

    try:
        _validate_scene_code(
            str(scene_payload.get("scene_code", "")),
            allow_fixed_metrics=bool(
                request.get("reuse_geometry_from")
                or request.get("reuse_from")
                or request.get("base_diagram_job_id")
            ),
        )
    except Exception as exc:
        issues.append(f"invalid_scene_code: {redact_secrets(exc)}")

    if not render_result.get("success"):
        issues.append(
            f"wolfram_failed: {render_result.get('fail_type', 'unknown')} "
            f"{render_result.get('message', '')}"
        )

    try:
        GeometryRenderSpec.model_validate(renderer_spec)
    except Exception as exc:
        issues.append(f"invalid_renderer_spec: {redact_secrets(exc)}")

    try:
        GeometryRendererResult.model_validate(renderer_result)
    except Exception as exc:
        issues.append(f"invalid_renderer_result: {redact_secrets(exc)}")

    if renderer_result.get("status") != "ok":
        issues.append(
            f"renderer_failed: {renderer_result.get('fail_type', 'unknown')} "
            f"{renderer_result.get('message', '')}"
        )

    renderer_audit_rel = str(renderer_result.get("renderer_audit") or "")
    renderer_audit_path = round_dir / renderer_audit_rel
    if renderer_audit_rel and renderer_audit_path.is_file():
        renderer_audit = _read_json(renderer_audit_path)
        renderer_warnings = renderer_audit.get("warnings")
        if isinstance(renderer_warnings, list):
            for warning in dict.fromkeys(str(item) for item in renderer_warnings):
                if warning.startswith("blocking:") or "unsupported synthetic marker" in warning:
                    issues.append(f"renderer_audit:{warning}")
                else:
                    warnings.append(f"renderer_audit:{warning}")

    fragment_rel = (
        renderer_result.get("tikz_fragment_path")
        or renderer_result.get("tikz_source_path")
        or ""
    )
    fragment_path = round_dir / str(fragment_rel)
    if not fragment_rel or not fragment_path.exists() or fragment_path.stat().st_size == 0:
        issues.append(f"missing_tikz_fragment: {fragment_rel}")

    preview_rel = str(renderer_result.get("preview_png_path") or "")
    preview_path = round_dir / preview_rel
    if not preview_rel or not preview_path.exists() or preview_path.stat().st_size == 0:
        issues.append(f"missing_preview_png: {preview_rel}")

    points = renderer_spec.get("points") if isinstance(renderer_spec.get("points"), dict) else {}
    for name in points:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", str(name)):
            issues.append(f"invalid_point_label: {name}")
        bad = _bad_label_text(name)
        if bad:
            issues.append(bad)

    labels = renderer_spec.get("labels") if isinstance(renderer_spec.get("labels"), dict) else {}
    for name, label in labels.items():
        bad_name = _bad_label_text(name)
        bad_label = _bad_label_text(label)
        if bad_name:
            issues.append(bad_name)
        if bad_label:
            issues.append(bad_label)

    required_markers, required_texts = _visible_requirements(request)
    rendered_markers = renderer_spec.get("markers") if isinstance(renderer_spec.get("markers"), list) else []
    rendered_texts = (
        renderer_spec.get("annotations") if isinstance(renderer_spec.get("annotations"), list) else []
    )
    required_marker_signatures = {_marker_signature(item) for item in required_markers}
    rendered_marker_signatures = {_marker_signature(item) for item in rendered_markers}
    required_text_signatures = {_text_signature(item) for item in required_texts}
    rendered_text_signatures = {_text_signature(item) for item in rendered_texts}
    for signature in sorted(required_marker_signatures - rendered_marker_signatures, key=str):
        issues.append(f"missing_required_marker:{signature}")
    for signature in sorted(required_text_signatures - rendered_text_signatures, key=str):
        issues.append(f"missing_required_text_annotation:{signature}")
    variant = str(request.get("diagram_variant") or request.get("variant") or "prompt")
    disclosure = str(request.get("disclosure_policy") or "clean")
    if variant == "prompt" and disclosure == "clean":
        for signature in sorted(rendered_marker_signatures - required_marker_signatures, key=str):
            issues.append(f"prompt_disallowed_marker:{signature}")
        for signature in sorted(rendered_text_signatures - required_text_signatures, key=str):
            issues.append(f"prompt_disallowed_text_annotation:{signature}")

    _audit_degenerate_geometry(renderer_spec, issues, warnings)

    if renderer_spec.get("status") != "ready":
        issues.append(f"renderer_spec_not_ready: {renderer_spec.get('status', '')}")

    if renderer_spec.get("teaching_focus"):
        warnings.append("teaching_focus is present; ensure it is not rendered as a solution hint")

    audit_result = {
        "schema_version": "diagram-agent-audit/v1",
        "status": "pass" if not issues else "block",
        "round_index": round_index,
        "issues": issues,
        "warnings": warnings,
        "preview_png_path": preview_rel,
        "tikz_fragment_path": fragment_rel,
        "request_disclosure_policy": request.get("disclosure_policy", ""),
    }
    audit_path = round_dir / "audit_result.json"
    _write_json(audit_path, audit_result)
    return {
        "status": "ok" if not issues else "failed",
        "action": "audit",
        "round_index": round_index,
        "audit_result_path": str(audit_path),
        "audit_result": audit_result,
    }
