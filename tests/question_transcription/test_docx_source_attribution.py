"""Fail-fast regressions for DOCX paragraph-stream image attribution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCX_SCRIPTS = (
    ROOT / ".codex" / "skills" / "math-docx-question-bank-ingestion" / "scripts"
)
if str(DOCX_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(DOCX_SCRIPTS))

from extract_docx_source import attribute_images  # noqa: E402


def _paragraph(index: int, text: str, images: list[str] | None = None) -> dict:
    return {
        "index": index,
        "text": text,
        "images": images or [],
        "previous_text": "",
        "next_text": "",
    }


def test_attribute_images_aborts_when_question_numbering_jumps_forward():
    paragraphs = [
        _paragraph(0, "1. 第一题"),
        _paragraph(1, "2. 第二题"),
        # Q3 exists in the document but its paragraph starts with figure-caption
        # noise, so the strict question-number matcher cannot see it.
        _paragraph(2, "图2图13. 如图1，第三题", ["media/image3.png"]),
        _paragraph(3, "4. 第四题"),
    ]

    with pytest.raises(
        ValueError,
        match=r"state lost.*expected question 3, found question 4",
    ):
        attribute_images(paragraphs)


def test_attribute_images_still_ignores_backward_solution_step_numbers():
    paragraphs = [
        _paragraph(0, "1. 第一题"),
        _paragraph(1, "2. 第二题"),
        _paragraph(2, "1. 解答中的第一步"),
        _paragraph(3, "2. 解答中的第二步"),
        _paragraph(4, "3. 第三题", ["media/image3.png"]),
    ]

    attributions = attribute_images(paragraphs)

    assert any(
        item["media"] == "media/image3.png" and item["question_number"] == 3
        for item in attributions
    )


def test_real_baoshan_2024_aborts_instead_of_collapsing_images_into_q5():
    word_source = yaml.safe_load(
        (
            ROOT
            / "documents/初三/2024届-上海市宝山区-初三二模数学-试卷及解析"
            / "word/word-source.yaml"
        ).read_text(encoding="utf-8")
    )

    with pytest.raises(
        ValueError,
        match=r"state lost.*expected question 6, found question 7",
    ):
        attribute_images(word_source["paragraphs"])
