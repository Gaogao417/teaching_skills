from __future__ import annotations

from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[1]
TOPIC_SCRIPTS = ROOT / ".codex/skills/math-topic-question-bank/scripts"
INGESTION_SCRIPTS = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
DOCX_INGESTION_SCRIPTS = (
    ROOT / ".codex/skills/math-docx-question-bank-ingestion/scripts"
)
sys.path.insert(0, str(TOPIC_SCRIPTS))
sys.path.insert(0, str(INGESTION_SCRIPTS))
sys.path.insert(0, str(DOCX_INGESTION_SCRIPTS))

from exam_source_contracts import ExamItemSource, ExamPaperMap  # noqa: E402
from audit_staging import (  # noqa: E402
    EMBEDDED_CHOICE_LABEL,
    box_area,
    box_intersection_area,
    choice_values,
)
from expand_staging_draft import expand_draft  # noqa: E402
from paper_map_contracts import validate_against_staging  # noqa: E402
from validate_exam_source import validate_source  # noqa: E402
from word_evidence_pages import (  # noqa: E402
    expected_page_ranges,
    infer_layout,
    resolve_draft_payload,
    validate_staging_coverage,
)


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


def test_word_evidence_uses_page_image_not_paragraphs_and_excluded_from_hash(
    tmp_path: Path,
) -> None:
    """Word 来源走整页图证据：字段是 page_image+page_number，不进 content_hash。"""
    from PIL import Image

    repo_root = tmp_path
    # 造两张真实整页 PNG（materialize 要打开算 hash）
    pages_dir = repo_root / "documents/PAPER-W/pages"
    pages_dir.mkdir(parents=True)
    for name in ("002.png", "005.png"):
        Image.new("RGB", (40, 60), "white").save(pages_dir / name)

    staging = repo_root / "staging/PAPER-W"
    draft = staging / "paper.draft.yaml"
    write_yaml(
        draft,
        {
            "schema": "math_exam_staging_draft/v1",
            "paper": {
                "id": "PAPER-W",
                "title": "W 区九年级数学",
                "grade": "九年级",
                "subject": "数学",
                "source_archive": "documents/PAPER-W",
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
                            "question_word_evidence": [
                                {
                                    "page_image": "documents/PAPER-W/pages/002.png",
                                    "page_number": 2,
                                }
                            ],
                            "prompt": [],
                            "official_solution": {
                                "start_anchor": "1. B",
                                "end_anchor": "<END_OF_SOURCE>",
                                "word_evidence": [
                                    {
                                        "page_image": "documents/PAPER-W/pages/005.png",
                                        "page_number": 5,
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

    # expand 应接受 page_image/page_number 新格式
    assert expand_draft(draft) == staging.resolve()
    source = yaml.safe_load(
        (staging / "items/Q001/source.yaml").read_text(encoding="utf-8")
    )
    we = source["word_evidence"]
    # 新字段：page_image / page_number / page_image_sha256，无旧字段
    assert we["question"][0]["page_image"] == "documents/PAPER-W/pages/002.png"
    assert we["question"][0]["page_number"] == 2
    assert "page_image_sha256" in we["question"][0]
    assert "paragraph_start" not in we["question"][0]
    assert "manifest" not in we["question"][0]
    assert we["official_solution"][0]["page_number"] == 5

    # 旧字段 draft 应被 expand 拒绝
    bad_draft = staging.parent / "PAPER-BAD/paper.draft.yaml"
    write_yaml(
        bad_draft,
        {
            "schema": "math_exam_staging_draft/v1",
            "paper": {
                "id": "PAPER-BAD",
                "title": "bad",
                "grade": "九",
                "subject": "数学",
                "source_archive": "documents/PAPER-W",
            },
            "question_bank": "../../question-bank.yaml",
            "sections": [
                {
                    "id": "choice",
                    "title": "x",
                    "items": [
                        {
                            "item_id": "Q001",
                            "question_number": 1,
                            "question_type": "choice",
                            "points": 4,
                            "question_word_evidence": [
                                {
                                    "manifest": "documents/x.yaml",
                                    "paragraph_start": 1,
                                    "paragraph_end": 2,
                                }
                            ],
                            "prompt": [],
                            "official_solution": {
                                "start_anchor": "1. B",
                                "end_anchor": "e",
                            },
                            "block": {
                                "stem_latex": "x",
                                "choices": ["1", "2", "3", "4"],
                                "answer": "B",
                            },
                        }
                    ],
                }
            ],
        },
    )
    try:
        expand_draft(bad_draft)
        assert False, "旧段落范围 draft 应被拒绝"
    except (TypeError, ValueError):
        pass

    # materialize_word_evidence：回填真实 page_image_sha256，并落盘
    from materialize_staging import materialize_word_evidence, sha256 as msha256

    for role, fname in (("question", "002.png"), ("official_solution", "005.png")):
        span = source["word_evidence"][role][0]
        materialize_word_evidence(span, repo_root=repo_root, label=f"Q001 {role}")
        assert span["page_image_sha256"] == msha256(pages_dir / fname)
        assert span["page_image_sha256"] != "sha256:" + "0" * 64
    write_yaml(staging / "items/Q001/source.yaml", source)

    # validate_source 通过（页图存在 + sha256 匹配）
    validated, errors = validate_source(
        staging / "items/Q001/source.yaml", repo_root=repo_root
    )
    assert validated is not None
    assert errors == [], f"validate_source 报错: {errors}"

    # validate 报页图缺失
    source["word_evidence"]["question"][0]["page_image"] = "documents/PAPER-W/pages/999.png"
    write_yaml(staging / "items/Q001/source.yaml", source)
    _, err2 = validate_source(
        staging / "items/Q001/source.yaml", repo_root=repo_root
    )
    assert any("missing page image" in e for e in err2), f"应报页图缺失: {err2}"


def test_word_evidence_page_ranges_cover_interleaved_cross_page_solution(
    tmp_path: Path,
) -> None:
    """交替排版必须补齐中间页和最后一题到文档末页。"""
    pages_dir = tmp_path / "documents/PAPER-CROSS/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 7):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    def evidence(page: int) -> list[dict[str, object]]:
        return [
            {
                "page_image": (
                    f"documents/PAPER-CROSS/word/pages/{page:03d}.png"
                ),
                "page_number": page,
            }
        ]

    draft = {
        "schema": "math_exam_staging_draft/v1",
        "sections": [
            {
                "id": "problem",
                "items": [
                    {
                        "item_id": "Q001",
                        "question_word_evidence": evidence(1),
                        "official_solution": {"word_evidence": evidence(2)},
                    },
                    {
                        "item_id": "Q002",
                        "question_word_evidence": evidence(3),
                        "official_solution": {"word_evidence": evidence(4)},
                    },
                ],
            }
        ],
    }
    resolved, report = resolve_draft_payload(
        draft,
        repo_root=tmp_path,
        layout="auto",
    )
    items = resolved["sections"][0]["items"]
    assert report["layout"] == "interleaved"
    assert [entry["page_number"] for entry in items[0]["question_word_evidence"]] == [
        1,
        2,
    ]
    assert [
        entry["page_number"]
        for entry in items[0]["official_solution"]["word_evidence"]
    ] == [2]
    assert [entry["page_number"] for entry in items[1]["question_word_evidence"]] == [
        3,
        4,
    ]
    assert [
        entry["page_number"]
        for entry in items[1]["official_solution"]["word_evidence"]
    ] == [4, 5, 6]


def test_word_evidence_page_ranges_support_separated_question_and_answer_sections() -> None:
    assert infer_layout([1, 2, 3], [7, 8, 9]) == "separated"
    assert expected_page_ranges(
        [1, 2, 3],
        [7, 8, 9],
        last_page=10,
        layout="separated",
    ) == [
        {"question": [1], "official_solution": [7]},
        {"question": [2], "official_solution": [8]},
        {"question": [3, 4, 5, 6], "official_solution": [9, 10]},
    ]


def test_staging_audit_rejects_incomplete_cross_page_word_evidence(
    tmp_path: Path,
) -> None:
    pages_dir = tmp_path / "documents/PAPER-CROSS/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 7):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    staging = tmp_path / "staging/PAPER-CROSS"
    for item_id, question, solution in (
        ("Q001", 1, 2),
        ("Q002", 3, 4),
    ):
        write_yaml(
            staging / f"items/{item_id}/source.yaml",
            {
                "item_id": item_id,
                "word_evidence": {
                    "question": [
                        {
                            "page_image": (
                                f"documents/PAPER-CROSS/word/pages/{question:03d}.png"
                            ),
                            "page_number": question,
                        }
                    ],
                    "official_solution": [
                        {
                            "page_image": (
                                f"documents/PAPER-CROSS/word/pages/{solution:03d}.png"
                            ),
                            "page_number": solution,
                        }
                    ],
                },
            },
        )
    errors = validate_staging_coverage(
        staging,
        ["Q001", "Q002"],
        repo_root=tmp_path,
    )
    assert errors == [
        (
            "Q001: word_evidence.question does not cover the complete "
            "interleaved range (missing pages [2])"
        ),
        (
            "Q002: word_evidence.question does not cover the complete "
            "interleaved range (missing pages [4])"
        ),
        (
            "Q002: word_evidence.official_solution does not cover the complete "
            "interleaved range (missing pages [5, 6])"
        ),
    ]
