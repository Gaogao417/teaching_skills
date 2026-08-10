from __future__ import annotations

from pathlib import Path
import sys

import pytest
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
    mentions_figure,
    normalize_choice_labels,
)
from expand_staging_draft import expand_draft  # noqa: E402
from paper_map_contracts import validate_against_staging  # noqa: E402
from validate_exam_source import validate_source  # noqa: E402
from word_evidence_pages import (  # noqa: E402
    _page_index_from_name,
    allowed_shared_boundaries,
    coerce_question_seeds,
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
    # Decimals / scientific notation are option BODIES, not labels: the half-width
    # dot branch must not fire when a digit follows. （3.14 → pi, 0.3 → decimal,
    # 3.0 \times 10^8 → scientific, 2.5x → coefficient.）
    for body in ("3.14", "0.3", "2.5x", r"3.0 \times 10^8", "1.0"):
        assert not EMBEDDED_CHOICE_LABEL.match(body), body
    # A half-width dot after a digit IS a label only with a non-digit follower.
    assert EMBEDDED_CHOICE_LABEL.match("3. 正文")
    assert EMBEDDED_CHOICE_LABEL.match("3.正文")


def test_choice_label_normalize_complete_sequence() -> None:
    # Complete ordered A–D with non-empty bodies → normalizable, bodies returned.
    ok, stripped = normalize_choice_labels(["A. 甲", "B. 乙", "C. 丙", "D. 丁"])
    assert ok is True
    assert stripped == ["甲", "乙", "丙", "丁"]
    # Numeric sequence 0–3 with CJK separators normalizes too.
    ok, stripped = normalize_choice_labels(["0、甲", "1、乙", "2、丙", "3、丁"])
    assert ok is True
    assert stripped == ["甲", "乙", "丙", "丁"]
    # Parenthesized letters form a complete sequence.
    ok, stripped = normalize_choice_labels(["（A）甲", "（B）乙", "（C）丙", "（D）丁"])
    assert ok is True
    assert stripped == ["甲", "乙", "丙", "丁"]


def test_choice_label_empty_body_still_blocked() -> None:
    # A label-only placeholder (no body) is NOT normalizable — it must stay a
    # structural error rather than collapse into an empty option.
    ok, stripped = normalize_choice_labels(["A.", "B. 乙", "C. 丙", "D. 丁"])
    assert ok is True
    assert stripped is not None
    assert stripped[0] == ""  # caller checks: any empty body → keep as error


def test_choice_label_partial_sequence_not_normalizable() -> None:
    # Only some choices carry labels, or labels are out of order → not a complete
    # sequence, so normalize_choice_labels returns False and the per-choice
    # embedded-label check stays in force for the genuinely labelled ones.
    ok, stripped = normalize_choice_labels(["A. 甲", "乙", "C. 丙", "D. 丁"])
    assert ok is False
    assert stripped is None
    ok, stripped = normalize_choice_labels(["A. 甲", "A. 乙", "C. 丙", "D. 丁"])
    assert ok is False
    assert stripped is None


def test_mentions_figure_detects_strong_signals() -> None:
    # 强信号短语：明确指代一张配图，应命中。
    for stem in (
        "如图，在 $\\triangle ABC$ 中，$D$ 是 $AB$ 的中点",
        "函数 $y=kx+b$ 的图象如图所示",
        "下图中，线段 $AB$ 的长为",
        "上图中阴影部分的面积",
        "图中四边形 $ABCD$ 是矩形",
        "某几何体的示意图如下",
    ):
        assert mentions_figure(stem), stem
    # 纯文字描述里的「图」字：不指代具体配图，不应命中（避免误报）。
    for stem in (
        "下面选项中既是中心对称图形又是轴对称图形的是",
        "反比例函数 $y=\\frac{k}{x}$ 的图象在二、四象限",
        "根据统计图可知",
        "该班学生身高柱状图的众数是",
        "",
        None,
    ):
        assert not mentions_figure(stem), stem


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


def test_word_evidence_allows_and_preserves_shared_boundary_page(
    tmp_path: Path,
) -> None:
    """前题 2–3、后题 3–4 时，共享的第 3 页不能被判无效或被重写掉。"""
    assert allowed_shared_boundaries(
        [2, 3],
        [7, 9],
        layout="separated",
    ) == [
        {"question": {3}, "official_solution": {9}},
        {"question": {7}, "official_solution": set()},
    ]

    pages_dir = tmp_path / "documents/PAPER-BOUNDARY/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 11):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    def evidence(*pages: int) -> list[dict[str, object]]:
        return [
            {
                "page_image": (
                    f"documents/PAPER-BOUNDARY/word/pages/{page:03d}.png"
                ),
                "page_number": page,
            }
            for page in pages
        ]

    draft = {
        "schema": "math_exam_staging_draft/v1",
        "sections": [
            {
                "id": "problem",
                "items": [
                    {
                        "item_id": "Q001",
                        "question_word_evidence": evidence(2, 3),
                        "official_solution": {"word_evidence": evidence(7, 8, 9)},
                    },
                    {
                        "item_id": "Q002",
                        "question_word_evidence": evidence(3, 4, 5, 6),
                        "official_solution": {"word_evidence": evidence(9, 10)},
                    },
                ],
            }
        ],
    }
    resolved, report = resolve_draft_payload(
        draft,
        repo_root=tmp_path,
        layout="separated",
    )
    assert report["changes"] == []
    items = resolved["sections"][0]["items"]
    assert [
        entry["page_number"] for entry in items[0]["question_word_evidence"]
    ] == [2, 3]
    assert [
        entry["page_number"]
        for entry in items[0]["official_solution"]["word_evidence"]
    ] == [7, 8, 9]


def _write_word_evidence_item(
    staging: Path,
    item_id: str,
    *,
    paper: str,
    question_pages: list[int],
    solution_pages: list[int],
) -> None:
    def evidence(pages: list[int]) -> list[dict[str, object]]:
        return [
            {
                "page_image": f"documents/{paper}/word/pages/{page:03d}.png",
                "page_number": page,
            }
            for page in pages
        ]

    write_yaml(
        staging / f"items/{item_id}/source.yaml",
        {
            "item_id": item_id,
            "word_evidence": {
                "question": evidence(question_pages),
                "official_solution": evidence(solution_pages),
            },
        },
    )


def test_staging_audit_accepts_non_contiguous_evidence(tmp_path: Path) -> None:
    """填空/选择题同页共享、单题只标种子页都合法，不再强制逐题连续覆盖。

    Q001 题干 p1、解答 p2；Q002 题干 p3/p4（跨页）、解答 p4。整卷 1..4 全覆盖，
    每题非空且页码在范围内 → 无任何错误。旧实现会把这种如实标注判成逐题 missing。
    """
    pages_dir = tmp_path / "documents/PAPER-NONCONTIG/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 5):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    staging = tmp_path / "staging/PAPER-NONCONTIG"
    _write_word_evidence_item(
        staging,
        "Q001",
        paper="PAPER-NONCONTIG",
        question_pages=[1],
        solution_pages=[2],
    )
    _write_word_evidence_item(
        staging,
        "Q002",
        paper="PAPER-NONCONTIG",
        question_pages=[3, 4],
        solution_pages=[4],
    )
    errors = validate_staging_coverage(
        staging,
        ["Q001", "Q002"],
        repo_root=tmp_path,
    )
    assert errors == []


def test_staging_audit_flags_whole_paper_coverage_gap(tmp_path: Path) -> None:
    """整卷若有页无人覆盖，只报一条整卷漏页，不再逐题报 missing/extra。

    页 1..6 都有页图，但 evidence 只覆盖 1..4（p5、p6 无人标）→ 仅一条整卷漏页。
    """
    pages_dir = tmp_path / "documents/PAPER-GAP/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 7):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    staging = tmp_path / "staging/PAPER-GAP"
    _write_word_evidence_item(
        staging,
        "Q001",
        paper="PAPER-GAP",
        question_pages=[1],
        solution_pages=[2],
    )
    _write_word_evidence_item(
        staging,
        "Q002",
        paper="PAPER-GAP",
        question_pages=[3],
        solution_pages=[4],
    )
    errors = validate_staging_coverage(
        staging,
        ["Q001", "Q002"],
        repo_root=tmp_path,
    )
    assert errors == [
        (
            "Word evidence coverage: pages [5, 6] not covered by any item "
            "(expected full coverage of pages 1..6)"
        )
    ]


def test_staging_audit_rejects_out_of_range_evidence_pages(tmp_path: Path) -> None:
    """页码越界（超出 last_page）逐题报错，整卷覆盖仍单独检查。"""
    pages_dir = tmp_path / "documents/PAPER-OOR/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 5):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    staging = tmp_path / "staging/PAPER-OOR"
    _write_word_evidence_item(
        staging,
        "Q001",
        paper="PAPER-OOR",
        question_pages=[1, 9],  # 9 > last_page 4
        solution_pages=[2],
    )
    _write_word_evidence_item(
        staging,
        "Q002",
        paper="PAPER-OOR",
        question_pages=[3],
        solution_pages=[4],
    )
    errors = validate_staging_coverage(
        staging,
        ["Q001", "Q002"],
        repo_root=tmp_path,
    )
    assert errors == [
        "Q001: word_evidence.question pages [9] outside [1, 4]",
    ]


def test_expected_page_ranges_rejects_interleaved_blowup() -> None:
    """interleaved 误判 + 大跨度不能把单题来源页膨胀到几百页。

    复现"长宁一模最后一题 306 个来源页"：interleaved 分支用
    ``range(question_start, solution_start + 1)`` 填充，当 solution_start 远大于
    question_start 时一次性生成上百页，这些页全在 [1, last_page] 内且恰好
    覆盖整卷，所以放宽后的整卷审计不拦。per-role 上限护栏必须在此硬拦截。
    """
    # interleaved + q=1 + s=306 + last=306 → range(1, 307) = 306 页
    with pytest.raises(ValueError, match="exceeds the per-role ceiling"):
        expected_page_ranges(
            [1],
            [306],
            last_page=306,
            layout="interleaved",
        )


def test_resolve_draft_payload_auto_blocks_runaway_interleaved(
    tmp_path: Path,
) -> None:
    """auto 模式下 infer_layout 误判 interleaved 时，resolve 必须报错而非产出几百页。

    转录把单题 solution 种子标到整卷末页，单题即满足 interleaved 充要条件
    (q[i]<=s[i])，于是 interleaved 分支用 range(q, s+1) 把题→解之间所有页填进
    question evidence。这些页全在 [1, last_page] 内且恰好覆盖整卷，放宽后的
    审计不拦。coerce_question_seeds 只在手动 --layout 时生效，auto 路径靠
    per-role 上限护栏兜底。
    """
    # 60 页真实页图 (last_page=60 合法，远低于整卷 200 上限)；单题 q=1 s=60
    # → interleaved → range(1, 61) = 60 页 > 50 的 per-role 上限 → 硬拦截。
    pages_dir = tmp_path / "documents/PAPER-BLOWUP/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 61):
        (pages_dir / f"{page:03d}.png").write_bytes(b"page")

    def evidence(page: int) -> list[dict[str, object]]:
        return [
            {
                "page_image": f"documents/PAPER-BLOWUP/word/pages/{page:03d}.png",
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
                        "official_solution": {"word_evidence": evidence(60)},
                    },
                ],
            }
        ],
    }
    with pytest.raises(ValueError, match="exceeds the per-role ceiling"):
        resolve_draft_payload(draft, repo_root=tmp_path, layout="auto")


