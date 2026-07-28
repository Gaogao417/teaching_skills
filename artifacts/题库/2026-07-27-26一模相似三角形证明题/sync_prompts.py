#!/usr/bin/env python3
"""Sync modified prompt images from 26一模相似三角形证明题 back to original staging."""

import shutil
import yaml
from pathlib import Path

BASE = Path("/Users/gaochong/develop/teaching_skills")
SRC_STAGING = BASE / "artifacts/题库/2026-07-27-26一模相似三角形证明题/staging/2026-一模相似三角形证明题/items"
ORIG_STAGING = BASE / "artifacts/题库/2026-07-24-上海初三试卷原题库/staging"

# Mapping: new_id -> (original_paper_id, original_item_id, label)
MAPPING = {
    "Q001": ("2026-BAOSHAN-TERM",   "Q023", "宝山23"),
    "Q002": ("2026-CHONGMING-TERM", "Q023", "崇明23"),
    "Q003": ("2026-FENGXIAN-TERM",  "Q023", "奉贤23"),
    "Q004": ("2026-JIADING-TERM",   "Q023", "嘉定23"),
    "Q005": ("2026-MINHANG-TERM",   "Q022", "闵行22"),
    "Q006": ("2026-PUTUO-TERM",     "Q023", "普陀23"),
    "Q007": ("2026-QINGPU-TERM",    "Q023", "青浦23"),
    "Q008": ("2026-SONGJIANG-TERM", "Q023", "松江23"),
    "Q009": ("2026-XUHUI-TERM",     "Q023", "徐汇23"),
    "Q010": ("2026-YANGPU-TERM",    "Q023", "杨浦23"),
}


def main():
    synced = []
    for new_id, (paper_id, orig_item_id, label) in MAPPING.items():
        src_assets = SRC_STAGING / new_id / "assets"
        dst_assets = ORIG_STAGING / paper_id / "items" / orig_item_id / "assets"

        # Find manual-prompt images
        manual_prompts = list(src_assets.glob("manual-prompt-*.png"))
        if not manual_prompts:
            continue

        for manual_img in manual_prompts:
            # Copy to original staging
            dst = dst_assets / manual_img.name
            if not dst.exists() or dst.read_bytes() != manual_img.read_bytes():
                shutil.copy2(manual_img, dst)
                print(f"  {new_id} ({label}): synced {manual_img.name} -> {paper_id}/{orig_item_id}")

            # Update diagram_col in original teacher assignment
            orig_teacher = ORIG_STAGING / paper_id / "items" / orig_item_id / "teacher.resolved.assignment.yaml"
            if orig_teacher.exists():
                teacher = yaml.safe_load(orig_teacher.read_text())
                for section in teacher.get("sections", []):
                    for block in section.get("blocks", []):
                        if block.get("type") == "problem":
                            diagram = block.get("diagram_col", {})
                            if diagram.get("variant") == "prompt":
                                old_path = diagram.get("image_path", "")
                                new_path = f"assets/{manual_img.name}"
                                if old_path != new_path:
                                    diagram["image_path"] = new_path
                                    orig_teacher.write_text(yaml.dump(teacher, allow_unicode=True, default_flow_style=False, sort_keys=False))
                                    print(f"    Updated diagram_col: {old_path} -> {new_path}")

            # Update diagram_col in original student assignment
            orig_student = ORIG_STAGING / paper_id / "items" / orig_item_id / "student.resolved.assignment.yaml"
            if orig_student.exists():
                student = yaml.safe_load(orig_student.read_text())
                for section in student.get("sections", []):
                    for block in section.get("blocks", []):
                        if block.get("type") == "problem":
                            diagram = block.get("diagram_col", {})
                            if diagram.get("variant") == "prompt":
                                old_path = diagram.get("image_path", "")
                                new_path = f"assets/{manual_img.name}"
                                if old_path != new_path:
                                    diagram["image_path"] = new_path
                                    orig_student.write_text(yaml.dump(student, allow_unicode=True, default_flow_style=False, sort_keys=False))
                                    print(f"    Updated student diagram_col: {old_path} -> {new_path}")

            synced.append(f"{new_id} ({label})")

    print(f"\nSynced {len(synced)} items: {', '.join(synced)}")


if __name__ == "__main__":
    main()
