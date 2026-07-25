from __future__ import annotations

import hashlib
from pathlib import Path
import sys

from PIL import Image
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
sys.path.insert(0, str(SCRIPTS))

import promote_exam_paper as promoter  # noqa: E402


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def assignment(item_id: str, number: int, *, teacher: bool) -> dict:
    block = {
        "type": "fillin",
        "id": item_id,
        "points": 4,
        "stem_latex": f"第 {number} 题：$x+{number}=$ \\fillin。",
    }
    if teacher:
        block.update(
            {
                "answer": f"${number}$",
                "explanation": "公众号原答案。",
                "teaching": {
                    "title": f"原题 {number}",
                    "difficulty": "standard" if number % 2 == 0 else "foundation",
                    "skill_tags": ["代数", f"第{number}题"],
                    "variation_dimension": "source_exam",
                    "diagram_requirement": "none",
                },
            }
        )
    return {
        "meta": {
            "title": f"{item_id} · {'教师版' if teacher else '学生版'}",
            "version": "teacher" if teacher else "student",
        },
        "render": {"template": "exam-zh-practice"},
        "sections": [
            {
                "id": "question",
                "title": "二、填空题",
                "type": "practice",
                "visibility": "both",
                "blocks": [block],
            }
        ],
    }


def make_staging_item(
    root: Path,
    paper_dir: Path,
    item_id: str,
    number: int,
    *,
    review_status: str = "approved",
    review_hash: str | None = None,
) -> None:
    original = root / "documents" / f"page-{number}.png"
    original.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (80, 60), "white").save(original)
    item_dir = paper_dir / "items" / item_id
    crop = item_dir / "assets" / "source.png"
    crop.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(original) as image:
        image.crop((10, 10, 60, 50)).save(crop)
    content_hash = f"sha256:{number:064x}"
    write_yaml(
        item_dir / "source.yaml",
        {
            "schema": "math_exam_item_source/v1",
            "item_id": item_id,
            "source_key": f"PAPER-A-Q{number:02d}",
            "paper_id": "PAPER-A",
            "question_number": number,
            "question_type": "fillin",
            "points": 4,
            "section_title": "二、填空题",
            "source_directory": "documents",
            "crops": {
                "question_evidence": [
                    {
                        "source": str(original.relative_to(root)),
                        "source_sha256": sha256(original),
                        "box_px": [10, 10, 60, 50],
                        "output": "assets/source.png",
                        "output_sha256": sha256(crop),
                    }
                ],
                "prompt": [],
                "official_solution": [
                    {
                        "source": str(original.relative_to(root)),
                        "source_sha256": sha256(original),
                        "box_px": [10, 10, 60, 50],
                        "output": "assets/source.png",
                        "output_sha256": sha256(crop),
                    }
                ],
            },
            "transcription": {
                "question_status": "author_pass",
                "official_solution_status": "author_pass",
                "human_review": "approved",
            },
            "content_hash": content_hash,
        },
    )
    write_yaml(
        item_dir / "review.yaml",
        {
            "schema": "math_exam_item_review/v1",
            "item_id": item_id,
            "source_key": f"PAPER-A-Q{number:02d}",
            "content_hash": review_hash or content_hash,
            "status": review_status,
            "reviewer": "reviewer",
            "reviewed_at": "2026-07-24T10:00:00+08:00",
            "notes": [],
        },
    )
    write_yaml(
        item_dir / "teacher.resolved.assignment.yaml",
        assignment(item_id, number, teacher=True),
    )
    write_yaml(
        item_dir / "student.resolved.assignment.yaml",
        assignment(item_id, number, teacher=False),
    )


def make_existing_item(bank_dir: Path) -> dict:
    item_id = "Q900"
    item_dir = bank_dir / "items" / item_id
    write_yaml(
        item_dir / "teacher.resolved.assignment.yaml",
        assignment(item_id, 900, teacher=True),
    )
    write_yaml(
        item_dir / "student.resolved.assignment.yaml",
        assignment(item_id, 900, teacher=False),
    )
    write_yaml(item_dir / "source.yaml", {"legacy": True})
    return {
        "id": item_id,
        "title": "旧正式题",
        "question_type": "fillin",
        "difficulty": "foundation",
        "skill_tags": ["旧题"],
        "variation_dimension": "source_exam",
        "diagram_requirement": "none",
        "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
        "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
        "source_ref": f"items/{item_id}/source.yaml",
        "weight": 1.0,
        "enabled": True,
    }


