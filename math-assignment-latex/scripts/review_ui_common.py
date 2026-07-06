#!/usr/bin/env python3
"""Shared helpers for assignment YAML review UIs."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
RENDER_SCRIPT = SCRIPT_DIR / "render_assignment.py"
VALIDATE_SCRIPT = SCRIPT_DIR / "validate_assignment.py"
COMPILE_SCRIPT = SCRIPT_DIR / "compile_latex.sh"


def load_assignment(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def dump_assignment(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False, width=120)


def template_name(data: dict[str, Any]) -> str:
    render = data.get("render")
    if not isinstance(render, dict):
        return "exam-zh-practice"
    return str(render.get("template") or "exam-zh-practice")


def assert_template(data: dict[str, Any], expected: str, path: Path) -> None:
    actual = template_name(data)
    if actual != expected:
        raise ValueError(f"{path} uses render.template={actual!r}; expected {expected!r}")


def reviewed_path(path: Path) -> Path:
    name = path.name
    if name.endswith(".assignment.yaml"):
        return path.with_name(name[: -len(".assignment.yaml")] + ".reviewed.assignment.yaml")
    return path.with_suffix(path.suffix + ".reviewed.yaml")


def preview_tex_path(path: Path, label: str = "") -> Path:
    prefix = "review-preview"
    if label:
        prefix += f"-{label}"
    stem = path.name
    if stem.endswith(".assignment.yaml"):
        stem = stem[: -len(".assignment.yaml")]
    else:
        stem = path.stem
    return path.parent / f"{prefix}-{stem}.tex"


def contains_key(obj: Any, key: str) -> bool:
    if isinstance(obj, dict):
        return key in obj or any(contains_key(value, key) for value in obj.values())
    if isinstance(obj, list):
        return any(contains_key(item, key) for item in obj)
    return False


def validate_data(data: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", suffix=".assignment.yaml", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False, width=120)
    try:
        result = run_command([sys.executable, str(VALIDATE_SCRIPT), str(temp_path)], cwd=base_dir)
    finally:
        temp_path.unlink(missing_ok=True)
    return result


def render_data(data: dict[str, Any], *, source_path: Path, out_path: Path) -> dict[str, Any]:
    if contains_key(data, "diagram_slot"):
        return {
            "ok": False,
            "returncode": 2,
            "stdout": "",
            "stderr": "YAML still contains diagram_slot. Run the diagram renderer before LaTeX render.",
            "out": str(out_path),
        }
    with tempfile.NamedTemporaryFile("w", suffix=".assignment.yaml", encoding="utf-8", delete=False) as handle:
        temp_path = Path(handle.name)
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False, width=120)
    try:
        result = run_command(
            [sys.executable, str(RENDER_SCRIPT), str(temp_path), "--out", str(out_path)],
            cwd=source_path.parent,
        )
    finally:
        temp_path.unlink(missing_ok=True)
    result["out"] = str(out_path)
    if out_path.exists():
        result["latex"] = out_path.read_text(encoding="utf-8")
    return result


def compile_tex(tex_path: Path) -> dict[str, Any]:
    return run_command(["bash", str(COMPILE_SCRIPT), str(tex_path)], cwd=tex_path.parent)


def run_command(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=120)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "cmd": cmd,
    }


def write_agent_request(
    *,
    mode: str,
    artifact_dir: Path,
    source_paths: dict[str, str],
    selection: dict[str, Any],
    instruction: str,
) -> Path:
    payload = {
        "mode": mode,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_paths": source_paths,
        "selection": selection,
        "instruction": instruction,
    }
    path = artifact_dir / f"{mode}_review_request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def public_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def clone_data(data: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(data)


def summarize_sections(data: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for index, section in enumerate(data.get("sections") or []):
        blocks = section.get("blocks") or []
        counts: dict[str, int] = {}
        for block in blocks:
            block_type = str(block.get("type") or "unknown")
            counts[block_type] = counts.get(block_type, 0) + 1
        summaries.append(
            {
                "index": index,
                "id": section.get("id", ""),
                "title": section.get("title", ""),
                "type": section.get("type", ""),
                "visibility": section.get("visibility", ""),
                "block_count": len(blocks),
                "counts": counts,
            }
        )
    return summaries
