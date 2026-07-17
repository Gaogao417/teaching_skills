from __future__ import annotations

import json
from pathlib import Path

from diagram_contracts import (
    DiagramGateCheck,
    DiagramGateReport,
    DiagramJob,
    DiagramJobRequest,
)


def _read(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _artifact(job_dir: Path, value: object) -> Path | None:
    text = str(value or "")
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else job_dir / path


def run_job_package_gate(
    job: DiagramJob,
    request: DiagramJobRequest,
    job_dir: Path,
) -> DiagramGateReport:
    """Validate the one bindable package emitted by a single job owner."""

    checks: list[DiagramGateCheck] = []
    execution = _read(job_dir / "execution_plan.json")
    workflow = _read(job_dir / "workflow_result.json")
    renderer = _read(job_dir / "renderer_result.json")
    expected_plan = request.execution_plan.model_dump(mode="json") if request.execution_plan else {}

    if execution != expected_plan:
        checks.append(
            DiagramGateCheck(
                name="job_execution_plan_lock",
                status="block",
                message="execution_plan.json is missing or differs from the planned request",
                refs=[job.job_id],
            )
        )
    if workflow.get("status") != "ok":
        checks.append(
            DiagramGateCheck(
                name="job_workflow_status",
                status="block",
                message=f"workflow status is {workflow.get('status', 'missing')}",
                refs=[job.job_id],
            )
        )
    if renderer.get("status") != "ok":
        checks.append(
            DiagramGateCheck(
                name="job_renderer_status",
                status="block",
                message=f"renderer status is {renderer.get('status', 'missing')}",
                refs=[job.job_id],
            )
        )

    fragment = _artifact(
        job_dir,
        renderer.get("tikz_fragment_path") or renderer.get("tikz_source_path"),
    )
    if fragment is None or not fragment.is_file() or fragment.stat().st_size == 0:
        checks.append(
            DiagramGateCheck(
                name="job_tikz_fragment",
                status="block",
                message="bindable TikZ fragment is missing or empty",
                refs=[job.job_id],
            )
        )

    preview = _artifact(
        job_dir,
        renderer.get("preview_png_path") or renderer.get("preview_svg"),
    )
    if preview is None or not preview.is_file() or preview.stat().st_size == 0:
        checks.append(
            DiagramGateCheck(
                name="job_preview",
                status="warn",
                message="renderer package has no durable preview; TikZ remains bindable",
                refs=[job.job_id],
            )
        )

    if not (job_dir / "final_renderer_spec.json").is_file():
        checks.append(
            DiagramGateCheck(
                name="job_renderer_spec",
                status="block",
                message="final_renderer_spec.json is missing",
                refs=[job.job_id],
            )
        )
    if not (job_dir / "semantic_provenance.json").is_file():
        checks.append(
            DiagramGateCheck(
                name="job_semantic_provenance",
                status="block",
                message="semantic_provenance.json is missing",
                refs=[job.job_id],
            )
        )

    statuses = {check.status for check in checks}
    status = "block" if "block" in statuses else "warn" if "warn" in statuses else "pass"
    return DiagramGateReport(
        assignment_id=request.assignment_id,
        status=status,
        checks=checks,
    )
