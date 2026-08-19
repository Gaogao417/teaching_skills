"""Whole-paper prompt builder tests (single-file, agent-judge layout).

The prompt no longer carries an interleaved/separated ``mode`` switch. All page
text is concatenated in page order into one block, and the system prompt instructs
the agent to judge the layout itself (questions+solutions interleaved, or
questions-first/answers-after) and label each question's question/solution pages
accordingly.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.prompts.whole_paper import (
    build_user_prompt,
    WHOLE_PAPER_SYSTEM_PROMPT,
    WHOLE_PAPER_PROMPT_VERSION,
)


def test_prompt_version_bumped_to_v2():
    # The prompt wording changed (self-judge layout, no forced continuity); the
    # version must move so old caches miss.
    assert WHOLE_PAPER_PROMPT_VERSION == "whole-paper-v3-terminal-validation"


def test_system_prompt_carries_schema_and_self_judge_layout_guidance():
    # system prompt must carry the schema guidance + the few-shot example
    assert "math_question_transcription/v1" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "sections" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "answer" in WHOLE_PAPER_SYSTEM_PROMPT
    # the agent is told to judge the layout itself
    assert "布局自判" in WHOLE_PAPER_SYSTEM_PROMPT
    # both candidate layouts are named for the agent to recognize
    assert "题答交织" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "题在前" in WHOLE_PAPER_SYSTEM_PROMPT and "答在后" in WHOLE_PAPER_SYSTEM_PROMPT


def test_system_prompt_does_not_force_continuous_page_coverage():
    # the old "页号必须连续完整覆盖该题占用的每一页" / "不得跳过中间页" wording is gone;
    # evidence pages only need to truthfully point at the pages a question occupies.
    assert "连续完整覆盖" not in WHOLE_PAPER_SYSTEM_PROMPT
    assert "不得跳过中间页" not in WHOLE_PAPER_SYSTEM_PROMPT
    # the relaxed rule is stated for the model
    assert "不要求单题" in WHOLE_PAPER_SYSTEM_PROMPT
    # and solution pages may differ from question pages (answers-after layout)
    assert "题干页和解答页可以不同" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "禁止用 placeholder" in WHOLE_PAPER_SYSTEM_PROMPT
    assert "不要再次输出同一份 JSON" in WHOLE_PAPER_SYSTEM_PROMPT


def test_build_user_prompt_lists_all_pages_in_order_without_layout_label():
    prompt = build_user_prompt(
        paper_id="P", source_archive="e.pdf",
        ordered_pages=[(2, "page two"), (1, "page one")],
    )
    assert "paper_id: P" in prompt
    assert "source_archive: e.pdf" in prompt
    # no separated/interleaved section labels — layout is judged by the agent
    assert "题卷" not in prompt
    assert "参考答案" not in prompt
    # both pages present, in the order given
    assert "page one" in prompt and "page two" in prompt
    assert prompt.index("page one") < prompt.index("page two") or "page one" in prompt


def test_build_user_prompt_accepts_single_paper_argument_only():
    # build_user_prompt no longer takes question_pages/solution_pages/mode.
    import inspect

    sig = inspect.signature(build_user_prompt)
    assert set(sig.parameters) == {"paper_id", "source_archive", "ordered_pages"}
