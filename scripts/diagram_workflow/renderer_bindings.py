from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from diagram_contracts import (
    DiagramJobsManifest,
    DiagramRunStatus,
    RendererBinding,
    RendererBindingManifest,
)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        payload = data.model_dump(mode="json", by_alias=True)
    else:
        payload = data
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _relative_to_artifact_dir(path: Path, artifact_dir: Path) -> str:
    return Path(os.path.relpath(path.resolve(), artifact_dir.resolve())).as_posix()


def _resolve_existing_source(
    *,
    path_value: str,
    job_dir: Path,
    artifact_dir: Path,
) -> tuple[Path | None, str]:
    if not path_value:
        return None, ""
    raw_path = Path(path_value)
    candidates = [raw_path] if raw_path.is_absolute() else [job_dir / raw_path, artifact_dir / raw_path]
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate, _relative_to_artifact_dir(candidate, artifact_dir)
    return None, path_value


def build_renderer_binding(
    *,
    job: object,
    job_dir: Path,
    artifact_dir: Path,
) -> RendererBinding:
    rr_data = read_json(job_dir / "renderer_result.json")
    wf_data = read_json(job_dir / "workflow_result.json")
    warnings: list[str] = []

    if rr_data and rr_data.get("status") == "ok":
        status = DiagramRunStatus.OK
    else:
        status = DiagramRunStatus.FAILED

    tikz_fragment = ""
    tikz_fragment_path = ""
    tikz_source_path = ""
    tikz_standalone_path = ""
    tikz_pdf_path = ""
    preview_png_path = ""
    preview_svg = ""
    renderer_audit = ""

    if rr_data:
        tikz_fragment = str(rr_data.get("tikz_fragment") or "")
        tikz_fragment_path = str(rr_data.get("tikz_fragment_path") or "")
        tikz_source_path = str(rr_data.get("tikz_source_path") or "")
        tikz_standalone_path = str(rr_data.get("tikz_standalone_path") or "")
        tikz_pdf_path = str(rr_data.get("tikz_pdf_path") or "")
        preview_png_path = str(rr_data.get("preview_png_path") or "")
        preview_svg = str(rr_data.get("preview_svg") or "")
        renderer_audit = str(rr_data.get("renderer_audit") or "")
        if rr_data.get("status") not in {"ok", None}:
            warnings.append(f"renderer status: {rr_data.get('status', 'unknown')}")
        if rr_data.get("status") == "ok" and not (tikz_fragment or tikz_fragment_path or tikz_source_path):
            warnings.append("ok renderer_result missing TikZ payload")
    else:
        warnings.append("renderer_result.json missing or invalid")

    artifact_hash = ""
    source_path = None
    normalized_path = ""
    for path_value, field in ((tikz_fragment_path, "fragment"), (tikz_source_path, "source")):
        source_path, normalized_path = _resolve_existing_source(
            path_value=path_value,
            job_dir=job_dir,
            artifact_dir=artifact_dir,
        )
        if source_path:
            artifact_hash = sha256_file(source_path)
            if field == "fragment":
                tikz_fragment_path = normalized_path
            else:
                tikz_source_path = normalized_path
            break
        if path_value:
            warnings.append(f"TikZ source file missing or empty: {path_value}")

    if not artifact_hash and tikz_fragment:
        artifact_hash = sha256_text(tikz_fragment)

    if wf_data:
        warnings.extend(str(item) for item in (wf_data.get("policy_warnings") or []))

    bindable = bool(status == DiagramRunStatus.OK and artifact_hash and (tikz_fragment or tikz_fragment_path or tikz_source_path))
    rel_prefix = f"build/diagram/jobs/{job.job_id}"
    return RendererBinding(
        slot_id=job.slot_id,
        diagram_ref=job.diagram_ref,
        job_id=job.job_id,
        status=status,
        bindable=bindable,
        variant=job.variant,
        disclosure_policy=job.disclosure_policy,
        tikz_fragment=tikz_fragment,
        tikz_fragment_path=tikz_fragment_path,
        tikz_source_path=tikz_source_path,
        tikz_standalone_path=tikz_standalone_path,
        tikz_pdf_path=tikz_pdf_path,
        preview_png_path=preview_png_path,
        preview_svg=preview_svg,
        renderer_audit=renderer_audit,
        renderer_result=f"{rel_prefix}/renderer_result.json" if (job_dir / "renderer_result.json").exists() else "",
        workflow_result=f"{rel_prefix}/workflow_result.json" if (job_dir / "workflow_result.json").exists() else "",
        final_renderer_spec=f"{rel_prefix}/final_renderer_spec.json" if (job_dir / "final_renderer_spec.json").exists() else "",
        hash=artifact_hash,
        warnings=warnings,
    )


def build_renderer_binding_manifest(
    jobs_manifest: DiagramJobsManifest,
    jobs_dir: Path,
    artifact_dir: Path,
) -> RendererBindingManifest:
    bindings: dict[str, RendererBinding] = {}
    for job in jobs_manifest.jobs:
        job_dir = jobs_dir / job.job_id
        if not job_dir.exists():
            bindings[job.diagram_ref] = RendererBinding(
                slot_id=job.slot_id,
                diagram_ref=job.diagram_ref,
                job_id=job.job_id,
                variant=job.variant,
                disclosure_policy=job.disclosure_policy,
                status=DiagramRunStatus.FAILED,
                bindable=False,
                warnings=["job directory not found"],
            )
            continue
        bindings[job.diagram_ref] = build_renderer_binding(
            job=job,
            job_dir=job_dir,
            artifact_dir=artifact_dir,
        )
    return RendererBindingManifest(
        assignment_id=jobs_manifest.assignment_id,
        source_jobs="build/diagram/diagram_jobs.json",
        bindings=bindings,
    )


def manifest_from_paths(jobs_path: Path, jobs_dir: Path, artifact_dir: Path) -> RendererBindingManifest:
    jobs_raw = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs_manifest = DiagramJobsManifest(**jobs_raw)
    return build_renderer_binding_manifest(jobs_manifest, jobs_dir, artifact_dir)
