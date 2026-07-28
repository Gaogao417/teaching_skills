#!/usr/bin/env python3
"""Update staging items: fix block ids and add proper solution text."""

import yaml
from pathlib import Path

STAGING = Path("/Users/gaochong/develop/teaching_skills/artifacts/题库/2026-07-27-26一模相似三角形证明题/staging/2026-一模相似三角形证明题/items")

# Solution text for items that need it (based on official solutions)
SOLUTIONS = {
    "Q001": {  # 宝山23
        "answer": "（1）见证明；（2）$BE\\perp CD$。",
        "solution_steps": [
            {
                "title": "第（1）问",
                "content": (
                    "四边形 $ABCD$ 是菱形，$\\therefore AB\\parallel CD$，$AG\\parallel BC$。\n"
                    "$\\therefore \\dfrac{BE}{EF}=\\dfrac{AC}{CF}$，$\\dfrac{BG}{BF}=\\dfrac{AC}{CF}$。\n"
                    "$\\therefore \\dfrac{BE}{EF}=\\dfrac{BG}{BF}$，即 $BE\\cdot BF=BG\\cdot EF$。"
                ),
            },
            {
                "title": "第（2）问",
                "content": (
                    "$E$ 是 $CD$ 的中点，$\\therefore CE=\\dfrac{1}{2}CD=\\dfrac{1}{2}AB$。\n"
                    "$AB\\parallel CD$，$\\therefore \\dfrac{CE}{AB}=\\dfrac{CF}{AF}=\\dfrac{EF}{BF}=\\dfrac{1}{2}$，即 $CF=\\dfrac{1}{2}AF$。\n"
                    "$AF\\cdot CF=2BF^2$，$\\therefore CF^2=BF^2$，$\\therefore CF=BF$。\n"
                    "$\\therefore \\angle FBC=\\angle FCB=\\angle FCE$。\n"
                    "$\\angle CEF=\\angle BEC$，$\\therefore \\triangle ECF\\sim\\triangle EBC$。\n"
                    "$\\therefore \\dfrac{EF}{CE}=\\dfrac{CE}{BE}$，即 $CE^2=EF\\cdot BE$。\n"
                    "设 $EF=a$，则 $BF=CF=2a$，$BE=3a$，$\\therefore CE^2=3a^2$。\n"
                    "$\\therefore CE^2+EF^2=CF^2$，$\\therefore \\angle CEF=90^\\circ$，即 $BE\\perp CD$。"
                ),
            },
        ],
    },
    "Q003": {  # 奉贤23
        "answer": "两结论均成立。",
        "solution_steps": [
            {
                "title": "第（1）问",
                "content": (
                    "$CD=BD$，$\\therefore \\angle B=\\angle DCB$。\n"
                    "$AE=AC$，$\\therefore \\angle AEC=\\angle ACB$。\n"
                    "$\\angle AEC=\\angle B+\\angle BAE$，$\\angle ACB=\\angle DCB+\\angle ACD$。\n"
                    "$\\therefore \\angle BAE=\\angle ACD$。\n"
                    "$\\because \\angle ADF=\\angle CDA$，$\\therefore \\triangle ADF\\sim\\triangle CDA$。"
                ),
            },
            {
                "title": "第（2）问",
                "content": (
                    "$\\because \\dfrac{AD}{AB}=\\dfrac{CE}{CB}$，$\\therefore DE\\parallel AC$，$\\therefore \\angle BDE=\\angle DAC$。\n"
                    "$\\because \\triangle ADF\\sim\\triangle CDA$，$\\therefore \\angle DFA=\\angle DAC$，$\\dfrac{AD}{DC}=\\dfrac{AF}{AC}$。\n"
                    "$\\therefore \\angle BDE=\\angle DFA$，$\\therefore \\angle ADE=\\angle CFA$。\n"
                    "$\\because \\angle BAE=\\angle ACD$，$\\therefore \\triangle ADE\\sim\\triangle CFA$。\n"
                    "$\\therefore \\dfrac{DE}{AF}=\\dfrac{AE}{AC}$，$\\therefore \\dfrac{DE}{AE}=\\dfrac{AF}{AC}=\\dfrac{AD}{DC}$。\n"
                    "$\\therefore AD\\cdot AE=DC\\cdot DE$。"
                ),
            },
        ],
    },
    "Q008": {  # 闵行22
        "answer": "两结论均成立。",
        "solution_steps": [
            {
                "title": "第（1）问",
                "content": (
                    "在 $\\triangle BAE$ 与 $\\triangle DCE$ 中：$\\dfrac{AE}{CE}=\\dfrac{BE}{DE}$，$\\angle AEB=\\angle CED$。\n"
                    "$\\therefore \\triangle BAE\\sim\\triangle DCE$。\n"
                    "$\\therefore \\angle BAE=\\angle DCE=90^\\circ$，$\\angle ABE=\\angle CDF$。\n"
                    "点 $F$ 是 $\\triangle ECD$ 边 $DE$ 的中点，$\\therefore CF=EF=FD=\\dfrac{1}{2}ED$。\n"
                    "$\\therefore \\angle FCD=\\angle CDF$，$\\therefore \\angle ABE=\\angle FCD$。"
                ),
            },
            {
                "title": "第（2）问",
                "content": (
                    "$\\angle BED+\\angle FEC=180^\\circ$，$\\angle BCG+\\angle FCE=180^\\circ$。\n"
                    "又 $\\angle FCE=\\angle FEC$，$\\therefore \\angle BED=\\angle BCG$。\n"
                    "$DA$ 平分 $\\angle BDC$，$\\therefore \\angle CDF=\\angle EDB$。\n"
                    "$\\because \\angle ABE=\\angle CDF$，$\\therefore \\angle ABE=\\angle EDB$。\n"
                    "在 $\\triangle BCG$ 与 $\\triangle DEB$ 中：$\\angle BED=\\angle BCG$，$\\angle ABE=\\angle EDB$。\n"
                    "$\\therefore \\triangle BCG\\sim\\triangle DEB$，$\\therefore \\dfrac{BG}{BD}=\\dfrac{BC}{DE}$。\n"
                    "$\\because CF=\\dfrac{1}{2}ED$，$\\therefore DE=2CF$。\n"
                    "$\\therefore \\dfrac{BG}{BD}=\\dfrac{BC}{2CF}$。"
                ),
            },
        ],
    },
    "Q011": {  # 松江23
        "answer": "两结论均成立。",
        "solution_steps": [
            {
                "title": "第（1）问",
                "content": (
                    "$\\angle AED+\\angle DEC=\\angle B+\\angle BCE$，$\\angle DEC=\\angle B=90^\\circ$，$\\therefore \\angle AED=\\angle BCE$。\n"
                    "又 $CE$ 平分 $\\angle ACB$，$\\therefore \\angle ACE=\\angle BCE$，$\\therefore \\angle AED=\\angle ACE$。\n"
                    "$\\angle EAG=\\angle CAE$，$\\therefore \\triangle AEG\\sim\\triangle ACE$。\n"
                    "$\\therefore \\dfrac{AE}{AC}=\\dfrac{AG}{AE}$，即 $AE^2=AG\\cdot AC$。"
                ),
            },
            {
                "title": "第（2）问",
                "content": (
                    "$\\because \\triangle AEG\\sim\\triangle ACE$，$\\therefore \\dfrac{AG}{AE}=\\dfrac{EG}{EC}$，即 $\\dfrac{AG}{EG}=\\dfrac{AE}{EC}$。\n"
                    "$\\angle DAE=\\angle CEG=90^\\circ$，$\\angle AED=\\angle ECG$，$\\therefore \\triangle ADE\\sim\\triangle EGC$。\n"
                    "$\\therefore \\dfrac{DE}{CG}=\\dfrac{AE}{CE}$，$\\therefore \\dfrac{AG}{EG}=\\dfrac{DE}{CG}$，即 $AG\\cdot GC=EG\\cdot ED$。"
                ),
            },
        ],
    },
}


