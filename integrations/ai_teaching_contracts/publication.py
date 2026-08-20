"""publication 校验（Phase 1 退出门禁 3，fail closed）。

发布管线在写入 registry 前必须调用 ``validate_for_publication``；非空
error 列表即拒绝。规则：
1. 只有 Approved 状态的对象可发布（Draft/InReview/Stale/Disabled/Superseded 拒绝）；
2. canonical 对象内任何字符串不得是绝对本地路径或 file:// URI（ADR-002 禁止事项）。
"""
from __future__ import annotations

import re
from typing import Iterable

# 允许走 publication 校验的对象类型（authoring/planning 可发布 artifact；
# v2 为 ADR-005 小问粒度版本，approach-set 为其组合层；
# Phase 4 起 +teaching_approach/v3 与 tutor_plan_bundle/v2（ADR-006 资源包））。
PUBLISHABLE_SCHEMAS = frozenset(
    {
        "ai_teaching_question_truth/v1",
        "ai_teaching_question_truth/v2",
        "ai_teaching_teaching_approach/v1",
        "ai_teaching_teaching_approach/v2",
        "ai_teaching_teaching_approach/v3",
        "ai_teaching_approach_set/v1",
        "ai_teaching_tutor_plan_bundle/v1",
        "ai_teaching_tutor_plan_bundle/v2",
    }
)

NOT_PUBLISHED_STATUSES = frozenset(
    {"Draft", "InReview", "Stale", "Disabled", "Superseded"}
)

_UNIX_ABS = re.compile(r"(?<![A-Za-z0-9])/(?:Users|home|Volumes|tmp|var|opt|etc|private)/")
_WIN_ABS = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\")
_FILE_SCHEME = "file://"


class PublicationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _iter_strings(node: object) -> Iterable[tuple[str, str]]:
    if isinstance(node, str):
        yield ("", node)
    elif isinstance(node, dict):
        for key, value in node.items():
            for where, s in _iter_strings(value):
                yield (f"{key}.{where}" if where else key, s)
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            for where, s in _iter_strings(value):
                yield (f"[{index}].{where}" if where else f"[{index}]", s)


def validate_for_publication(payload: dict) -> list[PublicationError]:
    """返回全部拒绝原因；空列表 = 可发布。非 dict 或缺 schema/status 视为不可发布。"""
    errors: list[PublicationError] = []
    if not isinstance(payload, dict):
        return [PublicationError("not_a_canonical_object", type(payload).__name__)]
    schema = payload.get("schema")
    status = payload.get("status")
    if schema not in PUBLISHABLE_SCHEMAS:
        errors.append(PublicationError("not_publishable_type", str(schema)))
        return errors
    if status in NOT_PUBLISHED_STATUSES or status != "Approved":
        errors.append(PublicationError("not_approved", str(status)))
    for where, value in _iter_strings(payload):
        reason = _absolute_path_reason(value)
        if reason:
            errors.append(PublicationError("absolute_local_path", f"{where}: {reason}"))
    return errors


def _absolute_path_reason(value: str) -> str | None:
    if _FILE_SCHEME in value:
        return "file:// URI is forbidden in canonical artifacts"
    if _UNIX_ABS.search(value):
        return "absolute local path is forbidden in canonical artifacts"
    if _WIN_ABS.search(value):
        return "absolute windows path is forbidden in canonical artifacts"
    return None