def test_coerce_question_seeds_repairs_outlier_in_manual_layout() -> None:
    """手动 --layout separated 时，标到答案区的 outlier question 种子被钳位。

    转录常把压轴题唯一证据页（答案页）记成 question_word_evidence 首页，该种子
    违反 separated 不变量（question 必须在首个 solution 之前），裸 --layout 会
    膨胀成跨页区间。coerce_question_seeds 保守地把它钳到 first_solution-1 并保持
    单调非递减，返回逐项修正记录供审核。
    """
    # 3 题：Q003 的 question 种子 28 落在答案区（solution 从 p9 起）→ 钳到 8
    question = [1, 2, 28]
    solution = [9, 12, 15]
    coerced, corrections = coerce_question_seeds(question, solution, layout="separated")
    assert coerced == [1, 2, 8]
    assert corrections == [{"index": 2, "original": 28, "coerced": 8}]

    # 手动 separated 但不给 override：违反布局的种子必须报错，不能静默膨胀。
    # _seeds_violate_layout 在 _last_page_from_evidence 之前触发，故 repo_root
    # 不会被实际用到，传一个不存在的路径即可。
    with pytest.raises(ValueError, match="violate the confirmed layout"):
        resolve_draft_payload(
            {
                "schema": "math_exam_staging_draft/v1",
                "sections": [
                    {
                        "id": "problem",
                        "items": [
                            {
                                "item_id": "Q001",
                                "question_word_evidence": [
                                    {
                                        "page_image": "documents/P/word/pages/001.png",
                                        "page_number": 1,
                                    }
                                ],
                                "official_solution": {
                                    "word_evidence": [
                                        {
                                            "page_image": "documents/P/word/pages/009.png",
                                            "page_number": 9,
                                        }
                                    ]
                                },
                            },
                            {
                                "item_id": "Q002",
                                "question_word_evidence": [
                                    {
                                        "page_image": "documents/P/word/pages/028.png",
                                        "page_number": 28,
                                    }
                                ],
                                "official_solution": {
                                    "word_evidence": [
                                        {
                                            "page_image": "documents/P/word/pages/012.png",
                                            "page_number": 12,
                                        }
                                    ]
                                },
                            },
                        ],
                    }
                ],
            },
            repo_root=Path("/nonexistent-repo-root"),
            layout="separated",
        )


