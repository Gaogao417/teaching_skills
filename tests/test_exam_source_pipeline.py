from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from PIL import Image
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
INGESTION_SCRIPTS = (
    ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
)
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(INGESTION_SCRIPTS))

from assemble_exam_paper import assemble  # noqa: E402
from derive_student_assignment import derive  # noqa: E402
from exam_source_contracts import (  # noqa: E402
    CropEvidence,
    ExamPaperManifest,
    TranscriptionState,
)
from promote_exam_source import promote  # noqa: E402
from question_bank_contracts import QuestionBank  # noqa: E402
from validate_exam_source import validate_source  # noqa: E402
from materialize_staging import materialize_crop  # noqa: E402

sys.path.insert(0, str(ROOT / "math-assignment-latex/scripts"))
from render_assignment import render  # noqa: E402
from validate_assignment import validate as validate_assignment  # noqa: E402


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_prompt_human_crop_marker_requires_a_note() -> None:
    base = {
        "question_status": "author_pass",
        "official_solution_status": "author_pass",
    }
    with pytest.raises(ValueError, match="prompt_review_notes"):
        TranscriptionState.model_validate(
            {**base, "prompt_status": "needs_human_crop"}
        )
    state = TranscriptionState.model_validate(
        {
            **base,
            "prompt_status": "needs_human_crop",
            "prompt_review_notes": ["右下水印需人工补裁。"],
        }
    )
    assert state.prompt_status == "needs_human_crop"


def source_fixture(tmp_path: Path, *, approved: bool = False) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    original = tmp_path / "original.png"
    crop = tmp_path / "item/assets/q001.png"
    Image.new("RGB", (100, 80), "white").save(original)
    crop.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(original) as image:
        image.crop((10, 20, 70, 60)).save(crop)
    status = {
        "question_status": "author_pass",
        "official_solution_status": "author_pass",
        "human_review": "approved" if approved else "pending",
    }
    record = {
        "schema": "math_exam_item_source/v1",
        "item_id": "Q001",
        "source_key": "paper-a:q1",
        "paper_id": "paper-a",
        "question_number": 1,
        "question_type": "choice",
        "points": 4,
        "section_title": "一、选择题",
        "source_directory": "documents/paper-a",
        "crops": {
            "question_evidence": [
                {
                    "source": "original.png",
                    "source_sha256": digest(original),
                    "box_px": [10, 20, 70, 60],
                    "output": "assets/q001.png",
                    "output_sha256": digest(crop),
                }
            ],
            "prompt": [],
            "official_solution": [
                {
                    "source": "original.png",
                    "source_sha256": digest(original),
                    "box_px": [10, 20, 70, 60],
                    "output": "assets/q001.png",
                    "output_sha256": digest(crop),
                }
            ],
        },
        "transcription": status,
        "content_hash": f"sha256:{'1' * 64}",
    }
    source = tmp_path / "item/source.yaml"
    write_yaml(source, record)
    return source


def review_fixture(tmp_path: Path, *, status: str = "approved", content_hash: str | None = None) -> Path:
    review = tmp_path / "item/review.yaml"
    write_yaml(
        review,
        {
            "schema": "math_exam_item_review/v1",
            "item_id": "Q001",
            "source_key": "paper-a:q1",
            "content_hash": content_hash or f"sha256:{'1' * 64}",
            "status": status,
            "reviewer": "reviewer-a",
            "reviewed_at": "2026-07-24T10:00:00+08:00",
            "notes": [],
        },
    )
    return review


def test_source_validation_checks_hashes_review_and_promotion(tmp_path: Path) -> None:
    source = source_fixture(tmp_path)
    review = review_fixture(tmp_path)
    record, errors = validate_source(source, review_path=review, repo_root=tmp_path)
    assert record is not None
    assert errors == []

    promoted = promote(source, review, repo_root=tmp_path)
    assert promoted["transcription"]["human_review"] == "approved"

    Image.new("RGB", (60, 40), "black").save(tmp_path / "item/assets/q001.png")
    _, errors = validate_source(source, repo_root=tmp_path)
    assert any("output_sha256 mismatch" in error for error in errors)


def test_crop_whiteout_must_stay_inside_crop() -> None:
    payload = {
        "source": "original.png",
        "source_sha256": f"sha256:{'1' * 64}",
        "box_px": [10, 20, 70, 60],
        "whiteout_px": [[0, 0, 61, 10]],
        "output": "assets/q001.png",
        "output_sha256": f"sha256:{'2' * 64}",
    }
    with pytest.raises(ValueError, match="whiteout_px"):
        CropEvidence.model_validate(payload)


