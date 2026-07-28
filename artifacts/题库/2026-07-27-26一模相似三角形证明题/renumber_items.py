#!/usr/bin/env python3
"""Renumber staging items after removing Q004, Q006, Q007."""

import shutil
import yaml
from pathlib import Path

STAGING = Path("/Users/gaochong/develop/teaching_skills/artifacts/题库/2026-07-27-26一模相似三角形证明题/staging/2026-一模相似三角形证明题")
ITEMS_DIR = STAGING / "items"

# Mapping: old_id -> new_id
RENUMBER = {
    "Q001": "Q001",
    "Q002": "Q002",
    "Q003": "Q003",
    "Q005": "Q004",
    "Q008": "Q005",
    "Q009": "Q006",
    "Q010": "Q007",
    "Q011": "Q008",
    "Q012": "Q009",
    "Q013": "Q010",
}

# New labels for each item
LABELS = {
    "Q001": "宝山23",
    "Q002": "崇明23",
    "Q003": "奉贤23",
    "Q004": "嘉定23",
    "Q005": "闵行22",
    "Q006": "普陀23",
    "Q007": "青浦23",
    "Q008": "松江23",
    "Q009": "徐汇23",
    "Q010": "杨浦23",
}


def main():
    # First, rename directories to temp names to avoid conflicts
    temp_dir = ITEMS_DIR / "_temp"
    temp_dir.mkdir(exist_ok=True)

    for old_id, new_id in RENUMBER.items():
        src = ITEMS_DIR / old_id
        if src.exists():
            shutil.move(str(src), str(temp_dir / old_id))

    # Now rename from temp to final
    for old_id, new_id in RENUMBER.items():
        src = temp_dir / old_id
        if not src.exists():
            continue
        dst = ITEMS_DIR / new_id
        shutil.move(str(src), str(dst))

        # Update source.yaml
        source_path = dst / "source.yaml"
        if source_path.exists():
            source = yaml.safe_load(source_path.read_text())
            old_key = source.get("source_key", "")
            source["item_id"] = new_id
            source["source_key"] = f"2026-一模相似三角形证明题-{new_id}"
            source["question_number"] = int(new_id[1:])
            source_path.write_text(yaml.dump(source, allow_unicode=True, default_flow_style=False, sort_keys=False))

        # Update teacher assignment
        teacher_path = dst / "teacher.resolved.assignment.yaml"
        if teacher_path.exists():
            teacher = yaml.safe_load(teacher_path.read_text())
            teacher["meta"]["title"] = f"26一模相似三角形证明题 {LABELS[new_id]}"
            for section in teacher.get("sections", []):
                for block in section.get("blocks", []):
                    if block.get("type") == "problem":
                        block["id"] = new_id
            teacher_path.write_text(yaml.dump(teacher, allow_unicode=True, default_flow_style=False, sort_keys=False))

        # Update student assignment
        student_path = dst / "student.resolved.assignment.yaml"
        if student_path.exists():
            student = yaml.safe_load(student_path.read_text())
            student["meta"]["title"] = f"26一模相似三角形证明题 {LABELS[new_id]}"
            for section in student.get("sections", []):
                for block in section.get("blocks", []):
                    if block.get("type") == "problem":
                        block["id"] = new_id
            student_path.write_text(yaml.dump(student, allow_unicode=True, default_flow_style=False, sort_keys=False))

        print(f"  {old_id} -> {new_id} ({LABELS[new_id]})")

    # Clean up temp dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    # Update paper.yaml
    paper_path = STAGING / "paper.yaml"
    paper = yaml.safe_load(paper_path.read_text())
    paper["sections"][0]["item_ids"] = [f"Q{i:03d}" for i in range(1, 11)]
    paper_path.write_text(yaml.dump(paper, allow_unicode=True, default_flow_style=False, sort_keys=False))
    print(f"\nUpdated paper.yaml with 10 items")


if __name__ == "__main__":
    main()
