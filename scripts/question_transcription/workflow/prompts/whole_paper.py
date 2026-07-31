"""Whole-paper transcription prompt + output contract (ports-design §7, design §2.3).

The bound :class:`WholePaperTranscriber` reads the ordered per-page text files and
produces a :class:`QuestionTranscriptionBundle` (``math_question_transcription/v1``):
questions, answers, solution steps. The prompt is provider-agnostic; all three
adapters (OpenCode glm-5.2 / Claude Code / direct GLM API) feed it the same input.
"""

from __future__ import annotations


__all__ = ["WHOLE_PAPER_PROMPT_VERSION", "WHOLE_PAPER_SYSTEM_PROMPT", "build_user_prompt"]


WHOLE_PAPER_PROMPT_VERSION = "whole-paper-v1"

WHOLE_PAPER_SYSTEM_PROMPT = """\
你是数学试卷整卷结构化转写器。你将收到一份按页码顺序排列的纯文本（每页用页码标记分隔），
这些纯文本来自试卷的逐页 OCR 抄录。

你的任务是把整卷还原成结构化的 JSON，严格符合下面的 schema。

输出 JSON 必须有以下顶层字段，缺一不可：
- "schema": 固定字符串 "math_question_transcription/v1"
- "paper": 对象，包含 "id"、"title"、"grade"、"subject"（默认"数学"）、"source_archive"
- "sections": 数组，每个元素是 {"section_ref": "1", "title": "...", "questions": [ ... ]}
- "provider": 固定 {"kind":"agent","name":"glm-5.2","version":"v1"}

题目放在 sections[].questions[] 里，不要把 questions 放在顶层。每道题必须有：
- "question_ref"（题号字符串，如 "1"、"18"）
- "question_number"（整数）
- "question_type"（choice / fillin / problem / short_answer 之一）
- "points"（整数分值）
- "content": 包含 "stem_latex"（题干 LaTeX）、"answer"、"clue"，以及
  - choice 题：恰好 4 个 "choices" 字符串，answer 必须是 "A"/"B"/"C"/"D" 之一
  - problem/short_answer 题：非空 "solution_steps" 字符串数组（按原卷解答顺序）
- "evidence": {"question": [...], "solution": [...], "solution_start_anchor": "...", "solution_end_anchor": "..."}

严格规则：
1. 只根据给定页文本还原题目；不要编造没有出现的题目、答案或解答步骤。
2. 数学公式用 LaTeX。
3. 跨页题干要合并为同一题。
4. 不要输出任何 JSON 以外的内容，不要 Markdown 代码围栏，不要前言或解释。
5. paper.id / paper.source_archive 用 manifest 提供的值；title/grade 若文本未给出，用合理默认（如 "未知"、"初三"）。
"""


def build_user_prompt(*, paper_id: str, source_archive: str, ordered_pages: list[tuple[int, str]]) -> str:
    """Compose the user message: paper metadata + ordered page text."""

    blocks = []
    blocks.append(f"paper_id: {paper_id}")
    blocks.append(f"source_archive: {source_archive}")
    blocks.append("以下是按页码顺序排列的整卷逐页文本：\n")
    for page_number, text in ordered_pages:
        blocks.append(f"===== page {page_number} =====")
        blocks.append(text)
        blocks.append("")
    blocks.append(
        "\n请把以上整卷还原为 math_question_transcription/v1 的 JSON，"
        "直接输出 JSON，不要任何额外文字。"
    )
    return "\n".join(blocks)
