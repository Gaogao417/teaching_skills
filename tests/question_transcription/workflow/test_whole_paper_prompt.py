"""Whole-paper prompt builder tests (interleaved vs separated layouts).

Covers architecture §7.4 (题卷/答案分文件): the prompt must support
both an interleaved paper (questions + solutions on the same pages) and a separated
paper (question-only卷 + answer-only参考答案).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.prompts.whole_paper import (
    PromptMode,
    build_interleaved_prompt,
    build_separated_prompt,
    build_user_prompt,
    WHOLE_PAPER_SYSTEM_PROMPT,
    WHOLE_PAPER_PROMPT_VERSION,
)


def test_prompt_version_and_system_prompt_present():
    assert WHOLE_PAPER_PROMPT_VERSION == "whole-paper-v1"
    # system prompt must carry the schema guidance + the few-shot example
    assert "math_question_transcription/v1" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "sections" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "answer" in WHOLE_PAPER_SYSTEM_PROMPT


def test_interleaved_prompt_lists_all_pages_in_order():
    prompt = build_interleaved_prompt(
        paper_id="P", source_archive="e.pdf",
        ordered_pages=[(2, "page two"), (1, "page one")],
    )
    assert "paper_id: P" in prompt
    assert "source_archive: e.pdf" in prompt
    assert "交织" in prompt
    # both pages present
    assert "page one" in prompt and "page two" in prompt


def test_separated_prompt_has_question_and_solution_sections():
    prompt = build_separated_prompt(
        paper_id="P", source_archive="e.pdf",
        question_pages=[(1, "1. 求 x")],
        solution_pages=[(1, "1. 解: x=2")],
    )
    assert "题卷" in prompt
    assert "参考答案" in prompt
    assert "1. 求 x" in prompt
    assert "1. 解: x=2" in prompt
    # instructs the model to merge by question number
    assert "题号" in prompt


def test_dispatch_build_user_prompt_interleaved_default():
    prompt = build_user_prompt(
        paper_id="P", source_archive="e.pdf", ordered_pages=[(1, "q")],
    )
    assert "交织" in prompt


def test_dispatch_build_user_prompt_separated():
    prompt = build_user_prompt(
        paper_id="P", source_archive="e.pdf",
        question_pages=[(1, "q")], solution_pages=[(1, "a")],
        mode="separated",
    )
    assert "题卷" in prompt and "参考答案" in prompt


def test_prompt_mode_literal_values():
    # PromptMode is a Literal; the two valid values are the layouts.
    assert "interleaved" in typing_get_args(PromptMode)
    assert "separated" in typing_get_args(PromptMode)


def typing_get_args(tp):
    import typing

    return typing.get_args(tp)
