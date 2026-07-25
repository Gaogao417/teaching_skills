from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
TOPIC_SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
INGESTION_SCRIPTS = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
sys.path.insert(0, str(TOPIC_SCRIPTS))
sys.path.insert(0, str(INGESTION_SCRIPTS))

from exam_source_contracts import ExamPaperMap  # noqa: E402
from audit_staging import (  # noqa: E402
    EMBEDDED_CHOICE_LABEL,
    box_area,
    box_intersection_area,
    choice_values,
)
from expand_staging_draft import expand_draft  # noqa: E402
from paper_map_contracts import validate_against_staging  # noqa: E402


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def test_paper_map_matches_source_page_order_and_anchors(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    source_path = staging / "items/Q001/source.yaml"
    write_yaml(
        source_path,
        {
            "question_number": 1,
            "crops": {
                "question_evidence": [
                    {"source": "documents/page-001.png"},
                    {"source": "documents/page-001.png"},
                ],
                "official_solution": [
                    {"source": "documents/page-006.png"},
                    {"source": "documents/page-007.png"},
                ],
            },
        },
    )
    payload = {
        "schema": "math_exam_paper_map/v1",
        "paper_id": "PAPER-A",
        "items": [
            {
                "item_id": "Q001",
                "question_number": 1,
                "question_pages": ["documents/page-001.png"],
                "official_solution": {
                    "pages": [
                        "documents/page-006.png",
                        "documents/page-007.png",
                    ],
                    "start_anchor": "1. 解：",
                    "end_anchor": "<END_OF_SOURCE>",
                },
            }
        ],
    }
    paper_map = ExamPaperMap.model_validate(payload)
    assert validate_against_staging(
        paper_map,
        paper_id="PAPER-A",
        ordered_item_ids=["Q001"],
        staging_dir=staging,
    ) == []

    payload["items"][0]["official_solution"]["pages"].reverse()
    mismatched = ExamPaperMap.model_validate(payload)
    errors = validate_against_staging(
        mismatched,
        paper_id="PAPER-A",
        ordered_item_ids=["Q001"],
        staging_dir=staging,
    )
    assert errors == [
        "Q001: paper-map official_solution pages differ from crop sources"
    ]


def test_prompt_overlap_helpers_detect_near_full_question_crop() -> None:
    evidence = [100, 200, 900, 700]
    near_duplicate_prompt = [110, 205, 890, 695]
    figure_only_prompt = [620, 330, 850, 610]

    evidence_area = box_area(evidence)
    near_area = box_area(near_duplicate_prompt)
    figure_area = box_area(figure_only_prompt)

    assert near_area / evidence_area >= 0.8
    assert (
        box_intersection_area(near_duplicate_prompt, evidence) / near_area
        >= 0.9
    )
    assert figure_area / evidence_area < 0.8


def test_choice_values_reject_embedded_numeric_or_letter_labels() -> None:
    assert choice_values(["正文一", "正文二"]) == ["正文一", "正文二"]
    assert choice_values({"A": "正文一", "B": "正文二"}) == ["正文一", "正文二"]
    for dirty in ("0. 正文", "1、正文", "A. 正文", "（B）正文"):
        assert EMBEDDED_CHOICE_LABEL.match(dirty)
    assert not EMBEDDED_CHOICE_LABEL.match(r"$1<x<2$")


def test_compact_draft_expands_canonical_staging_without_student_copy(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging/PAPER-A"
    draft = staging / "paper.draft.yaml"
    write_yaml(
        draft,
        {
            "schema": "math_exam_staging_draft/v1",
            "paper": {
                "id": "PAPER-A",
                "title": "A 区九年级数学",
                "grade": "九年级",
                "subject": "数学",
                "source_archive": "documents/PAPER-A",
            },
            "question_bank": "../../question-bank.yaml",
            "sections": [
                {
                    "id": "choice",
                    "title": "一、选择题",
                    "items": [
                        {
                            "item_id": "Q001",
                            "question_number": 1,
                            "question_type": "choice",
                            "points": 4,
                            "question_evidence": [
                                {
                                    "source": "documents/PAPER-A/001.png",
                                    "box_px": [10, 20, 90, 60],
                                }
                            ],
                            "prompt": [],
                            "official_solution": {
                                "start_anchor": "1. B",
                                "end_anchor": "<END_OF_SOURCE>",
                                "crops": [
                                    {
                                        "source": "documents/PAPER-A/006.png",
                                        "box_px": [10, 10, 90, 40],
                                    }
                                ],
                            },
                            "block": {
                                "stem_latex": "若 $x=1$，则 $x+1=$",
                                "choices": ["1", "2", "3", "4"],
                                "answer": "B",
                                "explanation": "官方参考答案：B。",
                            },
                        }
                    ],
                }
            ],
        },
    )

    assert expand_draft(draft) == staging.resolve()
    source = yaml.safe_load(
        (staging / "items/Q001/source.yaml").read_text(encoding="utf-8")
    )
    teacher = yaml.safe_load(
        (
            staging / "items/Q001/teacher.resolved.assignment.yaml"
        ).read_text(encoding="utf-8")
    )
    paper_map = ExamPaperMap.model_validate(
        yaml.safe_load((staging / "paper-map.yaml").read_text(encoding="utf-8"))
    )

    assert "independent_review" not in source["transcription"]
    assert source["transcription"]["human_review"] == "pending"
    assert teacher["sections"][0]["blocks"][0]["source_solution_images"][0][
        "image_path"
    ] == "assets/official-solution-01.png"
    assert not (staging / "items/Q001/author.yaml").exists()
    assert not (staging / "items/Q001/student.resolved.assignment.yaml").exists()
    assert paper_map.items[0].question_pages == ["documents/PAPER-A/001.png"]
