#!/usr/bin/env python3
"""Build staged single-item assignments and deterministic crops from authoring YAML."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from question_bank_repo import find_repo_root


REPO_ROOT = find_repo_root()
TEACHER_ONLY_KEYS = {
    "answer",
    "clue",
    "solution_steps",
    "solution_notes",
    "source_solution_images",
    "teaching",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def crop_asset(spec: dict[str, Any], item_dir: Path) -> dict[str, Any]:
    source = (REPO_ROOT / spec["source"]).resolve()
    output = item_dir / "assets" / spec["file"]
    box = tuple(int(value) for value in spec["box"])
    with Image.open(source) as image:
        width, height = image.size
        left, top, right, bottom = box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError(f"{spec['file']}: invalid crop {box} for {width}x{height}")
        output.parent.mkdir(parents=True, exist_ok=True)
        image.crop(box).save(output)
    return {
        "source": Path(spec["source"]).as_posix(),
        "source_sha256": sha256(source),
        "box_px": list(box),
        "output": f"assets/{spec['file']}",
        "output_sha256": sha256(output),
    }


def strip_teacher_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: strip_teacher_fields(child)
            for key, child in value.items()
            if key not in TEACHER_ONLY_KEYS
        }
    if isinstance(value, list):
        return [strip_teacher_fields(child) for child in value]
    return value


def assignment(item: dict[str, Any], paper: dict[str, Any]) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": item["question_type"],
        "id": item["id"],
        "points": item["points"],
        "stem_latex": item["stem_latex"],
        "answer": item["answer"],
    }
    for key in ("choices", "subquestions", "fillin_type", "answer_space"):
        if key in item:
            block[key] = copy.deepcopy(item[key])
    # official_solution_latex 已废弃：clue 和 solution_steps 由 draft 阶段直接写好，
    # 晋升只搬运不覆盖。保留字段读取仅为向后兼容旧 authoring YAML。
    if item.get("official_solution_latex"):
        if item["question_type"] in {"problem", "short_answer"}:
            block.setdefault("solution_steps", copy.deepcopy(item["official_solution_latex"]))
        else:
            block.setdefault("clue", str(item["official_solution_latex"]))
    if item.get("solution_notes"):
        block["solution_notes"] = copy.deepcopy(item["solution_notes"])
    prompt_specs = item.get("prompt_crops", [])
    if prompt_specs:
        prompt_image = {
            "image_path": f"assets/{prompt_specs[0]['file']}",
            "width": prompt_specs[0].get("width", "58mm"),
            "variant": "prompt",
            "disclosure_policy": "clean",
        }
        if item.get("render_stem_as_image"):
            block["stem_image"] = prompt_image
        else:
            block["diagram_col"] = prompt_image
    block["source_solution_images"] = [
        {
            "image_path": f"assets/{spec['file']}",
            "width": spec.get("width", "0.96\\linewidth"),
            "variant": "source_solution",
            "disclosure_policy": "teacher_only",
            "label": spec.get("label", f"原解答 {index}"),
        }
        for index, spec in enumerate(item["solution_crops"], start=1)
    ]
    block["teaching"] = {
        "source_key": item["source_key"],
        "skill_tags": item["skill_tags"],
        "difficulty": item["difficulty"],
        "official_solution_policy": "verbatim_transcription_with_separate_notes",
    }
    return {
        "meta": {
            "title": f"{paper['title']} · 原题第 {item['question_number']} 题 · 教师版",
            "grade": paper["grade"],
            "subject": paper.get("subject", "数学"),
            "total_points": item["points"],
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {"source_record": "source.yaml"},
        },
        "render": {"template": "exam-zh-practice", "paper_size": "a4paper"},
        "sections": [
            {
                "id": "question",
                "title": item["section_title"],
                "type": "practice",
                "visibility": "both",
                "blocks": [block],
            }
        ],
    }


def student_assignment(teacher: dict[str, Any]) -> dict[str, Any]:
    student = strip_teacher_fields(copy.deepcopy(teacher))
    student["meta"]["version"] = "student"
    student["meta"]["show_answers"] = False
    student["meta"]["title"] = student["meta"]["title"].replace("教师版", "学生版")
    for section in student["sections"]:
        section["visibility"] = "student"
    return student


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def build_item(item: dict[str, Any], paper: dict[str, Any], out_root: Path) -> None:
    item_dir = out_root / "items" / item["id"]
    crops = {
        "question_evidence": [crop_asset(spec, item_dir) for spec in item["question_crops"]],
        "prompt": [crop_asset(spec, item_dir) for spec in item.get("prompt_crops", [])],
        "official_solution": [crop_asset(spec, item_dir) for spec in item["solution_crops"]],
    }
    teacher = assignment(item, paper)
    student = student_assignment(teacher)
    source = {
        "schema": "math_exam_item_source/v1",
        "item_id": item["id"],
        "source_key": item["source_key"],
        "paper_id": paper["id"],
        "question_number": item["question_number"],
        "question_type": item["question_type"],
        "points": item["points"],
        "section_title": item["section_title"],
        "source_directory": paper["source_directory"],
        "crops": crops,
        "transcription": {
            "question_status": "author_pass",
            "official_solution_status": "author_pass",
            "independent_review": "pending",
            "human_review": "pending",
        },
        "content_hash": canonical_hash(
            {
                "teacher": teacher,
                "student": student,
                "crop_hashes": {
                    role: [entry["output_sha256"] for entry in entries]
                    for role, entries in crops.items()
                },
            }
        ),
    }
    write_yaml(item_dir / "source.yaml", source)
    write_yaml(item_dir / "teacher.resolved.assignment.yaml", teacher)
    write_yaml(item_dir / "student.resolved.assignment.yaml", student)
    print(f"{item['id']}: {item['source_key']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("authoring", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--only", nargs="*", default=[])
    args = parser.parse_args()
    payload = yaml.safe_load(args.authoring.read_text(encoding="utf-8"))
    wanted = set(args.only)
    for item in payload["items"]:
        if wanted and item["id"] not in wanted:
            continue
        build_item(item, payload["paper"], args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
