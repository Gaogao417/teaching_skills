"""Shared rules for mandatory visual figure checks on geometry long problems."""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal


FIGURE_REFERENCE = re.compile(r"如图|图所示|下图|上图|图中|示意图")

# This is intentionally a broad, deterministic classifier.  A false positive only
# costs one visual inspection; a false negative can silently drop a required diagram.
GEOMETRY_LONG_PROBLEM_SIGNAL = re.compile(
    r"\\(?:triangle|angle|perp|parallel|odot|arc|overarc)\b"
    r"|[△∠⊥∥⊙]"
    r"|三角形|四边形|平行四边形|矩形|菱形|正方形|梯形"
    r"|圆心|半径|直径|弦|切线|圆周角|相似|全等|角平分线"
    r"|垂足|中点|延长线|射线|线段|平面直角坐标系|坐标系|抛物线"
)

PROMPT_NO_FIGURE_VISUAL_CHECK_NOTE = (
    "geometry_visual_check:prompt:no_independent_figure"
)
SOLUTION_NO_FIGURE_VISUAL_CHECK_NOTE = (
    "geometry_visual_check:solution:no_independent_figure"
)


def mentions_figure(text: Any) -> bool:
    """Whether text explicitly refers to a concrete figure."""

    return bool(FIGURE_REFERENCE.search(str(text or "")))


def is_geometry_long_problem(
    question_type: Any,
    stem: Any,
    solution_steps: Iterable[Any] | None = None,
) -> bool:
    """Return whether a long-answer item must receive prompt+solution visual checks."""

    if str(question_type or "") not in {"problem", "short_answer"}:
        return False
    text = "\n".join(
        [str(stem or ""), *(str(step or "") for step in (solution_steps or []))]
    )
    return bool(GEOMETRY_LONG_PROBLEM_SIGNAL.search(text))


def no_figure_visual_check_note(role: Literal["prompt", "solution"]) -> str:
    return (
        PROMPT_NO_FIGURE_VISUAL_CHECK_NOTE
        if role == "prompt"
        else SOLUTION_NO_FIGURE_VISUAL_CHECK_NOTE
    )