def test_source_validation_checks_solution_crop_and_whiteout_pixels(
    tmp_path: Path,
) -> None:
    source = source_fixture(tmp_path)
    original = tmp_path / "solution-original.png"
    output = tmp_path / "item/assets/solution.png"
    Image.new("RGB", (40, 30), "black").save(original)
    with Image.open(original) as image:
        cropped = image.crop((5, 5, 35, 25))
    cropped.paste("white", (0, 0, 8, 6))
    cropped.save(output)

    record = yaml.safe_load(source.read_text(encoding="utf-8"))
    record["crops"]["solution"] = [
        {
            "source": "solution-original.png",
            "source_sha256": digest(original),
            "box_px": [5, 5, 35, 25],
            "whiteout_px": [[0, 0, 8, 6]],
            "output": "assets/solution.png",
            "output_sha256": digest(output),
        }
    ]
    write_yaml(source, record)
    _, errors = validate_source(source, repo_root=tmp_path)
    assert errors == []

    with Image.open(original) as image:
        image.crop((5, 5, 35, 25)).save(output)
    record["crops"]["solution"][0]["output_sha256"] = digest(output)
    write_yaml(source, record)
    _, errors = validate_source(source, repo_root=tmp_path)
    assert any(
        "solution[0]: output pixels do not match box_px crop" in error
        for error in errors
    )


def test_transparent_crop_is_composited_on_white_and_validated(
    tmp_path: Path,
) -> None:
    source = source_fixture(tmp_path)
    original = tmp_path / "transparent.png"
    output = tmp_path / "item/assets/transparent.png"
    transparent = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    transparent.putpixel((1, 1), (0, 0, 0, 255))
    transparent.save(original)
    crop = {
        "source": "transparent.png",
        "source_sha256": digest(original),
        "box_px": [0, 0, 4, 4],
        "whiteout_px": [],
        "output": "assets/transparent.png",
        "output_sha256": f"sha256:{'0' * 64}",
    }

    materialize_crop(
        crop,
        item_dir=tmp_path / "item",
        repo_root=tmp_path,
        label="Q001 prompt[0]",
    )
    with Image.open(output) as rendered:
        assert rendered.mode == "RGB"
        assert rendered.getpixel((0, 0)) == (255, 255, 255)
        assert rendered.getpixel((1, 1)) == (0, 0, 0)

    record = yaml.safe_load(source.read_text(encoding="utf-8"))
    record["crops"]["prompt"] = [crop]
    write_yaml(source, record)
    _, errors = validate_source(source, repo_root=tmp_path)
    assert errors == []

    Image.new("RGB", (4, 4), "black").save(output)
    record["crops"]["prompt"][0]["output_sha256"] = digest(output)
    write_yaml(source, record)
    _, errors = validate_source(source, repo_root=tmp_path)
    assert any(
        "prompt[0]: output pixels do not match box_px crop" in error
        for error in errors
    )


def test_promotion_rejects_nonapproved_or_stale_review(tmp_path: Path) -> None:
    source = source_fixture(tmp_path)
    pending = review_fixture(tmp_path, status="pending")
    with pytest.raises(ValueError, match="must be approved"):
        promote(source, pending, repo_root=tmp_path)
    stale = review_fixture(tmp_path, content_hash=f"sha256:{'2' * 64}")
    with pytest.raises(ValueError, match="content_hash"):
        promote(source, stale, repo_root=tmp_path)


