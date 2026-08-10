"""In-process ``validate_transcription`` MCP tool for the whole-paper transcriber.

The Claude Code transcriber route exposes this as a single constrained tool the
agent calls to validate its draft JSON against the authoritative
:class:`QuestionTranscriptionBundle` schema, instead of giving the agent a free
``Bash`` tool to run the validator itself (which induced long multi-turn
"write a script / run it / read it back" loops).

It is wired ONLY into the Claude Code path (architecture §3.2): the SDK's
``create_sdk_mcp_server`` builds an in-process MCP server (no subprocess, no
IPC) that the ``claude`` CLI can call as the ``validate_transcription`` tool.
The OpenCode path is untouched (it relies on PydanticAI's ``output_type``
structured-output validation + ``ModelRetry``).

``claude_agent_sdk`` is imported lazily inside :func:`build_validate_mcp_server`
so importing this module never loads the SDK (offline tests stay network-free),
mirroring :mod:`scripts.infrastructure.ai.claude_code.client`.

Beyond the Pydantic schema, :func:`check_page_number_invariants` enforces two
semantic invariants on the evidence page numbers that the schema alone cannot
catch (see A-outlier precheck report). They make the validator reject the two
most common whole-paper transcription failures *before* the draft reaches
``word_evidence_pages.resolve_draft_payload``, so the agent can self-correct
within its 3 validation retries instead of producing a draft that later
expands into a 300-page evidence list:

1. **separated layout (题前答后)**: every question page must precede the first
   solution page. A question seed at or past ``min(solution_pages)`` is an
   answer-block mis-recording (the agent saw the question number re-mentioned
   in the answer section and tagged that page).
2. **monotonic question order**: question page seeds must be non-decreasing in
   paper order. A single dip (Q004=p1 after Q003=p2) is an unstable tie-break
   on same-page multi-question mapping.

Both invariants are layout-aware: an interleaved paper (题答交织) legitimately
has each question on the same page as its own solution, so only the separated
case enforces the question-before-solution-block rule. The layout is inferred
the same way ``word_evidence_pages.infer_layout`` does it, from whether the
first solution page is page 1.
"""

from __future__ import annotations

from typing import Any


__all__ = ["build_validate_mcp_server", "validate_transcription_handler", "check_page_number_invariants"]


async def validate_transcription_handler(args: dict[str, Any]) -> dict[str, Any]:
    """Validate ``args["draft"]`` against ``QuestionTranscriptionBundle``.

    Returns an MCP tool-result dict: ``VALID`` + a short summary on success, or
    the full pydantic ``ValidationError`` text with ``is_error: True`` on failure.
    Callable directly from tests (no SDK required).
    """
    from scripts.question_transcription.contracts import (
        QuestionTranscriptionBundle,
    )
    from pydantic import ValidationError

    draft = args.get("draft")
    if not isinstance(draft, dict):
        return {
            "content": [{"type": "text", "text":
                "validate_transcription: 'draft' 必须是一个 JSON 对象。"}],
            "is_error": True,
        }
    try:
        bundle = QuestionTranscriptionBundle.model_validate(draft)
    except ValidationError as exc:
        return {
            "content": [{"type": "text", "text": str(exc)}],
            "is_error": True,
        }

    # Semantic page-number invariants (see module docstring). These catch the
    # two whole-paper transcription failures that the schema cannot: answer-block
    # question seeds and non-monotonic question ordering. Surface them as retry
    # errors so the agent self-corrects before emitting the final JSON.
    invariant_errors = check_page_number_invariants(bundle)
    if invariant_errors:
        joined = "\n".join(f"- {e}" for e in invariant_errors)
        return {
            "content": [{"type": "text", "text":
                "页号语义校验失败（evidence 页号不合理）：\n" + joined +
                "\n请修正 evidence.question / evidence.solution 的 page_number 后重新校验。"}],
            "is_error": True,
        }

    n_sections = len(bundle.sections)
    n_questions = sum(len(s.questions) for s in bundle.sections)
    return {
        "content": [{"type": "text", "text":
            f"VALID — {n_sections} 个 section，{n_questions} 道题。"
            "请立即把校验通过的 draft JSON 作为最终回复输出。"}],
    }


