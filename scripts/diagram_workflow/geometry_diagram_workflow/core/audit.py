from __future__ import annotations

import re
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

