from __future__ import annotations

from pathlib import Path

import yaml

from diagram_contracts import (
    DiagramGateCheck,
    DiagramVariant,
    DisclosurePolicy,
    RendererBindingManifest,
)


def _check_prompt_clean(
    artifacts: RendererBindingManifest,
) -> list[DiagramGateCheck]:
    """Prompt diagrams must not include annotated or solution-only disclosures."""
    checks: list[DiagramGateCheck] = []
    for art in artifacts.bindings.values():
        if art.variant == DiagramVariant.PROMPT and art.disclosure_policy != DisclosurePolicy.CLEAN:
            checks.append(DiagramGateCheck(
                name="prompt_clean_policy",
                status="block",
                message=f"Prompt artifact '{art.slot_id}' has disclosure_policy='{art.disclosure_policy.value}', expected 'clean'",
                refs=[art.slot_id],
            ))
    return checks


def _check_student_no_solution(
    resolved_path: Path | None,
) -> list[DiagramGateCheck]:
    """Student resolved YAML must not reference solution or annotated diagrams."""
    checks: list[DiagramGateCheck] = []
    if resolved_path is None or not resolved_path.exists():
        return checks

    data = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return checks

    meta = data.get("meta")
    is_student = False
    if isinstance(meta, dict):
        version = str(meta.get("version", "")).lower()
        is_student = "student" in version

    if not is_student:
        return checks

    for section in data.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks") or []:
            if not isinstance(block, dict):
                continue
            for obj in _collect_resolved_diagrams(block):
                variant = obj.get("variant", "")
                policy = obj.get("disclosure_policy", "")
                if variant == "solution":
                    checks.append(DiagramGateCheck(
                        name="student_no_solution",
                        status="block",
                        message="Student resolved YAML references variant='solution' diagram",
                        refs=[obj.get("diagram_ref", "")],
                    ))
                if policy == "annotated":
                    checks.append(DiagramGateCheck(
                        name="student_no_annotated",
                        status="block",
                        message="Student resolved YAML references disclosure_policy='annotated' diagram",
                        refs=[obj.get("diagram_ref", "")],
                    ))
    return checks


def _collect_resolved_diagrams(block: dict) -> list[dict]:
    """Collect resolved TikZ diagram objects from a block and answer space."""
    found = []
    for key in ("diagram_col", "prompt_diagram"):
        obj = block.get(key)
        if isinstance(obj, dict) and (obj.get("kind") == "tikz" or obj.get("tikz_code") or obj.get("tikz_path")):
            found.append(obj)
    answer_space = block.get("answer_space")
    if isinstance(answer_space, dict):
        for key in ("diagram_col",):
            obj = answer_space.get(key)
            if isinstance(obj, dict) and (obj.get("kind") == "tikz" or obj.get("tikz_code") or obj.get("tikz_path")):
                found.append(obj)
        for part in answer_space.get("parts") or []:
            if not isinstance(part, dict):
                continue
            for key in ("diagram_col",):
                obj = part.get(key)
                if isinstance(obj, dict) and (obj.get("kind") == "tikz" or obj.get("tikz_code") or obj.get("tikz_path")):
                    found.append(obj)
    return found


def _walk(value: object):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _resolved_data(resolved_path: Path | None) -> dict[str, object]:
    if resolved_path is None or not resolved_path.is_file():
        return {}
    value = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _check_resolved_no_slots(resolved_path: Path | None) -> list[DiagramGateCheck]:
    data = _resolved_data(resolved_path)
    refs = [str(node.get("slot_id") or "") for node in _walk(data) if "diagram_slot" in node]
    if not refs:
        return []
    return [
        DiagramGateCheck(
            name="resolved_no_diagram_slot",
            status="block",
            message="Resolved assignment still contains diagram_slot declarations",
            refs=[ref for ref in refs if ref],
        )
    ]


def _check_resolved_binding_integrity(
    resolved_path: Path | None,
    artifacts: RendererBindingManifest,
) -> list[DiagramGateCheck]:
    data = _resolved_data(resolved_path)
    checks: list[DiagramGateCheck] = []
    for node in _walk(data):
        if not (
            node.get("kind") == "tikz"
            or node.get("tikz_code")
            or node.get("tikz_path")
        ):
            continue
        diagram_ref = str(node.get("diagram_ref") or "")
        binding = artifacts.bindings.get(diagram_ref)
        if binding is None or not binding.bindable:
            checks.append(
                DiagramGateCheck(
                    name="resolved_binding_integrity",
                    status="block",
                    message=f"Resolved diagram '{diagram_ref}' has no bindable manifest entry",
                    refs=[diagram_ref],
                )
            )
            continue
        mismatches: list[str] = []
        if str(node.get("diagram_job_id") or node.get("job_id") or "") != binding.job_id:
            mismatches.append("job_id")
        if str(node.get("artifact_hash") or node.get("hash") or "") != binding.artifact_hash:
            mismatches.append("hash")
        if str(node.get("variant") or "prompt") != binding.variant.value:
            mismatches.append("variant")
        if str(node.get("disclosure_policy") or "clean") != binding.disclosure_policy.value:
            mismatches.append("disclosure_policy")
        if mismatches:
            checks.append(
                DiagramGateCheck(
                    name="resolved_binding_integrity",
                    status="block",
                    message=f"Resolved diagram '{diagram_ref}' mismatches binding fields: {mismatches}",
                    refs=[diagram_ref],
                )
            )
    return checks
