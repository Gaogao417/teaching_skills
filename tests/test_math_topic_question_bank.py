from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPTS = REPO_ROOT / ".codex/skills/math-topic-question-bank/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from derive_student_assignment import derive  # noqa: E402
from question_bank_review_server import QuestionBankCatalog  # noqa: E402
from validate_question_bank import stem_quality_errors, validate_manifest  # noqa: E402


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def teacher_assignment(item_id: str, item_dir: Path) -> dict:
    diagram_dir = item_dir / "diagram"
    diagram_dir.mkdir(parents=True, exist_ok=True)
    (diagram_dir / "prompt.fragment.tex").write_text("% prompt\n", encoding="utf-8")
    (diagram_dir / "solution.fragment.tex").write_text("% solution\n", encoding="utf-8")
    return {
        "meta": {
            "title": f"{item_id} · 教师版",
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {"explanation": "source-explanation.yaml"},
        },
        "render": {"template": "exam-zh-practice"},
        "sections": [
            {
                "id": "question",
                "title": "练习",
                "type": "practice",
                "visibility": "both",
                "blocks": [
                    {
                        "type": "problem",
                        "id": item_id,
                        "stem": "已知 $x+1=3$，求 $x$。",
                        "points": 5,
                        "answer": "$x=2$",
                        "solution_steps": [{"title": "移项", "content": "$x=2$。"}],
                        "teaching": {"teaching_goal": "解方程"},
                        "diagram_col": {
                            "kind": "tikz",
                            "tikz_path": "diagram/prompt.fragment.tex",
                            "variant": "prompt",
                            "disclosure_policy": "clean",
                        },
                    }
                ],
            },
            {
                "id": "solution-figure",
                "title": "解答图",
                "type": "answer_key",
                "visibility": "teacher",
                "blocks": [
                    {
                        "type": "diagram",
                        "id": f"{item_id}-solution",
                        "kind": "tikz",
                        "tikz_path": "diagram/solution.fragment.tex",
                        "variant": "solution",
                        "disclosure_policy": "annotated",
                    }
                ],
            },
        ],
    }


def build_bank(tmp_path: Path, count: int = 2) -> Path:
    items = []
    for index in range(1, count + 1):
        item_id = f"Q{index:03d}"
        item_dir = tmp_path / "items" / item_id
        teacher = teacher_assignment(item_id, item_dir)
        student = derive(teacher)
        teacher_path = item_dir / "teacher.resolved.assignment.yaml"
        student_path = item_dir / "student.resolved.assignment.yaml"
        write_yaml(teacher_path, teacher)
        write_yaml(student_path, student)
        items.append(
            {
                "id": item_id,
                "title": f"样题 {index}",
                "question_type": "problem",
                "difficulty": "foundation" if index == 1 else "standard",
                "skill_tags": ["解方程"],
                "variation_dimension": "changed_numbers",
                "diagram_requirement": "prompt_and_solution",
                "student_assignment": str(student_path.relative_to(tmp_path)),
                "teacher_assignment": str(teacher_path.relative_to(tmp_path)),
            }
        )
    manifest = {
        "schema": "math_topic_question_bank/v1",
        "bank": {
            "id": "equation-demo",
            "topic": "方程样例",
            "grade": "七年级",
            "subject": "数学",
            "source_explanation": "source-explanation.yaml",
            "status": "ready",
            "target_count": count,
        },
        "items": items,
    }
    path = tmp_path / "question-bank.yaml"
    write_yaml(path, manifest)
    return path


def test_ready_bank_and_student_derivation(tmp_path: Path) -> None:
    manifest = build_bank(tmp_path)
    bank, errors = validate_manifest(manifest)
    assert bank is not None
    assert errors == []
    student = yaml.safe_load(
        (tmp_path / "items/Q001/student.resolved.assignment.yaml").read_text(encoding="utf-8")
    )
    rendered = yaml.safe_dump(student, allow_unicode=True)
    assert "solution_steps" not in rendered
    assert "teaching:" not in rendered
    assert "variant: solution" not in rendered
    assert "variant: prompt" in rendered


def test_student_derivation_removes_nested_solution_diagram(tmp_path: Path) -> None:
    teacher = teacher_assignment("Q001", tmp_path / "items/Q001")
    block = teacher["sections"][0]["blocks"][0]
    block["answer_space"] = {
        "type": "steps",
        "diagram_col": {
            "kind": "tikz",
            "tikz_path": "diagram/solution.fragment.tex",
            "variant": "solution",
            "disclosure_policy": "annotated",
        },
    }

    student = derive(teacher)
    student_block = student["sections"][0]["blocks"][0]
    assert "diagram_col" not in student_block["answer_space"]
    assert student_block["diagram_col"]["variant"] == "prompt"