def teacher_assignment(image_path: str) -> dict:
    return {
        "meta": {
            "title": "原题第 1 题 · 教师版",
            "version": "teacher",
            "show_answers": True,
        },
        "render": {"template": "exam-zh-practice"},
        "sections": [
            {
                "id": "question",
                "title": "一、选择题",
                "type": "practice",
                "visibility": "both",
                "blocks": [
                    {
                        "type": "choice",
                        "id": "Q001",
                        "points": 4,
                        "stem_latex": "若 $x=1$，则 $x+1=$（\\quad）。",
                        "choices": {"A": "1", "B": "2", "C": "3", "D": "4"},
                        "answer": "B",
                        "explanation": "代入得 $x+1=2$。",
                        "solution_notes": ["严谨补充：这里直接代入。"],
                        "source_solution_images": [
                            {
                                "image_path": image_path,
                                "width": "0.96\\linewidth",
                                "variant": "source_solution",
                                "disclosure_policy": "teacher_only",
                                "label": "原解答",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def paper_fixture(tmp_path: Path) -> Path:
    bank_dir = tmp_path / "bank"
    source = source_fixture(bank_dir, approved=True)
    teacher = teacher_assignment("assets/q001.png")
    student = derive(teacher)
    write_yaml(bank_dir / "item/teacher.resolved.assignment.yaml", teacher)
    write_yaml(bank_dir / "item/student.resolved.assignment.yaml", student)
    write_yaml(
        bank_dir / "question-bank.yaml",
        {
            "schema": "math_topic_question_bank/v1",
            "bank": {
                "id": "paper-a-bank",
                "topic": "归档试卷",
                "grade": "九年级",
                "subject": "数学",
                "source_archive": "documents/paper-a",
                "status": "ready",
                "target_count": 1,
            },
            "items": [
                {
                    "id": "Q001",
                    "title": "第 1 题",
                    "question_type": "choice",
                    "difficulty": "foundation",
                    "skill_tags": ["代入"],
                    "variation_dimension": "source_exam",
                    "diagram_requirement": "none",
                    "student_assignment": "item/student.resolved.assignment.yaml",
                    "teacher_assignment": "item/teacher.resolved.assignment.yaml",
                    "source_ref": str(source.relative_to(bank_dir)),
                }
            ],
        },
    )
    manifest = tmp_path / "paper.yaml"
    write_yaml(
        manifest,
        {
            "schema": "math_exam_paper/v1",
            "paper": {
                "id": "paper-a",
                "title": "A 区九年级数学",
                "grade": "九年级",
                "subject": "数学",
                "duration": "100分钟",
            },
            "question_bank": "bank/question-bank.yaml",
            "sections": [{"id": "choice", "title": "一、选择题", "item_ids": ["Q001"]}],
        },
    )
    return manifest


def test_contract_backward_compatibility_and_archive_source_ref() -> None:
    legacy = {
        "schema": "math_topic_question_bank/v1",
        "bank": {
            "id": "legacy",
            "topic": "旧题库",
            "grade": "八年级",
            "source_explanation": "explanation.yaml",
            "target_count": 1,
        },
        "items": [
            {
                "id": "Q001",
                "title": "旧题",
                "question_type": "fillin",
                "difficulty": "foundation",
                "skill_tags": ["比例"],
                "variation_dimension": "changed_numbers",
                "student_assignment": "student.yaml",
                "teacher_assignment": "teacher.yaml",
            }
        ],
    }
    QuestionBank.model_validate(legacy)
    archive = yaml.safe_load(yaml.safe_dump(legacy))
    archive["bank"].pop("source_explanation")
    archive["bank"]["source_archive"] = "documents/paper"
    with pytest.raises(ValueError, match="source_ref"):
        QuestionBank.model_validate(archive)


def test_paper_assembly_keeps_inline_teacher_evidence_and_strips_student(tmp_path: Path) -> None:
    manifest = paper_fixture(tmp_path)
    ExamPaperManifest.model_validate(yaml.safe_load(manifest.read_text(encoding="utf-8")))
    output = tmp_path / "output"
    output.mkdir()
    teacher = assemble(manifest, output, "teacher")
    student = assemble(manifest, output, "student")
    teacher_block = teacher["sections"][0]["blocks"][0]
    student_block = student["sections"][0]["blocks"][0]
    assert teacher["render"]["answer_key_position"] == "inline"
    assert teacher_block["source_solution_images"]
    assert teacher_block["solution_notes"]
    assert "answer" not in student_block
    assert "source_solution_images" not in student_block
    assert "solution_notes" not in student_block
    assert validate_assignment(teacher, base_dir=output) == []
    assert validate_assignment(student, base_dir=output) == []
    teacher_tex = render(teacher)
    student_tex = render(student)
    assert "原解答" in teacher_tex
    assert "\\includegraphics" in teacher_tex
    assert "q001.png" in teacher_tex
    assert "q001.png" not in student_tex


def test_student_choice_and_fillin_do_not_require_answer() -> None:
    for question_type in ("choice", "fillin"):
        block = {
            "type": question_type,
            "id": f"{question_type}-1",
            "stem_latex": "求值。",
        }
        if question_type == "choice":
            block["choices"] = {"A": "1", "B": "2"}
        assignment = {
            "meta": {"title": "学生版", "version": "student"},
            "sections": [
                {
                    "id": "questions",
                    "type": "practice",
                    "visibility": "student",
                    "blocks": [block],
                }
            ],
        }
        assert validate_assignment(assignment) == []


def test_complex_source_stem_image_renders_instead_of_duplicate_text(
    tmp_path: Path,
) -> None:
    image = tmp_path / "prompt-full-question.png"
    Image.new("RGB", (120, 160), "white").save(image)
    assignment = {
        "meta": {"title": "材料题", "version": "student"},
        "render": {"template": "exam-zh-practice"},
        "sections": [
            {
                "id": "questions",
                "type": "practice",
                "visibility": "student",
                "blocks": [
                    {
                        "type": "problem",
                        "id": "Q022",
                        "stem_latex": "这段转写只用于检索，不应重复渲染。",
                        "stem_image": {
                            "image_path": image.name,
                            "width": "0.98\\linewidth",
                            "variant": "prompt",
                            "disclosure_policy": "clean",
                        },
                    }
                ],
            }
        ],
    }
    assert validate_assignment(assignment, base_dir=tmp_path) == []
    rendered = render(assignment)
    assert image.name in rendered
    assert "这段转写只用于检索" not in rendered
