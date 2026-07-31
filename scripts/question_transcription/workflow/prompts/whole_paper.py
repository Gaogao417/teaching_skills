"""Whole-paper transcription prompt + output contract (architecture §7.4).

The bound :class:`WholePaperTranscriber` reads the ordered per-page text files and
produces a :class:`QuestionTranscriptionBundle` (``math_question_transcription/v1``):
questions, answers, solution steps. The prompt is provider-agnostic; both current
adapters (OpenCode glm-5.2 and Claude Code) feed it the same input.
"""

from __future__ import annotations

import typing


__all__ = [
    "WHOLE_PAPER_PROMPT_VERSION",
    "WHOLE_PAPER_SYSTEM_PROMPT",
    "PromptMode",
    "build_user_prompt",
    "build_interleaved_prompt",
    "build_separated_prompt",
]


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

下面是一个选择题的完整 JSON 示例（仅作格式参考，不要照抄内容）：
{"schema":"math_question_transcription/v1","paper":{"id":"DEMO","title":"示例","grade":"初三","subject":"数学","source_archive":"demo.pdf"},"sections":[{"section_ref":"1","title":"一、选择题","questions":[{"question_ref":"1","question_number":1,"question_type":"choice","points":3,"content":{"stem_latex":"$2+2=$","choices":["3","4","5","6"],"answer":"B","clue":"基本加法"},"evidence":{"question":[{"kind":"page","source":"transcription","page_number":1}],"solution":[{"kind":"page","source":"transcription","page_number":1}],"solution_start_anchor":"B","solution_end_anchor":"B"}}]}],"provider":{"kind":"agent","name":"glm-5.2","version":"v1"}}

请严格按此结构输出，answer 字段必须非空（choice 题填 A/B/C/D）。
"""


PromptMode = typing.Literal["interleaved", "separated"]
"""
How the paper's questions and solutions are laid out across the page text:

- ``interleaved`` — questions and their solutions are interleaved on the same pages
  (e.g. ``1. 题干... 【详解】...``). One ordered page list covers the whole paper.
- ``separated`` — the question paper and the answer/solution file are separate
  (e.g. a question-only卷 and an answer-only参考答案). Two ordered page lists are
  provided: question pages and solution pages. The model must match each solution
  to its question by question number.
"""


def _format_pages(label: str, ordered_pages: list[tuple[int, str]]) -> list[str]:
    blocks = [f"----- {label} -----"]
    for page_number, text in ordered_pages:
        blocks.append(f"===== page {page_number} =====")
        blocks.append(text)
        blocks.append("")
    return blocks


def build_interleaved_prompt(
    *, paper_id: str, source_archive: str, ordered_pages: list[tuple[int, str]]
) -> str:
    """Compose the user message for an interleaved paper (questions + solutions together)."""

    blocks = [
        f"paper_id: {paper_id}",
        f"source_archive: {source_archive}",
        "本卷题目与解答在同一批页面中交织出现。以下是按页码顺序排列的整卷逐页文本：\n",
    ]
    blocks.extend(_format_pages("整卷（题题与解答交织）", ordered_pages))
    blocks.append(
        "\n请把以上整卷还原为 math_question_transcription/v1 的 JSON，"
        "每道题的 answer 与 solution_steps 从同一批页面的解答部分提取，"
        "直接输出 JSON，不要任何额外文字。"
    )
    return "\n".join(blocks)


def build_separated_prompt(
    *,
    paper_id: str,
    source_archive: str,
    question_pages: list[tuple[int, str]],
    solution_pages: list[tuple[int, str]],
) -> str:
    """Compose the user message for a separated paper (题卷 + 答案分文件).

    ``question_pages`` are the question-only pages; ``solution_pages`` are the
    answer/solution-only pages. The model matches each solution to its question by
    question number and merges them into one paper.
    """

    blocks = [
        f"paper_id: {paper_id}",
        f"source_archive: {source_archive}",
        "本卷题目与解答分别在不同文件/页面：先给出【题卷】逐页文本，再给出【参考答案】逐页文本。"
        "请把每道解答按题号匹配到对应题目，合并成一份完整的 math_question_transcription/v1。"
        "题号在题卷和答案中应一致（如 `1．`、`18.`）。\n",
    ]
    blocks.extend(_format_pages("题卷（仅题目）", question_pages))
    blocks.append("")
    blocks.extend(_format_pages("参考答案（仅解答）", solution_pages))
    blocks.append(
        "\n请把以上题卷与答案合并还原为 math_question_transcription/v1 的 JSON，"
        "每道题的 answer / solution_steps 取自参考答案，题干取自题卷，"
        "直接输出 JSON，不要任何额外文字。"
    )
    return "\n".join(blocks)


def build_user_prompt(
    *,
    paper_id: str,
    source_archive: str,
    ordered_pages: list[tuple[int, str]] | None = None,
    question_pages: list[tuple[int, str]] | None = None,
    solution_pages: list[tuple[int, str]] | None = None,
    mode: PromptMode = "interleaved",
) -> str:
    """Dispatch to the interleaved or separated prompt builder.

    - ``mode="interleaved"`` (default): uses ``ordered_pages``.
    - ``mode="separated"``: uses ``question_pages`` + ``solution_pages``.
    """

    if mode == "separated":
        return build_separated_prompt(
            paper_id=paper_id,
            source_archive=source_archive,
            question_pages=question_pages or [],
            solution_pages=solution_pages or [],
        )
    return build_interleaved_prompt(
        paper_id=paper_id,
        source_archive=source_archive,
        ordered_pages=ordered_pages or [],
    )
