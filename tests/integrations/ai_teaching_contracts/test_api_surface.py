"""退出门禁 2：Approved version 不存在原地更新 API（adapter 层就不提供）。

结构性自证：枚举整个包的公开 API，逐一对照白名单。白名单里没有任何
mutation 语义的入口；新增公开函数必须先改这里的 ALLOWED_API（评审时
白名单 diff 即审查点）。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import integrations.ai_teaching_contracts as pkg  # noqa: E402
from integrations.ai_teaching_contracts import artifact_uri, models, publication, validation  # noqa: E402

ALLOWED_API = frozenset(
    {
        # __init__ 再导出
        "ArtifactUri",
        "ArtifactUriError",
        "LocalArtifactResolver",
        "PublicationError",
        "SchemaKind",
        "canonical_schema_for",
        "parse_artifact_uri",
        "resolver_from_env",
        "validate_for_publication",
        "validate_payload",
    }
)

MUTATION_NAME_FRAGMENTS = (
    "update",
    "patch",
    "mutate",
    "overwrite",
    "replace",
    "edit",
    "delete",
    "remove",
    "save",
    "write",
    "set_",
    "in_place",
    "inplace",
)


def test_package_public_api_is_exactly_the_whitelist():
    assert set(pkg.__all__) == ALLOWED_API, set(pkg.__all__) ^ ALLOWED_API
    submodules = {"artifact_uri", "publication", "validation", "models", "annotations"}
    public = {
        name
        for name in dir(pkg)
        if not name.startswith("_") and name not in submodules
    }
    assert public == ALLOWED_API, public ^ ALLOWED_API


def _public_callables(module) -> dict[str, object]:
    return {
        name: obj
        for name, obj in vars(module).items()
        if not name.startswith("_") and callable(obj) and getattr(obj, "__module__", None) == module.__name__
    }


def test_no_module_exports_mutation_semantics():
    for module in (artifact_uri, validation, publication):
        for name, obj in _public_callables(module).items():
            lowered = name.lower()
            assert not any(frag in lowered for frag in MUTATION_NAME_FRAGMENTS), (
                f"{module.__name__}.{name} 疑似原地更新 API（ADR-004 §3：Approved 后只允许新建 version）"
            )


def test_models_module_defines_no_own_functions():
    own = {
        name: obj
        for name, obj in vars(models).items()
        if inspect.isfunction(obj)
        and getattr(obj, "__module__", None) == models.__name__
    }
    # models.py 只允许模型类与类型别名；自身不定义任何函数（pydantic 导入除外）
    assert not own, own


def test_validate_payload_returns_outcome_not_mutated_payload():
    # validate 入口不回写、不规范化调用方对象（不可变语义从入口开始）
    import copy

    payload = {
        "schema": "ai_teaching_question_truth/v1",
        "status": "Draft",
    }
    snapshot = copy.deepcopy(payload)
    validation.validate_payload(payload)
    assert payload == snapshot
