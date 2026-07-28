#!/usr/bin/env python3
"""Set up the staging question bank for 26一模相似三角形证明题.

Copies 13 items from their original TERM papers into a new topic staging,
normalizes images -> diagram_col, recomputes content_hash, and writes
paper.yaml + source.yaml for each item.
"""

import hashlib
import shutil
from pathlib import Path
import yaml

REPO_ROOT = Path("/Users/gaochong/develop/teaching_skills")
SOURCE_BANK = REPO_ROOT / "artifacts/题库/2026-07-24-上海初三试卷原题库"
STAGING_DIR = REPO_ROOT / "artifacts/题库/2026-07-27-26一模相似三角形证明题"
STAGING_PAPER = STAGING_DIR / "staging" / "2026-一模相似三角形证明题"

# Mapping: new_id -> (paper_id, original_item_id, source_key_suffix)
ITEMS = [
    ("Q001", "2026-BAOSHAN-TERM",   "Q023", "宝山23"),
    ("Q002", "2026-CHONGMING-TERM", "Q023", "崇明23"),
    ("Q003", "2026-FENGXIAN-TERM",  "Q023", "奉贤23"),
    ("Q004", "2026-HONGKOU-TERM",   "Q023", "虹口23"),
    ("Q005", "2026-JIADING-TERM",   "Q023", "嘉定23"),
    ("Q006", "2026-JINSHAN-TERM",   "Q022", "金山22"),
    ("Q007", "2026-JINSHAN-TERM",   "Q023", "金山23"),
    ("Q008", "2026-MINHANG-TERM",   "Q022", "闵行22"),
    ("Q009", "2026-PUTUO-TERM",     "Q023", "普陀23"),
    ("Q010", "2026-QINGPU-TERM",    "Q023", "青浦23"),
    ("Q011", "2026-SONGJIANG-TERM", "Q023", "松江23"),
    ("Q012", "2026-XUHUI-TERM",     "Q023", "徐汇23"),
    ("Q013", "2026-YANGPU-TERM",    "Q023", "杨浦23"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_content(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def normalize_images_to_diagram_col(assignment: dict) -> dict:
    """Convert images[] with variant=source_prompt to diagram_col."""
    for section in assignment.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") != "problem":
                continue
            images = block.get("images", [])
            if not images:
                continue
            # Find the prompt image (source_prompt variant)
            prompt_img = None
            for img in images:
                if img.get("variant") == "source_prompt":
                    prompt_img = img
                    break
            if prompt_img:
                # Remove images field, add diagram_col
                del block["images"]
                block["diagram_col"] = {
                    "image_path": prompt_img["image_path"],
                    "width": prompt_img.get("width", "0.75\\linewidth"),
                    "variant": "prompt",
                    "disclosure_policy": "clean",
                }
    return assignment


def generate_content_hash(source_yaml: dict, teacher_yaml: dict) -> str:
    """Compute content_hash from source + teacher assignment content."""
    # Combine key fields for hashing
    parts = []
    for crop_group in source_yaml.get("crops", {}).values():
        if isinstance(crop_group, list):
            for crop in crop_group:
                if isinstance(crop, dict):
                    parts.append(crop.get("output", ""))
                    parts.append(crop.get("output_sha256", ""))
    # Add stem_latex from teacher assignment
    for section in teacher_yaml.get("sections", []):
        for block in section.get("blocks", []):
            if block.get("type") == "problem":
                parts.append(block.get("stem_latex", ""))
    return sha256_content("|".join(parts))


def main():
    # Ensure staging directories exist
    items_dir = STAGING_PAPER / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    paper_entries = []

    for new_id, paper_id, orig_item_id, label in ITEMS:
        orig_item_dir = SOURCE_BANK / "staging" / paper_id / "items" / orig_item_id
        new_item_dir = items_dir / new_id
        new_item_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = new_item_dir / "assets"
        assets_dir.mkdir(exist_ok=True)

        # Read original source.yaml
        orig_source_path = orig_item_dir / "source.yaml"
        if not orig_source_path.exists():
            print(f"WARNING: {orig_source_path} not found, skipping {new_id}")
            continue
        orig_source = yaml.safe_load(orig_source_path.read_text())

        # Read original teacher resolved assignment
        orig_teacher_path = orig_item_dir / "teacher.resolved.assignment.yaml"
        orig_teacher = yaml.safe_load(orig_teacher_path.read_text()) if orig_teacher_path.exists() else None

        # Read original student resolved assignment
        orig_student_path = orig_item_dir / "student.resolved.assignment.yaml"
        orig_student = yaml.safe_load(orig_student_path.read_text()) if orig_student_path.exists() else None

        # Copy assets
        orig_assets = orig_item_dir / "assets"
        if orig_assets.exists():
            for asset_file in orig_assets.iterdir():
                if asset_file.is_file():
                    dest = assets_dir / asset_file.name
                    if not dest.exists():
                        shutil.copy2(asset_file, dest)

        # Normalize teacher assignment
        if orig_teacher:
            teacher = normalize_images_to_diagram_col(orig_teacher)
            # Update meta
            teacher["meta"]["title"] = f"26一模相似三角形证明题 {label}"
            # Write teacher assignment
            teacher_path = new_item_dir / "teacher.resolved.assignment.yaml"
            teacher_path.write_text(yaml.dump(teacher, allow_unicode=True, default_flow_style=False, sort_keys=False))

        # Normalize student assignment
        if orig_student:
            student = normalize_images_to_diagram_col(orig_student)
            student["meta"]["title"] = f"26一模相似三角形证明题 {label}"
            # Remove any answer/solution fields
            for section in student.get("sections", []):
                for block in section.get("blocks", []):
                    block.pop("answer", None)
                    block.pop("solution_steps", None)
                    block.pop("source_solution_images", None)
            student_path = new_item_dir / "student.resolved.assignment.yaml"
            student_path.write_text(yaml.dump(student, allow_unicode=True, default_flow_style=False, sort_keys=False))

        # Create new source.yaml with recomputed content_hash
        # Update crops output paths to use assets/ prefix consistently
        new_source = dict(orig_source)
        new_source["item_id"] = new_id
        new_source["source_key"] = f"2026-一模相似三角形证明题-{new_id}"
        new_source["paper_id"] = "2026-一模相似三角形证明题"
        new_source["question_number"] = int(new_id[1:])
        new_source["source_directory"] = orig_source.get("source_directory", "")

        # Recompute content_hash
        if orig_teacher:
            new_source["content_hash"] = generate_content_hash(new_source, orig_teacher)
        else:
            new_source["content_hash"] = sha256_content(new_id)

        # Reset transcription state for fresh review
        new_source["transcription"] = {
            "question_status": "author_pass",
            "official_solution_status": "author_pass",
            "independent_review": "pending",
            "human_review": "pending",
        }

        source_path = new_item_dir / "source.yaml"
        source_path.write_text(yaml.dump(new_source, allow_unicode=True, default_flow_style=False, sort_keys=False))

        paper_entries.append({
            "item_id": new_id,
            "question_number": int(new_id[1:]),
            "label": label,
            "source_key": new_source["source_key"],
        })
        print(f"  {new_id} ({label}): copied from {paper_id}/{orig_item_id}")

    # Write paper.yaml
    paper_yaml = {
        "schema": "math_exam_paper/v1",
        "paper": {
            "id": "2026-一模相似三角形证明题",
            "title": "26一模相似三角形证明题专题",
            "grade": "九年级",
            "subject": "数学",
            "source_archive": "artifacts/题库/2026-07-24-上海初三试卷原题库/staging",
        },
        "question_bank": "../../question-bank.yaml",
        "sections": [
            {
                "id": "topic",
                "title": "相似三角形证明题",
                "item_ids": [e["item_id"] for e in paper_entries],
            }
        ],
    }
    paper_path = STAGING_PAPER / "paper.yaml"
    paper_path.write_text(yaml.dump(paper_yaml, allow_unicode=True, default_flow_style=False, sort_keys=False))
    print(f"\nWrote paper.yaml with {len(paper_entries)} items")
    print(f"Staging dir: {STAGING_PAPER}")


if __name__ == "__main__":
    main()
