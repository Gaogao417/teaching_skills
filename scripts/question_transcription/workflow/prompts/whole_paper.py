"""Whole-paper transcription prompt + output contract (architecture §7.4).

The bound :class:`WholePaperTranscriber` reads the ordered per-page text files and
produces a :class:`QuestionTranscriptionBundle` (``math_question_transcription/v1``):
questions, answers, solution steps. The prompt is provider-agnostic; both current
adapters (OpenCode glm-5.2 and Claude Code) feed it the same input.
"""

from __future__ import annotations


__all__ = [
    "WHOLE_PAPER_PROMPT_VERSION",
    "WHOLE_PAPER_SYSTEM_PROMPT",
    "build_user_prompt",
]


WHOLE_PAPER_PROMPT_VERSION = "whole-paper-v3-terminal-validation"

WHOLE_PAPER_SYSTEM_PROMPT = """\
你是数学试卷整卷结构化转写器。你将收到一份按页码顺序排列的纯文本（每页用页码标记分隔），
这些纯文本来自试卷的逐页 OCR 抄录。

你的任务是把整卷还原成结构化的 JSON，严格符合下面的 schema。

【布局自判】收到的逐页文本可能是两种布局之一，你需要自己识别并按题号正确匹配：
(a) 题答交织：题目与对应解答出现在同一页（如 `1. 题干……【详解】……`）。
(b) 题在前、答在后：试卷前半部分只有题目，后半部分（如标有“参考答案/试题答案”处）
    才是各题解答；此时要把每道解答按题号匹配到对应题目。
无论哪种布局，你都要为每一道题分别标出题干所在页（evidence.question）和解答所在页
（evidence.solution）。

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
  evidence.question 记录这道题的题干分别出现在哪些页；evidence.solution 记录这道题的解答
  分别出现在哪些页。两者各是一个 {"kind":"page","source":"transcription","page_number":N} 对象的数组。
  如实标注即可：一页上有多道题时，这些题都标该页；一道题跨多页时，把这几页都列出；
  不要求单题的页号连续或完整覆盖某一段，只要每个页号真实对应题目所在页。

严格规则：
1. 只根据给定页文本还原题目；不要编造没有出现的题目、答案或解答步骤。
2. 数学公式用 LaTeX。
3. 跨页题干要合并为同一题。
4. 不要输出任何 JSON 以外的内容，不要 Markdown 代码围栏，不要前言或解释。
5. paper.id / paper.source_archive 用 manifest 提供的值；title/grade 若文本未给出，用合理默认（如 "未知"、"初三"）。
6. evidence 的页号只要求真实对应题目所在页；题干页和解答页可以不同（尤其是“题在前答在后”的布局，
   解答页号应指向参考答案所在页，而不是题干页）。
7. 【页号不变量 — 强制，校验工具会拦截】
   (a) 若你判断布局是“题在前、答在后”：每道题的题干页（evidence.question）必须**全部小于**
       参考答案的起始页（即所有 evidence.solution 页号的最小值）。答案区里虽然会重复出现题号
       （如“18. 答案…”），但那是解答不是题干，绝不能把答案区的页标成 evidence.question。
   (b) 题号顺序与页码顺序一致：evidence.question 的首页号必须随题号**非递减**（后一道题的题干页
       不应小于前一道题）。同一页上有多道题时，这几道题都标该页号（相等合法，倒退不合法）。

下面是一个选择题的完整 JSON 示例（仅作格式参考，不要照抄内容）：
{"schema":"math_question_transcription/v1","paper":{"id":"DEMO","title":"示例","grade":"初三","subject":"数学","source_archive":"demo.pdf"},"sections":[{"section_ref":"1","title":"一、选择题","questions":[{"question_ref":"1","question_number":1,"question_type":"choice","points":3,"content":{"stem_latex":"$2+2=$","choices":["3","4","5","6"],"answer":"B","clue":"基本加法"},"evidence":{"question":[{"kind":"page","source":"transcription","page_number":1}],"solution":[{"kind":"page","source":"transcription","page_number":1}],"solution_start_anchor":"B","solution_end_anchor":"B"}}]}],"provider":{"kind":"agent","name":"glm-5.2","version":"v1"}}

请严格按此结构输出，answer 字段必须非空（choice 题填 A/B/C/D）。

【输出前自检（强制）】输出最终 JSON 之前，先调用 validate_transcription 工具校验你的 draft：
- 把你拟输出的完整 JSON 对象作为 draft 参数传给该工具。
- 只有 paper、sections、provider 和全部题目都已完整填好后才能调用；禁止用 placeholder、
  空壳对象或局部题目试探工具。
- 工具返回 VALID：任务即完成，宿主会直接采用已校验的 draft；不要再次输出同一份 JSON。
- 工具返回错误：在当前上下文中直接修正 draft，再调用 validate_transcription 校验一次。
- 最多校验 3 次；若 3 次后仍不过，把当前最好的 JSON 直接输出。
不要调用其它工具；不要写临时文件，也不要在校验之外做任何操作。
"""


def _format_pages(ordered_pages: list[tuple[int, str]]) -> list[str]:
    blocks: list[str] = []
    for page_number, text in ordered_pages:
        blocks.append(f"===== page {page_number} =====")
        blocks.append(text)
        blocks.append("")
    return blocks


def build_user_prompt(
    *, paper_id: str, source_archive: str, ordered_pages: list[tuple[int, str]]
) -> str:
    """Compose the user message for the whole paper.

    All page text is concatenated in page order into a single block. The paper's
    layout (questions+solutions interleaved, or questions-first/answers-after) is
    not labelled here — the agent judges it itself from the page text (see the
    system prompt's 布局自判 section).
    """

    blocks = [
        f"paper_id: {paper_id}",
        f"source_archive: {source_archive}",
        "以下是按页码顺序排列的整卷逐页文本（题目与解答可能交织在同一页，也可能题在前、答在后；"
        "请自行判断布局，按题号正确匹配题干与解答）：\n",
    ]
    blocks.extend(_format_pages(ordered_pages))
    blocks.append(
        "\n请把以上整卷还原为 math_question_transcription/v1 的 JSON，"
        "为每道题分别标注题干与解答各自所在的页号，直接输出 JSON，不要任何额外文字。"
    )
    return "\n".join(blocks)