def test_stem_quality_rejects_process_noise_and_repeated_geometry() -> None:
    assert stem_quality_errors("已知 $x+1=3$，求 $x$。") == []
    assert stem_quality_errors("完成三格填空：先写比例，再求答案。")
    assert stem_quality_errors("按照“提二次项系数—配方”的顺序完成本题。")
    assert stem_quality_errors("如图，点序为 $P-A-C$。")
    assert stem_quality_errors(r"如图，$D\in BC$，$P=AD\cap BE$。")


def test_ready_bank_rejects_student_hints_and_prompt_caption(tmp_path: Path) -> None:
    manifest = build_bank(tmp_path)
    student_path = tmp_path / "items/Q001/student.resolved.assignment.yaml"
    student = yaml.safe_load(student_path.read_text(encoding="utf-8"))
    block = student["sections"][0]["blocks"][0]
    block["hints"] = [{"content": "先移项。"}]
    block["diagram_col"]["caption"] = "先看等量关系。"
    write_yaml(student_path, student)
    _, errors = validate_manifest(manifest)
    assert any("must not contain hints" in error for error in errors)
    assert any("must not carry a student-facing caption" in error for error in errors)

def test_seeded_sampling_outputs_valid_assignments(tmp_path: Path) -> None:
    manifest = build_bank(tmp_path)
    output_dir = tmp_path / "sample"
    command = [
        sys.executable,
        str(SKILL_SCRIPTS / "sample_question_bank.py"),
        str(manifest),
        "--count",
        "2",
        "--seed",
        "7",
        "--output-dir",
        str(output_dir),
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    assert "seed=7" in result.stdout

    for version in ("student", "teacher"):
        assignment = output_dir / f"sample.{version}.assignment.yaml"
        validate = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / ".codex/skills/math-assignment-latex/scripts/validate_assignment.py"),
                str(assignment),
            ],
            text=True,
            capture_output=True,
        )
        assert validate.returncode == 0, validate.stdout + validate.stderr
    teacher_text = (output_dir / "sample.teacher.assignment.yaml").read_text(encoding="utf-8")
    assert "variant: solution" in teacher_text


def test_sampling_defensively_removes_student_solution_diagrams(tmp_path: Path) -> None:
    manifest = build_bank(tmp_path, count=1)
    student_path = tmp_path / "items/Q001/student.resolved.assignment.yaml"
    student = yaml.safe_load(student_path.read_text(encoding="utf-8"))
    block = student["sections"][0]["blocks"][0]
    block["answer_space"] = {
        "type": "steps",
        "height": "20mm",
        "diagram_col": {
            "kind": "tikz",
            "tikz_path": "diagram/solution.fragment.tex",
            "variant": "solution",
            "disclosure_policy": "annotated",
        },
    }
    block["answer"] = "$x=2$"
    write_yaml(student_path, student)

    output_dir = tmp_path / "sample"
    subprocess.run(
        [
            sys.executable,
            str(SKILL_SCRIPTS / "sample_question_bank.py"),
            str(manifest),
            "--count",
            "1",
            "--seed",
            "11",
            "--output-dir",
            str(output_dir),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    sampled = yaml.safe_load(
        (output_dir / "sample.student.assignment.yaml").read_text(encoding="utf-8")
    )
    sampled_block = sampled["sections"][0]["blocks"][0]
    assert "answer" not in sampled_block
    assert "diagram_col" not in sampled_block["answer_space"]


def test_review_catalog_exposes_solution_step_previews(tmp_path: Path) -> None:
    bank_dir = tmp_path / "bank"
    build_bank(bank_dir, count=1)
    teacher_path = bank_dir / "items/Q001/teacher.resolved.assignment.yaml"
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    block = teacher["sections"][0]["blocks"][0]
    diagram_dir = teacher_path.parent / "diagram"
    (diagram_dir / "step.fragment.tex").write_text("% step\n", encoding="utf-8")
    (diagram_dir / "step.preview.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (diagram_dir / "solution.preview.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    block["solution_steps"][0]["diagram_col"] = {
        "kind": "tikz",
        "tikz_path": "diagram/step.fragment.tex",
        "variant": "solution",
        "disclosure_policy": "annotated",
    }
    write_yaml(teacher_path, teacher)

    catalog = QuestionBankCatalog(tmp_path)
    detail, files = catalog.detail("equation-demo")
    item = detail["items"][0]

    assert [preview["title"] for preview in item["solution_previews"]] == ["移项", "解答图"]
    assert "/solution-step-0?v=" in item["solution_steps"][0]["preview_url"]
    assert files[("Q001", "solution-step-0")].name == "step.preview.svg"
    assert files[("Q001", "solution-extra-0")].name == "solution.preview.svg"