# --------------------------------------------------------------------------- #
# D-pages: page-N.png naming compatibility (PDF-extracted pages)
# --------------------------------------------------------------------------- #


def test_page_index_from_name_handles_both_naming_conventions() -> None:
    """_page_index_from_name 接受纯数字(001)和 page-N(page-01)两种命名。

    PDF 提取产出 page-01.png / page-1.png，DOCX 提取产出 001.png。
    旧代码的 path.stem.isdigit() 跳过了所有 page-N 文件，导致
    _last_page_from_evidence 对 PDF 源卷报 "no rendered pages found"。
    """
    assert _page_index_from_name("001") == 1
    assert _page_index_from_name("042") == 42
    assert _page_index_from_name("page-01") == 1
    assert _page_index_from_name("page-1") == 1
    assert _page_index_from_name("page-29") == 29
    # 非页文件（media/ 公式碎片）返回 None，调用方跳过
    assert _page_index_from_name("image1") is None
    assert _page_index_from_name("media") is None


def test_last_page_from_evidence_reads_page_n_named_directory(
    tmp_path: Path,
) -> None:
    """_last_page_from_evidence 对 page-N.png 命名的页图目录正确取末页。

    复现 D 类 2026-BAOSHAN 场景：35 个 page-NN.png 文件，旧 isdigit() 全跳过。
    """
    pages_dir = tmp_path / "documents/BAOSHAN/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 36):
        (pages_dir / f"page-{page:02d}.png").write_bytes(b"page")

    draft = {
        "schema": "math_exam_staging_draft/v1",
        "sections": [
            {
                "id": "problem",
                "items": [
                    {
                        "item_id": "Q001",
                        "question_word_evidence": [
                            {
                                "page_image": "documents/BAOSHAN/word/pages/page-01.png",
                                "page_number": 1,
                            }
                        ],
                        "official_solution": {
                            "word_evidence": [
                                {
                                    "page_image": "documents/BAOSHAN/word/pages/page-01.png",
                                    "page_number": 1,
                                }
                            ]
                        },
                    },
                ],
            }
        ],
    }
    # interleaved 单题 q=s=1；last_page 应解析为 35（不是报错）
    _, report = resolve_draft_payload(draft, repo_root=tmp_path, layout="interleaved")
    assert report["last_page"] == 35


