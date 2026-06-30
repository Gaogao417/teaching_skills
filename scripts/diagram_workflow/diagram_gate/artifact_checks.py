from __future__ import annotations

import hashlib
import json
from pathlib import Path

from diagram_contracts import (
    AssignmentPlanDiagramView,
    DiagramGateCheck,
    DiagramJobsManifest,
    RendererBindingManifest,
)


def _check_required_bindable(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
) -> list[DiagramGateCheck]:
    """Required slots must have a renderer artifact that the resolver can bind."""
    checks: list[DiagramGateCheck] = []
    for job in jobs.jobs:
        if not job.required:
            continue
        art = artifacts.bindings.get(job.diagram_ref)
        if not art or not art.bindable:
            checks.append(DiagramGateCheck(
                name="required_bindable",
                status="block",
                message=f"Required slot '{job.slot_id}' has no bindable artifact",
                refs=[job.slot_id],
            ))
    return checks


def _check_tikz_payload_exists(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """Bindable artifacts must carry inline TikZ or a non-empty TikZ source path."""
    checks: list[DiagramGateCheck] = []
    for art in artifacts.bindings.values():
        if art.tikz_fragment:
            continue
        path_value = art.tikz_fragment_path or art.tikz_source_path
        if not path_value:
            if art.bindable:
                checks.append(DiagramGateCheck(
                    name="tikz_payload_exists",
                    status="block",
                    message=f"Bindable TikZ artifact has no tikz_fragment or tikz path: {art.slot_id}",
                    refs=[art.slot_id],
                ))
            continue
        source_path = Path(path_value)
        full_path = source_path if source_path.is_absolute() else artifact_dir / source_path
        if not full_path.exists():
            checks.append(DiagramGateCheck(
                name="tikz_payload_exists",
                status="warn",
                message=f"TikZ source file missing: {path_value}",
                refs=[art.slot_id],
            ))
        elif full_path.stat().st_size == 0:
            checks.append(DiagramGateCheck(
                name="tikz_payload_exists",
                status="block",
                message=f"TikZ source file is empty: {path_value}",
                refs=[art.slot_id],
            ))
    return checks


def _check_content_hash(
    jobs: DiagramJobsManifest,
    plan_data: AssignmentPlanDiagramView | dict[str, object],
) -> list[DiagramGateCheck]:
    """Warn when jobs were collected from an older version of the plan YAML."""
    checks: list[DiagramGateCheck] = []
    plan_view = (
        plan_data
        if isinstance(plan_data, AssignmentPlanDiagramView)
        else AssignmentPlanDiagramView.model_validate(plan_data)
    )
    current_hashes: dict[str, str] = {}
    for section in plan_view.sections:
        for block in section.blocks:
            slots = []
            if block.diagram_slot is not None:
                slots.append(block.diagram_slot)
            if block.answer_space is not None:
                if block.answer_space.diagram_slot is not None:
                    slots.append(block.answer_space.diagram_slot)
                slots.extend(
                    part.diagram_slot
                    for part in block.answer_space.parts
                    if part.diagram_slot is not None
                )
            for slot in slots:
                slot_data = slot.model_dump(mode="json", by_alias=True)
                canonical = json.dumps(slot_data, sort_keys=True, ensure_ascii=False)
                current_hashes[slot.slot_id] = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    for job in jobs.jobs:
        current = current_hashes.get(job.slot_id)
        if current and job.content_hash and current != job.content_hash:
            checks.append(DiagramGateCheck(
                name="content_hash_stale",
                status="warn",
                message=f"Job '{job.job_id}' content_hash is stale (plan YAML has changed)",
                refs=[job.slot_id],
            ))
    return checks


def _check_tikz_path_accessible(
    artifacts: RendererBindingManifest,
    artifact_dir: Path,
) -> list[DiagramGateCheck]:
    """TikZ paths in renderer bindings must resolve from the artifact root."""
    checks: list[DiagramGateCheck] = []
    for art in artifacts.bindings.values():
        path_value = art.tikz_fragment_path or art.tikz_source_path
        if not path_value:
            continue
        p = Path(path_value)
        if p.is_absolute():
            if not p.exists():
                checks.append(DiagramGateCheck(
                    name="tikz_path_accessible",
                    status="block",
                    message=f"Absolute tikz_path does not exist: {path_value}",
                    refs=[art.slot_id],
                ))
        else:
            full = artifact_dir / p
            if not full.exists():
                checks.append(DiagramGateCheck(
                    name="tikz_path_accessible",
                    status="warn",
                    message=f"Relative tikz_path not found from artifact dir: {path_value}",
                    refs=[art.slot_id],
                ))
    return checks


def _check_diagram_ref_consistency(
    jobs: DiagramJobsManifest,
    artifacts: RendererBindingManifest,
) -> list[DiagramGateCheck]:
    """Renderer bindings should point back to refs declared by the jobs manifest."""
    checks: list[DiagramGateCheck] = []
    job_refs = {job.diagram_ref for job in jobs.jobs}
    for diagram_ref in artifacts.bindings:
        if diagram_ref not in job_refs:
            checks.append(DiagramGateCheck(
                name="diagram_ref_consistency",
                status="warn",
                message=f"Renderer binding with ref '{diagram_ref}' has no matching job slot",
                refs=[diagram_ref],
            ))
    return checks
