#!/usr/bin/env python3
"""Run diagram-only acceptance from assignment YAML to rendered PNGs.

This script intentionally starts after assignment-latex/YAML generation.  It
does not compile TeX or inspect PDF layout; it only proves that every diagram
declared in the YAML can drive an independent diagram job to a PNG artifact.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: PyYAML is required") from exc


SCRIPT_DIR = Path(__file__).resolve().parent
VALID_VARIANTS = {"prompt", "solution"}


def read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML object")
    if "sections" not in data and "problems" in data:
        flat: list[dict[str, Any]] = []
        for problem in data.get("problems") or []:
            if isinstance(problem, dict):
                flat.extend(problem.get("sections") or [])
        data = {**data, "sections": flat}
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relpath(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()


def compact_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in ("", None, [])]
    if value in ("", None, []):
        return []
    return [value]


def first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def block_problem_text(block: dict[str, Any]) -> str:
    choices = block.get("choices")
    choice_text = ""
    if isinstance(choices, dict):
        choice_text = " ".join(f"{key}. {value}" for key, value in choices.items())
    return first_text(
        block.get("problem_text"),
        block.get("stem"),
        block.get("stem_latex"),
        block.get("content"),
        block.get("content_latex"),
        choice_text,
    )


def iter_blocks(data: dict[str, Any]):
    for si, section in enumerate(data.get("sections") or []):
        if not isinstance(section, dict):
            continue
        for bi, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict):
                continue
            yield si, bi, block


def diagram_objects_from_block(block: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for key in ("diagram_col", "prompt_diagram"):
        if isinstance(block.get(key), dict):
            found.append((key, block[key]))
    if block.get("type") == "diagram":
        found.append(("diagram", block))
    if block.get("type") == "diagram_row":
        for index, item in enumerate(block.get("items") or block.get("diagrams") or []):
            if isinstance(item, dict):
                found.append((f"diagram_row.items[{index}]", item))
    answer_space = block.get("answer_space")
    if isinstance(answer_space, dict):
        for key in ("diagram_col", "diagram"):
            if isinstance(answer_space.get(key), dict):
                found.append((f"answer_space.{key}", answer_space[key]))
        for index, part in enumerate(answer_space.get("parts") or []):
            if not isinstance(part, dict):
                continue
            for key in ("diagram_col", "prompt_diagram", "diagram"):
                if isinstance(part.get(key), dict):
                    found.append((f"answer_space.parts[{index}].{key}", part[key]))
    return found


def infer_variant(obj: dict[str, Any]) -> str:
    variant = obj.get("variant") or obj.get("diagram_variant")
    if variant in VALID_VARIANTS:
        return str(variant)
    image_path = str(obj.get("image_path") or "")
    return "solution" if "solution" in image_path else "prompt"


def request_from_diagram(
    obj: dict[str, Any],
    block: dict[str, Any],
    job_id: str,
    variant: str,
) -> dict[str, Any]:
    embedded = obj.get("diagram_request")
    request = dict(embedded) if isinstance(embedded, dict) else {}
    problem_text = first_text(
        obj.get("problem_text"),
        request.get("problem_text"),
        block_problem_text(block),
    )
    disclosure_policy = obj.get("disclosure_policy") or request.get("disclosure_policy")
    if not disclosure_policy:
        disclosure_policy = "clean" if variant == "prompt" else "annotated"

    request.update(
        {
            "schema_version": request.get("schema_version", "teaching-diagram-request/v1"),
            "needs_diagram": request.get("needs_diagram", True),
            "diagram_type": obj.get("diagram_type") or request.get("diagram_type") or "synthetic_geometry",
            "diagram_intent": obj.get("diagram_intent") or request.get("diagram_intent") or "student_explanation",
            "diagram_variant": variant,
            "variant": variant,
            "disclosure_policy": disclosure_policy,
            "diagram_job_id": job_id,
            "problem_text": problem_text,
            "objects_hint": obj.get("objects_hint") or request.get("objects_hint") or block.get("objects_hint") or {},
            "teaching_focus": compact_list(
                obj.get("teaching_focus") or request.get("teaching_focus") or block.get("teaching_focus")
            ),
            "must_not_imply": compact_list(obj.get("must_not_imply") or request.get("must_not_imply")),
            "fallback": obj.get("fallback") or request.get("fallback") or "textual_diagram_description",
        }
    )
    reuse = obj.get("reuse_geometry_from") or obj.get("reuse_from") or request.get("reuse_geometry_from")
    if reuse:
        request["reuse_geometry_from"] = str(reuse)
        request["reuse_from"] = str(reuse)
    if obj.get("add_auxiliary") is not None:
        request["add_auxiliary"] = obj.get("add_auxiliary")
    for key in ("max_retries", "seed", "wolfram_timeout_s", "wolfram_hard_timeout_s", "model_config"):
        if key in obj:
            request[key] = obj[key]
    return request


def collect_jobs(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs_by_id: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    image_refs: dict[str, list[dict[str, Any]]] = {}

    for si, bi, block in iter_blocks(data):
        owner = str(block.get("id") or f"sections[{si}].blocks[{bi}]")
        for field, obj in diagram_objects_from_block(block):
            image_path = obj.get("image_path")
            job_id = obj.get("diagram_job_id")
            ref = {
                "owner": owner,
                "field": field,
                "image_path": image_path,
                "diagram_job_id": job_id,
                "reuse_from": obj.get("reuse_from") or obj.get("reuse_geometry_from"),
            }
            if image_path:
                image_refs.setdefault(str(image_path), []).append(ref)
            if not isinstance(job_id, str) or not job_id.strip():
                errors.append({"owner": owner, "field": field, "error": "missing diagram_job_id"})
                continue
            if not isinstance(image_path, str) or not image_path.strip():
                errors.append({"owner": owner, "field": field, "error": "missing image_path"})
                continue
            job_id = job_id.strip()
            variant = infer_variant(obj)
            request = request_from_diagram(obj, block, job_id, variant)
            if not request.get("problem_text") and variant == "prompt":
                errors.append({"owner": owner, "field": field, "job_id": job_id, "error": "missing problem_text"})
            if variant == "solution" and not request.get("reuse_geometry_from"):
                errors.append({"owner": owner, "field": field, "job_id": job_id, "error": "solution job missing reuse_geometry_from"})

            existing = jobs_by_id.get(job_id)
            ref_record = {"owner": owner, "field": field, "image_path": image_path}
            if existing:
                existing["refs"].append(ref_record)
                if existing["variant"] != variant:
                    existing.setdefault("validation_errors", []).append("same diagram_job_id used with multiple variants")
                if existing["image_path"] != image_path:
                    existing.setdefault("validation_errors", []).append("same diagram_job_id used with multiple image_path values")
                continue

            jobs_by_id[job_id] = {
                "diagram_job_id": job_id,
                "variant": variant,
                "image_path": image_path,
                "request": request,
                "refs": [ref_record],
                "validation_errors": [],
            }

    duplicate_errors = []
    for image_path, refs in image_refs.items():
        owners = {ref["owner"] for ref in refs}
        if len(owners) <= 1:
            continue
        missing_reuse = [ref for ref in refs if not ref.get("reuse_from")]
        if len(missing_reuse) > 1:
            duplicate_errors.append(
                {
                    "image_path": image_path,
                    "refs": missing_reuse,
                    "error": "image reused by multiple blocks without explicit reuse_from",
                }
            )
    errors.extend(duplicate_errors)
    return list(jobs_by_id.values()), errors


def expected_image_path(assignment_dir: Path, image_path: str) -> Path:
    path = Path(image_path)
    return path if path.is_absolute() else assignment_dir / path


def check_job_artifacts(job_dir: Path, expected_image: Path) -> dict[str, Any]:
    scene_payloads = sorted(job_dir.glob("rounds/round_*/scene_payload.json"))
    render_results = sorted(job_dir.glob("rounds/round_*/render_result.json"))
    return {
        "workflow_events_exists": (job_dir / "workflow_events.jsonl").exists(),
        "scene_payload_exists": bool(scene_payloads),
        "render_result_exists": bool(render_results),
        "renderer_result_exists": (job_dir / "renderer_result.json").exists(),
        "expected_image_exists": expected_image.exists() and expected_image.stat().st_size > 0,
        "scene_payloads": [relpath(path, job_dir) for path in scene_payloads],
        "render_results": [relpath(path, job_dir) for path in render_results],
    }


def run_command(cmd: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_one_job(
    job: dict[str, Any],
    assignment_dir: Path,
    diagram_root: Path,
    python_executable: str,
    dry_run: bool,
) -> dict[str, Any]:
    job_id = job["diagram_job_id"]
    variant = job["variant"]
    job_dir = diagram_root / "jobs" / job_id
    request_path = job_dir / "diagram-request.json"
    expected_image = expected_image_path(assignment_dir, job["image_path"])

    record = {
        "diagram_job_id": job_id,
        "variant": variant,
        "image_path": job["image_path"],
        "job_dir": str(job_dir),
        "request_path": str(request_path),
        "refs": job["refs"],
        "validation_errors": list(job.get("validation_errors") or []),
        "workflow_status": "not_run",
        "renderer_status": "not_run",
        "success": False,
    }
    if record["validation_errors"]:
        record["failure_reason"] = "; ".join(record["validation_errors"])
        return record

    write_json(request_path, job["request"])
    if dry_run:
        record["workflow_status"] = "dry_run"
        record["renderer_status"] = "dry_run"
        record["success"] = True
        return record

    workflow_cmd = [
        python_executable,
        str(SCRIPT_DIR / "run_diagram_workflow.py"),
        str(request_path),
        "--job-id",
        job_id,
        "--out",
        str(diagram_root),
        "--python",
        python_executable,
    ]
    record["workflow_command"] = run_command(workflow_cmd, SCRIPT_DIR.parent)
    workflow_result_path = job_dir / "workflow_result.json"
    workflow_result = {}
    if workflow_result_path.exists():
        workflow_result = json.loads(workflow_result_path.read_text(encoding="utf-8"))
    record["workflow_status"] = workflow_result.get("status", "missing_workflow_result")

    if record["workflow_command"]["returncode"] == 0 and record["workflow_status"] == "ok":
        renderer_cmd = [
            python_executable,
            str(SCRIPT_DIR / "render_geometry_spec.py"),
            str(job_dir / "final_renderer_spec.json"),
            "--out-dir",
            str(job_dir),
            "--variant",
            variant,
        ]
        record["renderer_command"] = run_command(renderer_cmd, SCRIPT_DIR.parent)
        renderer_result_path = job_dir / "renderer_result.json"
        renderer_result = {}
        if renderer_result_path.exists():
            renderer_result = json.loads(renderer_result_path.read_text(encoding="utf-8"))
        record["renderer_status"] = renderer_result.get("status", "missing_renderer_result")
    else:
        record["renderer_status"] = "skipped"

    artifact_checks = check_job_artifacts(job_dir, expected_image)
    record["artifact_checks"] = artifact_checks
    solution_check = {}
    if workflow_result:
        solution_check = workflow_result.get("solution_reuse_check") or {}
    record["solution_reuse_check"] = solution_check
    record["success"] = (
        record["workflow_status"] == "ok"
        and record["renderer_status"] == "ok"
        and artifact_checks["workflow_events_exists"]
        and artifact_checks["scene_payload_exists"]
        and artifact_checks["render_result_exists"]
        and artifact_checks["renderer_result_exists"]
        and artifact_checks["expected_image_exists"]
        and (variant != "solution" or solution_check.get("locked_points_same") is True)
    )
    if not record["success"]:
        record["failure_reason"] = (
            workflow_result.get("error")
            or workflow_result.get("reason")
            or record.get("renderer_status")
            or "diagram job failed"
        )
    return record


def run_jobs(
    jobs: list[dict[str, Any]],
    assignment_dir: Path,
    diagram_root: Path,
    python_executable: str,
    max_workers: int,
    dry_run: bool,
) -> list[dict[str, Any]]:
    prompt_jobs = [job for job in jobs if job["variant"] != "solution"]
    solution_jobs = [job for job in jobs if job["variant"] == "solution"]
    results: list[dict[str, Any]] = []
    for wave in (prompt_jobs, solution_jobs):
        if not wave:
            continue
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(run_one_job, job, assignment_dir, diagram_root, python_executable, dry_run)
                for job in wave
            ]
            for future in as_completed(futures):
                results.append(future.result())
    return sorted(results, key=lambda item: item["diagram_job_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run diagram-only acceptance from assignment YAML")
    parser.add_argument("assignment", type=Path, help="Path to assignment.yaml")
    parser.add_argument("--out-dir", type=Path, help="Diagram root; defaults to <assignment-dir>/diagram")
    parser.add_argument("--report", type=Path, help="Report path; defaults to <diagram-root>/diagram_acceptance_report.json")
    parser.add_argument("--python", default=sys.executable, help="Python executable for workflow subprocesses")
    parser.add_argument("--jobs", type=int, default=4, help="Maximum parallel prompt/solution jobs per wave")
    parser.add_argument("--dry-run", action="store_true", help="Only scan YAML and write job requests/report")
    args = parser.parse_args()

    assignment_path = args.assignment.resolve()
    assignment_dir = assignment_path.parent
    diagram_root = (args.out_dir or (assignment_dir / "diagram")).resolve()
    report_path = (args.report or (diagram_root / "diagram_acceptance_report.json")).resolve()
    data = read_yaml(assignment_path)
    jobs, collection_errors = collect_jobs(data)
    results = run_jobs(
        jobs,
        assignment_dir,
        diagram_root,
        args.python,
        max(1, args.jobs),
        args.dry_run,
    )
    success_count = sum(1 for result in results if result.get("success"))
    failed_count = len(results) - success_count
    report = {
        "schema_version": "diagram-acceptance-report/v1",
        "assignment": str(assignment_path),
        "diagram_root": str(diagram_root),
        "dry_run": args.dry_run,
        "job_count": len(jobs),
        "success_count": success_count,
        "failed_count": failed_count,
        "collection_errors": collection_errors,
        "jobs": results,
        "status": "ok" if not collection_errors and failed_count == 0 else "failed",
    }
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
