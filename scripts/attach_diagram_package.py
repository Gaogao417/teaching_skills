#!/usr/bin/env python3
"""Attach a DiagramPackage to an HTML or assignment.yaml artifact."""

from __future__ import annotations

import argparse
import json
import os
import re
from html import escape
from pathlib import Path
from typing import Any

import yaml


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relpath(target: Path, start_file: Path) -> str:
    return Path(os.path.relpath(Path(target).resolve(), start_file.resolve().parent)).as_posix()


def artifact_path(root: Path, rel_or_abs: str | None) -> Path | None:
    if not rel_or_abs:
        return None
    path = Path(rel_or_abs)
    return path if path.is_absolute() else root / path


def build_package(diagram_dir: Path, target: Path, caption: str | None) -> dict[str, Any]:
    result_path = diagram_dir / "workflow_result.json"
    result = read_json(result_path)
    spec_path = diagram_dir / result.get("final_diagram_spec", "final_diagram_spec.json")
    spec = read_json(spec_path) if spec_path.exists() else {}
    renderer_spec_rel = result.get("final_renderer_spec") or spec.get("renderer_spec_path")
    renderer_spec_path = artifact_path(diagram_dir, renderer_spec_rel)
    renderer_result_rel = result.get("renderer_result") or spec.get("renderer_result_path") or "renderer_result.json"
    renderer_result_path = artifact_path(diagram_dir, renderer_result_rel)
    renderer_result = read_json(renderer_result_path) if renderer_result_path and renderer_result_path.exists() else {}
    image_path = artifact_path(diagram_dir, renderer_result.get("image_path"))
    image_exists = bool(image_path and image_path.exists())
    workflow_status = result.get("status", "failed")
    renderer_status = renderer_result.get("status", "missing")
    status = "ok" if workflow_status == "ok" and renderer_status == "ok" and image_exists else "pending_renderer"
    if workflow_status != "ok":
        status = workflow_status
    elif renderer_status not in {"ok", "missing"}:
        status = "renderer_failed"
    fallback = result.get("fallback", "使用题干文字描述或教师手动画图建议。")
    if workflow_status == "ok" and renderer_status == "missing":
        fallback = "图形坐标规格已生成，但 renderer_result.json 或 PNG 尚未生成；先按题干文字关系观察。"
    elif workflow_status == "ok" and renderer_status == "ok" and not image_exists:
        fallback = "renderer_result.json 已生成，但最终 PNG 不存在；先按题干文字关系观察。"
    elif workflow_status == "ok" and renderer_status != "ok":
        fallback = renderer_result.get("message") or fallback
    package = {
        "schema_version": "teaching-diagram-package/v1",
        "status": status,
        "workflow_status": workflow_status,
        "renderer_status": renderer_status,
        "workflow_result": relpath(result_path, target),
        "diagram_spec": relpath(spec_path, target) if spec_path.exists() else "",
        "renderer_spec": relpath(renderer_spec_path, target)
        if renderer_spec_path and renderer_spec_path.exists()
        else "",
        "renderer_result": relpath(renderer_result_path, target)
        if renderer_result_path and renderer_result_path.exists()
        else "",
        "image_path": relpath(image_path, target) if image_exists else "",
        "caption": caption or "观察图形中的关键对象和关系。",
        "teaching_focus": spec.get("renderer_spec", {}).get(
            "teaching_focus",
            spec.get("diagram_spec", {}).get("teaching_focus", []),
        ),
        "fallback": fallback,
    }
    return package


def diagram_block(package: dict[str, Any], block_id: str, fallback_type: str) -> dict[str, Any]:
    if package.get("status") == "ok" and package.get("image_path"):
        return {
            "type": "diagram",
            "id": block_id,
            "image_path": package["image_path"],
            "caption": package.get("caption", ""),
            "teaching_focus": package.get("teaching_focus", []),
            "source": {
                "workflow_result": package.get("workflow_result", ""),
                "diagram_spec": package.get("diagram_spec", ""),
                "renderer_spec": package.get("renderer_spec", ""),
                "renderer_result": package.get("renderer_result", ""),
            },
        }
    fallback = package.get("fallback", "本题图形生成未成功，先按题干文字关系手动画图。")
    if fallback_type == "hint":
        return {
            "type": "hint",
            "id": f"{block_id}-fallback",
            "content": fallback,
            "level": 1,
        }
    if fallback_type == "step":
        return {
            "type": "step",
            "id": f"{block_id}-fallback",
            "title": "图形提示",
            "content": fallback,
        }
    return {
        "type": "reading_tip",
        "id": f"{block_id}-fallback",
        "items": [{"latex": fallback}],
    }