def test_entries_for_pages_emits_page_n_prefix_for_pdf_source(
    tmp_path: Path,
) -> None:
    """resolve 对 page-N 源卷输出的 evidence 路径保留 page- 前缀。

    确保展开后的 page_image 路径和磁盘上的 page-NN.png 命名一致，
    不会退回 001.png（那样 materialize 阶段找不到文件）。
    """
    pages_dir = tmp_path / "documents/QINGPU/word/pages"
    pages_dir.mkdir(parents=True)
    for page in range(1, 8):
        (pages_dir / f"page-{page:01d}.png").write_bytes(b"page")

    draft = {
        "schema": "math_exam_staging_draft/v1",
        "sections": [
            {
                "id": "problem",
                "items": [
                    {
                        "item_id": "Q001",
                        "question_word_evidence": [
                            {
                                "page_image": "documents/QINGPU/word/pages/page-1.png",
                                "page_number": 1,
                            }
                        ],
                        "official_solution": {
                            "word_evidence": [
                                {
                                    "page_image": "documents/QINGPU/word/pages/page-1.png",
                                    "page_number": 1,
                                }
                            ]
                        },
                    },
                    {
                        "item_id": "Q002",
                        "question_word_evidence": [
                            {
                                "page_image": "documents/QINGPU/word/pages/page-2.png",
                                "page_number": 2,
                            }
                        ],
                        "official_solution": {
                            "word_evidence": [
                                {
                                    "page_image": "documents/QINGPU/word/pages/page-3.png",
                                    "page_number": 3,
                                }
                            ]
                        },
                    },
                ],
            }
        ],
    }
    resolved, _ = resolve_draft_payload(draft, repo_root=tmp_path, layout="interleaved")
    q1 = resolved["sections"][0]["items"][0]["question_word_evidence"]
    # 展开后路径仍以 page- 开头，不是纯数字
    assert all("page-" in e["page_image"] for e in q1), [
        e["page_image"] for e in q1
    ]