def check_page_number_invariants(bundle: Any) -> list[str]:
    """Return a list of human-readable page-number invariant violations.

    Empty list = pass. Two checks, both layout-aware:

    1. **separated layout (题前答后)**: when the first solution page is not
       page 1, the paper is "questions first, answers after", and every
       question page must stay before the answer block. A question seed at or
       past ``min(solution_pages)`` is the agent recording the answer-block
       re-mention of the question number as its question page (the A1 outlier
       pattern from the evidence precheck: 5 papers had 8-22 trailing
       questions whose only evidence page was the answer page).
    2. **question order monotonicity (both layouts)**: question page seeds must
       be non-decreasing in paper order. A dip (Q004=p1 after Q003=p2) is the
       unstable same-page tie-break (the A2 pattern: 7 papers had 1-2 such
       inversions among the first few questions).

    Layout is inferred from the first solution page the same way
    ``word_evidence_pages.infer_layout`` does it: solution starting at page 1
    means interleaved (题答交织), anything later means separated. Interleaved
    papers are *not* checked against rule 1 because a question legitimately
    shares its page with its own solution.
    """
    questions = [q for section in bundle.sections for q in section.questions]
    if len(questions) < 2:
        return []  # a single question has no ordering to violate

    question_starts: list[int] = []
    solution_starts: list[int] = []
    for q in questions:
        q_pages = [ref.page_number for ref in q.evidence.question]
        s_pages = [ref.page_number for ref in q.evidence.solution]
        if not q_pages or not s_pages:
            continue  # schema requires non-empty, but guard defensively
        question_starts.append(min(q_pages))
        solution_starts.append(min(s_pages))

    if len(question_starts) < 2:
        return []

    errors: list[str] = []
    first_solution_page = min(solution_starts)

    # Rule 1: separated layout — no question page may reach the answer block.
    # Interleaved (solution starts at page 1) is exempt: q and s legitimately
    # share page 1.
    is_separated = first_solution_page > 1
    if is_separated:
        for index, (q, q_page) in enumerate(zip(questions, question_starts)):
            if q_page >= first_solution_page:
                errors.append(
                    f"题 {q.question_ref}: evidence.question 首页 p{q_page} 已进入答案区"
                    f"（答案从 p{first_solution_page} 起）。题在前答在后的布局下，题干页"
                    f"必须全部在答案区之前；该题的题干页应小于 p{first_solution_page}，"
                    "不要把答案区里重复出现的题号页标成题干页。"
                )

    # Rule 2: question page seeds must be non-decreasing (both layouts). Same-page
    # multi-question mapping is fine (equal), but a backwards dip is a tie-break
    # instability. Skip an entry that rule 1 already flagged so the agent gets one
    # clear message per broken question.
    for index in range(1, len(question_starts)):
        prev_ref = questions[index - 1].question_ref
        curr_ref = questions[index].question_ref
        if question_starts[index] < question_starts[index - 1]:
            errors.append(
                f"题 {curr_ref}: evidence.question 首页 p{question_starts[index]} "
                f"小于上一题 {prev_ref} 的 p{question_starts[index - 1]}，"
                "题号顺序应与页码顺序一致（非递减）。同页多道题请标同一页号。"
            )

    return errors


def build_validate_mcp_server():
    """Build the in-process MCP server exposing ``validate_transcription``.

    Returns the ``McpSdkServerConfig`` produced by
    ``claude_agent_sdk.create_sdk_mcp_server``; pass it as one entry of
    ``ClaudeAgentOptions(mcp_servers={"validator": <this>}, ...)`` and list
    ``"validate_transcription"`` in ``allowed_tools``.
    """
    from claude_agent_sdk import create_sdk_mcp_server, tool

    validate_transcription = tool(
        "validate_transcription",
        "校验整卷转录 JSON 是否符合 math_question_transcription/v1 schema。"
        "传入你拟输出的完整 JSON 对象（draft）；返回 VALID 表示通过，"
        "返回错误时按错误文本修正后再校验。",
        {"draft": dict},
    )(validate_transcription_handler)

    return create_sdk_mcp_server(
        "transcription-validator", tools=[validate_transcription]
    )