def insert_block(blocks: list[dict[str, Any]], block: dict[str, Any]) -> None:
    block_id = block.get("id")
    if block_id and any(item.get("id") == block_id for item in blocks):
        return
    insert_at = 1 if blocks and blocks[0].get("type") == "problemcard" else 0
    blocks.insert(insert_at, block)


def attach_yaml(target: Path, package: dict[str, Any], block_id: str) -> None:
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("assignment YAML must be a mapping")
    meta = data.setdefault("meta", {})
    source_artifacts = meta.setdefault("source_artifacts", {})
    source_artifacts["diagram_package"] = package.get("workflow_result", "")
    if package.get("renderer_result"):
        source_artifacts["diagram_renderer_result"] = package["renderer_result"]
    package_path = target.with_suffix(".diagram-package.json")
    write_json(package_path, package)

    sections = data.get("sections") or []
    if not sections:
        raise ValueError("assignment YAML has no sections")
    blocks = sections[0].setdefault("blocks", [])
    template = data.get("render", {}).get("template", "")
    fallback_type = "step" if "practice" in template else "hint"
    insert_block(blocks, diagram_block(package, block_id, fallback_type))
    target.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def html_figure(package: dict[str, Any]) -> str:
    if package.get("status") == "ok" and package.get("image_path"):
        caption = escape(package.get("caption", "观察图形中的关键对象和关系。"))
        image_path = escape(package["image_path"])
        return (
            '\n  <figure class="edu-diagram u-avoid-break">\n'
            f'    <img class="edu-diagram-image" src="{image_path}" alt="{caption}">\n'
            f'    <figcaption class="edu-diagram-caption">{caption}</figcaption>\n'
            "  </figure>\n"
        )
    return (
        '\n  <aside class="edu-teacher-note no-print">\n'
        '    <div class="edu-card-title">图形生成降级</div>\n'
        f'    <p class="edu-p">{escape(package.get("fallback", "本题图形生成未成功，先按题干文字关系手动画图。"))}</p>\n'
        "  </aside>\n"
    )


def attach_html(target: Path, package: dict[str, Any]) -> None:
    package_path = target.with_suffix(".diagram-package.json")
    write_json(package_path, package)
    html = target.read_text(encoding="utf-8")
    if "class=\"edu-diagram" in html or "class='edu-diagram" in html:
        return
    figure = html_figure(package)
    pattern = re.compile(r"(<section\s+class=[\"']edu-problem-card[\"'][\s\S]*?</section>)", re.IGNORECASE)
    if pattern.search(html):
        html = pattern.sub(r"\1" + figure, html, count=1)
    else:
        html = html.replace('<section class="edu-section">', figure + '\n<section class="edu-section">', 1)
    target.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach a local DiagramPackage to YAML or HTML")
    parser.add_argument("diagram_dir", type=Path, help="Directory containing workflow_result.json")
    parser.add_argument("target", type=Path, help="Target .assignment.yaml/.yaml or .html artifact")
    parser.add_argument("--caption", help="Caption for the inserted diagram")
    parser.add_argument("--id", default="fig-main", help="Diagram block id for YAML targets")
    args = parser.parse_args()

    diagram_dir = args.diagram_dir.resolve()
    target = args.target.resolve()
    package = build_package(diagram_dir, target, args.caption)
    suffixes = "".join(target.suffixes)
    if suffixes.endswith(".html"):
        attach_html(target, package)
    elif suffixes.endswith(".yaml") or suffixes.endswith(".yml"):
        attach_yaml(target, package, args.id)
    else:
        raise ValueError(f"Unsupported target type: {target}")
    print(target)


if __name__ == "__main__":
    main()