def fixture(
    tmp_path: Path,
    *,
    second_review_status: str = "approved",
    second_review_hash: str | None = None,
    with_existing: bool = True,
) -> tuple[Path, Path]:
    bank_dir = tmp_path / "bank"
    existing = [make_existing_item(bank_dir)] if with_existing else []
    write_yaml(
        bank_dir / "question-bank.yaml",
        {
            "schema": "math_topic_question_bank/v1",
            "bank": {
                "id": "exam-bank",
                "topic": "整卷原题",
                "grade": "九年级",
                "subject": "数学",
                "source_archive": "documents",
                "status": "plan",
                "target_count": 99,
            },
            "items": existing,
        },
    )
    paper_dir = bank_dir / "staging" / "PAPER-A"
    make_staging_item(tmp_path, paper_dir, "Q001", 1)
    make_staging_item(
        tmp_path,
        paper_dir,
        "Q002",
        2,
        review_status=second_review_status,
        review_hash=second_review_hash,
    )
    write_yaml(
        paper_dir / "paper.yaml",
        {
            "schema": "math_exam_paper/v1",
            "paper": {
                "id": "PAPER-A",
                "title": "A 卷",
                "grade": "九年级",
                "subject": "数学",
            },
            "question_bank": "../../question-bank.yaml",
            "sections": [
                {
                    "id": "fillin-a",
                    "title": "二、填空题 A",
                    "item_ids": ["Q002"],
                },
                {
                    "id": "fillin-b",
                    "title": "二、填空题 B",
                    "item_ids": ["Q001"],
                },
            ],
        },
    )
    write_yaml(
        paper_dir / "paper-map.yaml",
        {
            "schema": "math_exam_paper_map/v1",
            "paper_id": "PAPER-A",
            "items": [
                {
                    "item_id": "Q002",
                    "question_number": 2,
                    "question_pages": ["documents/page-2.png"],
                    "official_solution": {
                        "pages": ["documents/page-2.png"],
                        "start_anchor": "2. 解：",
                        "end_anchor": "1. 解：",
                    },
                },
                {
                    "item_id": "Q001",
                    "question_number": 1,
                    "question_pages": ["documents/page-1.png"],
                    "official_solution": {
                        "pages": ["documents/page-1.png"],
                        "start_anchor": "1. 解：",
                        "end_anchor": "<END_OF_SOURCE>",
                    },
                },
            ],
        },
    )
    return paper_dir / "paper.yaml", bank_dir / "question-bank.yaml"


def test_promotes_whole_paper_in_section_order_and_preserves_old_items(
    tmp_path: Path,
) -> None:
    paper, bank = fixture(tmp_path)
    result = promoter.promote_paper(paper, bank, repo_root=tmp_path)

    promoted = yaml.safe_load(bank.read_text(encoding="utf-8"))
    assert [item["id"] for item in promoted["items"]] == ["Q900", "Q002", "Q001"]
    assert promoted["items"][1]["title"] == "原题 2"
    assert promoted["items"][1]["difficulty"] == "standard"
    assert promoted["items"][1]["skill_tags"] == ["代数", "第2题"]
    assert promoted["items"][1]["variation_dimension"] == "source_exam"
    assert (bank.parent / "items/Q900/teacher.resolved.assignment.yaml").is_file()
    assert (bank.parent / "items/Q001/source.yaml").is_file()
    assert (bank.parent / "items/Q002/review.yaml").is_file()
    formal_source = yaml.safe_load(
        (bank.parent / "items/Q001/source.yaml").read_text(encoding="utf-8")
    )
    assert formal_source["transcription"]["human_review"] == "approved"

    paper_copy = Path(result["paper_manifest"])
    copied = yaml.safe_load(paper_copy.read_text(encoding="utf-8"))
    assert copied["question_bank"] == "../../question-bank.yaml"
    assert [item for section in copied["sections"] for item in section["item_ids"]] == [
        "Q002",
        "Q001",
    ]
    copied_map = yaml.safe_load(
        (paper_copy.parent / "paper-map.yaml").read_text(encoding="utf-8")
    )
    assert [item["item_id"] for item in copied_map["items"]] == ["Q002", "Q001"]


@pytest.mark.parametrize(
    ("review_status", "review_hash", "message"),
    [
        ("pending", None, "review status must be approved"),
        ("approved", f"sha256:{'f' * 64}", "content_hash"),
    ],
)
def test_review_failure_registers_nothing(
    tmp_path: Path,
    review_status: str,
    review_hash: str | None,
    message: str,
) -> None:
    paper, bank = fixture(
        tmp_path,
        second_review_status=review_status,
        second_review_hash=review_hash,
        with_existing=False,
    )
    original = bank.read_bytes()
    with pytest.raises(ValueError, match=message):
        promoter.promote_paper(paper, bank, repo_root=tmp_path)
    assert bank.read_bytes() == original
    assert not (bank.parent / "items/Q001").exists()
    assert not (bank.parent / "items/Q002").exists()
    assert not (bank.parent / "papers/PAPER-A").exists()


def test_rejects_manifest_or_directory_id_conflicts(tmp_path: Path) -> None:
    paper, bank = fixture(tmp_path, with_existing=False)
    payload = yaml.safe_load(bank.read_text(encoding="utf-8"))
    payload["items"].append(
        {
            "id": "Q001",
            "title": "冲突题",
            "question_type": "fillin",
            "difficulty": "foundation",
            "skill_tags": ["冲突"],
            "variation_dimension": "source_exam",
            "student_assignment": "items/Q001/student.resolved.assignment.yaml",
            "teacher_assignment": "items/Q001/teacher.resolved.assignment.yaml",
            "source_ref": "items/Q001/source.yaml",
        }
    )
    write_yaml(bank, payload)
    with pytest.raises(ValueError, match="item ID conflict"):
        promoter.promote_paper(paper, bank, repo_root=tmp_path)

    payload["items"] = []
    write_yaml(bank, payload)
    (bank.parent / "items/Q002").mkdir(parents=True)
    with pytest.raises(ValueError, match="directory conflict"):
        promoter.promote_paper(paper, bank, repo_root=tmp_path)


def test_atomic_manifest_failure_rolls_back_copied_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paper, bank = fixture(tmp_path, with_existing=False)
    original = bank.read_bytes()

    def fail_replace(path: Path, payload: dict) -> None:
        raise OSError("simulated manifest replace failure")

    monkeypatch.setattr(promoter, "_atomic_replace_yaml", fail_replace)
    with pytest.raises(OSError, match="simulated"):
        promoter.promote_paper(paper, bank, repo_root=tmp_path)
    assert bank.read_bytes() == original
    assert not (bank.parent / "items/Q001").exists()
    assert not (bank.parent / "items/Q002").exists()
    assert not (bank.parent / "papers/PAPER-A").exists()
