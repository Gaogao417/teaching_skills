from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from scripts.question_transcription.workflow.adapters.source.figure_detection import (
    FigureDetector,
    _expand_clipped_ink,
)


class _FakeClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, **kwargs: Any) -> tuple[Any, bool]:
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response, False


def _page(tmp_path: Path, size: tuple[int, int] = (2000, 1000)) -> Path:
    path = tmp_path / "page.png"
    Image.new("RGB", size, "white").save(path)
    return path


def _questions(*numbers: int) -> list[dict[str, Any]]:
    return [
        {"question_number": number, "stem": f"第 {number} 题如图"}
        for number in numbers
    ]


def test_width_normalized_coordinates_are_clamped_and_converted_to_pixels(
    tmp_path: Path,
) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 4,
                        "nearest_question_anchor": "（第4题图）",
                        "box_w1000": [-10, -10, 300, 300],
                    }
                ],
            },
            {
                "is_math_figure": True,
                "is_complete": True,
                "clipped_edges": [],
                "dominant_content": "math_figure",
                "figure_box_w1000": [100, 100, 900, 900],
                "confidence": "high",
                "reason": "主体为几何图",
            },
        ]
    )
    page = _page(tmp_path)

    result = FigureDetector(client=client).detect(
        page,
        page_sha256="sha256:test",
        questions=_questions(4),
        page_size=(2000, 1000),
    )

    # The endpoint box is clamped to the page and retained alongside the
    # validator sub-box; neither coordinate interpretation is discarded.
    assert result.boxes == {4: [[0, 0, 824, 824]]}
    localization_prompt = client.calls[0]["messages"][0]["content"][1]["text"]
    assert "width_normalized_1000 等比例坐标" in localization_prompt
    assert "绝对禁止输出像素坐标" in localization_prompt
    assert "右下角约为(1000,500)" in localization_prompt


def test_undeclared_coordinate_system_is_rejected_without_crop_validation(
    tmp_path: Path,
) -> None:
    client = _FakeClient(
        [
            {
                "figures": [
                    {
                        "question_number": 4,
                        "nearest_question_anchor": "第4题",
                        "box_w1000": [600, 100, 800, 400],
                    }
                ]
            }
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=_questions(4),
        page_size=(2000, 1000),
    )

    assert result.boxes == {}
    assert "width_normalized_1000" in result.review_notes[4][0]
    assert len(client.calls) == 1


def test_transient_connection_error_is_retried(tmp_path: Path) -> None:
    client = _FakeClient(
        [
            ConnectionError("transient"),
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 4,
                        "nearest_question_anchor": "第4题图",
                        "box_w1000": [600, 100, 800, 400],
                    }
                ],
            },
            {
                "is_math_figure": True,
                "is_complete": True,
                "clipped_edges": [],
                "dominant_content": "math_figure",
                "figure_box_w1000": [0, 0, 1000, 1000],
                "confidence": "high",
                "reason": "主体为几何图",
            },
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=_questions(4),
        page_size=(2000, 1000),
    )

    assert 4 in result.boxes
    assert len(client.calls) == 3


def test_same_box_cannot_be_assigned_to_two_questions(tmp_path: Path) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 4,
                        "nearest_question_anchor": "第4题图",
                        "box_w1000": [600, 100, 800, 400],
                    },
                    {
                        "question_number": 6,
                        "nearest_question_anchor": "第6题图",
                        "box_w1000": [600, 100, 800, 400],
                    },
                ],
            }
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=_questions(4, 6),
        page_size=(2000, 1000),
    )

    assert result.boxes == {}
    assert "无法唯一配对" in result.review_notes[4][0]
    assert "无法唯一配对" in result.review_notes[6][0]
    assert len(client.calls) == 1


def test_subfigure_caption_is_cross_checked_against_question_stem(
    tmp_path: Path,
) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 22,
                        "nearest_question_anchor": "图3",
                        "box_w1000": [300, 100, 500, 300],
                    }
                ],
            },
            {
                "is_math_figure": True,
                "is_complete": True,
                "clipped_edges": [],
                "dominant_content": "math_figure",
                "figure_box_w1000": [0, 0, 1000, 1000],
                "confidence": "high",
                "reason": "主体为测高示意图",
            },
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=[
            {
                "question_number": 22,
                "stem": "制作测高仪（如图1），第一次实践如图3，第二次如图4。",
            }
        ],
        page_size=(2000, 1000),
    )

    assert 22 in result.boxes
    assert result.review_notes == {}


def test_text_dominant_candidate_fails_second_pass_validation(tmp_path: Path) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 4,
                        "nearest_question_anchor": "第4题",
                        "box_w1000": [300, 100, 600, 400],
                    }
                ],
            },
            {
                "is_math_figure": False,
                "is_complete": False,
                "clipped_edges": [],
                "dominant_content": "answer_option",
                "confidence": "high",
                "reason": "主体为选择题文字",
            },
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=_questions(4),
        page_size=(2000, 1000),
    )

    assert result.boxes == {}
    assert "主体为选择题文字" in result.review_notes[4][0]
    assert len(client.calls) == 2