def main():
    for item_dir in sorted(STAGING.iterdir()):
        if not item_dir.is_dir():
            continue
        item_id = item_dir.name
        teacher_path = item_dir / "teacher.resolved.assignment.yaml"
        if not teacher_path.exists():
            print(f"  {item_id}: no teacher assignment, skipping")
            continue

        teacher = yaml.safe_load(teacher_path.read_text())

        # Fix block id
        for section in teacher.get("sections", []):
            for block in section.get("blocks", []):
                if block.get("type") == "problem":
                    block["id"] = item_id

        # Add solution text if available
        if item_id in SOLUTIONS:
            sol = SOLUTIONS[item_id]
            for section in teacher.get("sections", []):
                for block in section.get("blocks", []):
                    if block.get("type") == "problem":
                        block["answer"] = sol["answer"]
                        block["solution_steps"] = sol["solution_steps"]

        teacher_path.write_text(yaml.dump(teacher, allow_unicode=True, default_flow_style=False, sort_keys=False))

        # Also fix student assignment block id
        student_path = item_dir / "student.resolved.assignment.yaml"
        if student_path.exists():
            student = yaml.safe_load(student_path.read_text())
            for section in student.get("sections", []):
                for block in section.get("blocks", []):
                    if block.get("type") == "problem":
                        block["id"] = item_id
            student_path.write_text(yaml.dump(student, allow_unicode=True, default_flow_style=False, sort_keys=False))

        sol_status = "updated solution" if item_id in SOLUTIONS else "no solution update needed"
        print(f"  {item_id}: fixed id, {sol_status}")


if __name__ == "__main__":
    main()