def test_solution_figures_are_bound_to_validated_question_steps(
    tmp_path: Path,
) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 20,
                        "solution_step_index": 1,
                        "nearest_question_anchor": "20．",
                        "nearest_solution_anchor": "（2）如图",
                        "box_w1000": [100, 100, 350, 350],
                    },
                    {
                        "question_number": 21,
                        "solution_step_index": 0,
                        "nearest_question_anchor": "21．",
                        "nearest_solution_anchor": "第21题图",
                        "box_w1000": [600, 100, 850, 350],
                    },
                ],
            },
            {
                "is_math_figure": True,
                "belongs_to_solution_step": True,
                "dominant_content": "math_figure",
                "figure_box_w1000": [0, 0, 1000, 1000],
                "confidence": "high",
                "reason": "辅助图与（2）相邻",
            },
            {
                "is_math_figure": True,
                "belongs_to_solution_step": True,
                "dominant_content": "math_figure",
                "figure_box_w1000": [0, 0, 1000, 900],
                "confidence": "high",
                "reason": "图注为第21题图",
            },
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=[
            {
                "question_number": 20,
                "stem": "",
                "solution_steps": ["先证明。", "作辅助线，如图。"],
            },
            {
                "question_number": 21,
                "stem": "",
                "solution_steps": ["由第21题图可得。"],
            },
        ],
        page_size=(2000, 1000),
        role="solution",
    )

    assert set(result.boxes) == {20, 21}
    assert result.step_indices == {20: [1], 21: [0]}
    assert "solution_step_index" in client.calls[0]["messages"][0]["content"][1]["text"]


def test_solution_crop_rejected_when_step_ownership_is_not_confirmed(
    tmp_path: Path,
) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 20,
                        "solution_step_index": 0,
                        "nearest_question_anchor": "20．",
                        "nearest_solution_anchor": "（1）",
                        "box_w1000": [100, 100, 350, 350],
                    }
                ],
            },
            {
                "is_math_figure": True,
                "belongs_to_solution_step": False,
                "dominant_content": "math_figure",
                "figure_box_w1000": [0, 0, 1000, 1000],
                "confidence": "low",
                "reason": "看不出属于第20题",
            },
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=[
            {"question_number": 20, "stem": "", "solution_steps": ["如图。"]}
        ],
        page_size=(2000, 1000),
        role="solution",
    )

    assert result.boxes == {}
    assert "看不出属于第20题" in result.review_notes[20][0]


def test_same_solution_box_cannot_be_assigned_to_two_steps(tmp_path: Path) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 20,
                        "solution_step_index": 0,
                        "nearest_question_anchor": "20．",
                        "nearest_solution_anchor": "（1）",
                        "box_w1000": [100, 100, 350, 350],
                    },
                    {
                        "question_number": 20,
                        "solution_step_index": 1,
                        "nearest_question_anchor": "20．",
                        "nearest_solution_anchor": "（2）",
                        "box_w1000": [100, 100, 350, 350],
                    },
                ],
            }
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=[
            {"question_number": 20, "stem": "", "solution_steps": ["一", "二"]}
        ],
        page_size=(2000, 1000),
        role="solution",
    )

    assert result.boxes == {}
    assert "多个解答步骤" in result.review_notes[20][0]
    assert len(client.calls) == 1


def test_figure_content_passes_even_when_completeness_is_over_cautious(
    tmp_path: Path,
) -> None:
    client = _FakeClient(
        [
            {
                "coordinate_system": "width_normalized_1000",
                "figures": [
                    {
                        "question_number": 18,
                        "nearest_question_anchor": "第18题图",
                        "box_w1000": [600, 100, 800, 400],
                    }
                ],
            },
            {
                "is_math_figure": True,
                # Neighbouring text can make the provider over-cautious about
                # completeness; attachment gates on the figure-content check.
                "is_complete": False,
                "clipped_edges": ["left"],
                "dominant_content": "math_figure",
                "figure_box_w1000": [0, 0, 1000, 1000],
                "confidence": "high",
                "reason": "主体是完整图形，左侧邻近题干被截断",
            },
        ]
    )

    result = FigureDetector(client=client).detect(
        _page(tmp_path),
        page_sha256="sha256:test",
        questions=_questions(18),
        page_size=(2000, 1000),
    )

    assert result.boxes == {18: [[900, 0, 1900, 1000]]}
    assert result.review_notes == {}
    assert len(client.calls) == 2


def test_clipped_figure_line_is_expanded_only_within_validation_crop(
    tmp_path: Path,
) -> None:
    page = tmp_path / "line-cut-by-model-box.png"
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.line((200, 80, 200, 220), fill="black", width=3)
    image.save(page)

    expanded = _expand_clipped_ink(
        page,
        [150, 70, 250, 140],
        [100, 40, 300, 260],
        (400, 300),
    )

    assert expanded[3] >= 220
    assert expanded[3] <= 260
    assert expanded[0] >= 100
    assert expanded[2] <= 300
