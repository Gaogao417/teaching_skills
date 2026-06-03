#!/usr/bin/env python3
"""
Agentic GeometricScene workflow.

The workflow accepts one teaching-oriented geometry request, asks an
OpenAI-compatible text model to write/revise a Wolfram GeometricScene,
solves it through Wolfram, compiles a renderer-friendly geometry spec, and
optionally renders/evaluates a debug image up to max_retries.

中文导览：
1. 入口请求先被归一化成 workflow 内部使用的扁平字段。
2. 文本模型生成 GeometricScene；solution 图会复用 prompt 图坐标，只追加辅助点/标记。
3. Wolfram 子进程负责求解，主进程用 hard timeout 防止 kernel 卡死。
4. 渲染结果会被编译成 renderer spec，并可交给视觉模型做可用性反馈。
5. 每一轮的产物都落在 rounds/round_N，最终产物落在输出目录根部。
"""

from __future__ import annotations

import argparse
import base64
import json
import multiprocessing as mp
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import (
    configure_utf8_stdio,
    project_root,
    redact_secrets,
    resolve_wolfram_kernel,
    wl_dir as resolve_wl_dir,
)

configure_utf8_stdio()

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised in environments without deps.
    OpenAI = None  # type: ignore[assignment]

try:
    from wolframclient.evaluation import WolframLanguageSession
    from wolframclient.language import Global, wl, wlexpr
except ImportError as exc:  # pragma: no cover
    WolframLanguageSession = None  # type: ignore[assignment]
    Global = None  # type: ignore[assignment]
    wl = None  # type: ignore[assignment]
    wlexpr = None  # type: ignore[assignment]
    WOLFRAM_IMPORT_ERROR = exc
else:
    WOLFRAM_IMPORT_ERROR = None


FORBIDDEN_WL_TOKENS = [
    "RunProcess",
    "StartProcess",
    "CreateFile",
    "DeleteFile",
    "DeleteDirectory",
    "RenameFile",
    "CopyFile",
    "Import[",
    "URLRead",
    "URLExecute",
    "Get[",
    "Put[",
    "<<",
]

SKILL_SETS = {
    "generate": [
        "wolfram-geometricscene-reference",
        "wolfram-schema-first-param-types",
        "dimensionless-constraints-library",
        "wolfram-python-integration-patterns",
        "windows-encoding-compatibility",
    ],
    "evaluate": [
        "human-rating-loop",
        "tool-output-standards",
    ],
    "finalize": [
        "agent-io-schema",
        "tool-output-standards",
    ],
}

DEFAULT_TEXT_MODELS = [
    "qwen3.5-plus",
    "qwen3.6-plus",
    "qwen3.6-flash",
    "qwen3.6-flash-2026-04-16",
    "qwen3.5-flash",
    "qwen3.5-flash-2026-02-23",
    "qwen3.5-35b-a3b",
    "qwen3.6-35b-a3b",
    "qwen3.5-122b-a10b",
    "qwen3.5-397b-a17b",
    "qwen3.6-27b",
    "qwen3.6-plus-2026-04-02",
    "qwen3.5-plus-2026-04-20",
    "qwen3.5-plus-2026-02-15",
    "deepseek-v4-flash",
]

DEFAULT_VISION_MODELS = [
    "qwen3.5-flash",
    "qwen3.6-flash",
    "qwen3.6-flash-2026-04-16",
    "qwen3.5-flash-2026-02-23",
    "qwen3.5-plus",
    "qwen3.6-plus",
    "qwen3.6-plus-2026-04-02",
    "qwen3.5-plus-2026-04-20",
    "qwen3.5-plus-2026-02-15",
    "qwen3.5-122b-a10b",
    "qwen3.5-35b-a3b",
    "qwen3.6-35b-a3b",
    "qwen3.5-397b-a17b",
    "qwen3.6-27b",
    "qwen3.6-max-preview",
]


class WorkflowState(TypedDict, total=False):
    """节点之间传递的最小状态包。

    这个文件目前没有真正接入 LangGraph，但 state 的字段刻意按节点输入/输出
    来组织，方便以后把下面几个 *_node 函数直接搬进图编排。
    """

    request: Dict[str, Any]
    out_dir: str
    round_index: int
    max_retries: int
    scene_payload: Dict[str, Any]
    render_result: Dict[str, Any]
    vision_result: Dict[str, Any]
    history: List[Dict[str, Any]]
    skills_context: Dict[str, str]
    status: str
    error: str


class ModelPoolError(RuntimeError):
    def __init__(self, role: str, attempts: List[Dict[str, Any]]):
        super().__init__(
            f"All {role} models failed: "
            + json.dumps(attempts, ensure_ascii=False, default=_json_default)
        )
        self.role = role
        self.attempts = attempts


def _json_default(value: Any) -> str:
    return str(value)


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("workflow request must be a JSON object")
    return data


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return _read_json(path)


def _compact_string_parts(*values: Any) -> str:
    return "\n".join(str(value).strip() for value in values if str(value or "").strip())


def _normalize_workflow_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize public request contracts to the flat runtime shape.

    The production teaching pipeline now sends DiagramJobRequest v2. Most of
    this workflow's generation/rendering helpers predate that contract and read
    flat fields such as problem_text, objects_hint, and model_config, so v2 is
    flattened once at the boundary.

    中文说明：
    外部 schema 是面向教学流水线的分层结构；本文件里很多函数仍按早期扁平字段
    读取配置。这里是唯一的适配边界，后续步骤都假定 request 已经被拍平。
    """
    if request.get("schema_version") != "diagram-job-request/v2":
        return request

    engine = str(request.get("engine") or "geometric_scene")
    diagram_kind = str(request.get("diagram_kind") or "synthetic_geometry")
    if engine != "geometric_scene":
        raise ValueError(f"unsupported diagram engine for geometry workflow: {engine}")
    if diagram_kind != "synthetic_geometry":
        raise ValueError(f"unsupported diagram_kind for geometry workflow: {diagram_kind}")

    problem_context = request.get("problem_context")
    if not isinstance(problem_context, dict):
        problem_context = {}
    semantic_constraints = request.get("semantic_constraints")
    if not isinstance(semantic_constraints, dict):
        semantic_constraints = {}
    visual_requirements = request.get("visual_requirements")
    if not isinstance(visual_requirements, dict):
        visual_requirements = {}
    reuse = request.get("reuse")
    if not isinstance(reuse, dict):
        reuse = {}
    engine_options = request.get("engine_options")
    if not isinstance(engine_options, dict):
        engine_options = {}

    model_config = (
        engine_options.get("engine_model_config")
        or engine_options.get("model_config")
        or {}
    )
    if not isinstance(model_config, dict):
        model_config = {}

    given_objects = _compact_list(semantic_constraints.get("given_objects"))
    given_constraints = _compact_list(semantic_constraints.get("given_constraints"))
    derived_constraints = _compact_list(semantic_constraints.get("derived_constraints"))

    normalized = dict(request)
    normalized.update(
        {
            "diagram_job_id": request.get("job_id", ""),
            "diagram_type": diagram_kind,
            "diagram_intent": diagram_kind,
            "teaching_diagram_intent": request.get("teaching_intent", ""),
            "diagram_variant": request.get("variant", "prompt"),
            "problem_text": _compact_string_parts(
                problem_context.get("stem_latex"),
                problem_context.get("subquestion_latex"),
                problem_context.get("source_problem_text"),
            ),
            "grade_or_topic": problem_context.get("grade_or_topic", ""),
            "objects_hint": {
                "points": given_objects,
                "segments": [],
                "curves": [],
                "constraints": [*given_constraints, *derived_constraints],
            },
            "teaching_focus": given_objects or given_constraints,
            "must_not_imply": _compact_list(semantic_constraints.get("clean_forbidden")),
            "solution_allowed_annotations": _compact_list(
                semantic_constraints.get("solution_allowed_annotations")
            ),
            "reuse_geometry_from": reuse.get("reuse_geometry_from", ""),
            "base_job_dir": reuse.get("base_job_dir", ""),
            "model_config": model_config,
            "max_retries": engine_options.get("max_retries", 3),
            "wolfram_timeout_s": engine_options.get("wolfram_timeout_s", 30),
            "wolfram_hard_timeout_s": engine_options.get("wolfram_hard_timeout_s", 60),
            "wolfram_render_image": False,
        }
    )
    if engine_options.get("seed") is not None:
        normalized["seed"] = engine_options["seed"]
    if visual_requirements.get("caption"):
        normalized["caption"] = visual_requirements["caption"]
    return normalized


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)


def _emit_event(out_dir: Path, event: str, **fields: Any) -> None:
    """写入 JSONL 事件，同时向 stderr 打一行机器可读日志。

    事件里可能包含模型错误或请求片段，所以写出前统一做一次脱敏。
    """

    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
        **fields,
    }
    redacted_payload = json.loads(
        json.dumps(payload, ensure_ascii=False, default=_json_default),
        parse_int=int,
        parse_float=float,
    )
    for key, value in list(redacted_payload.items()):
        if isinstance(value, str):
            redacted_payload[key] = redact_secrets(value)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "workflow_events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(redacted_payload, ensure_ascii=False, default=_json_default) + "\n")
    print(
        "GSB_EVENT " + json.dumps(redacted_payload, ensure_ascii=False, default=_json_default),
        file=sys.stderr,
        flush=True,
    )


def _project_root() -> Path:
    return project_root()


def _skills_root() -> Path:
    return _project_root() / ".opencode" / "skills"


def _read_skill(skill_name: str, max_chars: int = 9000) -> str:
    skill_path = _skills_root() / skill_name / "SKILL.md"
    if not skill_path.exists():
        return f"[missing skill: {skill_name}]"
    text = skill_path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[skill truncated for prompt budget]"


def load_skills_context() -> Dict[str, str]:
    """按生成、评估、收尾三类读取本地 skill 文档，供模型 prompt 使用。"""

    contexts: Dict[str, str] = {}
    for group, names in SKILL_SETS.items():
        parts = []
        for name in names:
            parts.append(f"## Skill: {name}\n\n{_read_skill(name)}")
        contexts[group] = "\n\n---\n\n".join(parts)
    return contexts


def _default_out_dir(prefix: str = "workflow") -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("outputs") / f"{prefix}_{timestamp}"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_local_env() -> None:
    root = _project_root()
    candidate_roots = [root, root.parent, root.parent.parent, Path.cwd()]
    seen: set[Path] = set()
    for candidate in candidate_roots:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_env_file(resolved / ".env")
        _load_env_file(resolved / ".env.local")


def _env_first(*names: str) -> Optional[str]:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _split_models(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _dedupe_models(models: List[str]) -> List[str]:
    seen = set()
    deduped = []
    for model in models:
        if model not in seen:
            seen.add(model)
            deduped.append(model)
    return deduped


def _model_pool(
    config: Dict[str, Any],
    pool_key: str,
    single_keys: List[str],
    env_names: List[str],
    defaults: List[str],
) -> List[str]:
    candidates: List[str] = []
    for key in single_keys:
        candidates.extend(_split_models(config.get(key)))
    candidates.extend(_split_models(config.get(pool_key)))
    candidates.extend(_split_models(_env_first(*env_names)))
    candidates.extend(defaults)
    return _dedupe_models(candidates)


def _model_error_record(role: str, model: str, exc: Exception) -> Dict[str, str]:
    return {
        "role": role,
        "model": model,
        "error_type": exc.__class__.__name__,
        "error": redact_secrets(exc),
    }


def _is_retryable_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "missing openai-compatible api key" in message:
        return False
    if "api key" in message and ("missing" in message or "not set" in message):
        return False
    return True


def _resolved_model_config(model_config: Dict[str, Any]) -> Dict[str, Any]:
    """合并请求、环境变量和默认值，得到文本/视觉模型池配置。

    模型池按“请求显式指定 -> 环境变量 -> 默认列表”的优先级排列；调用端会
    依次尝试，直到某个模型成功或遇到不可重试错误。
    """

    load_local_env()
    resolved = dict(model_config)
    configured_base_url = _env_first(
        "GSB_BASE_URL", "DASHSCOPE_BASE_URL", "OPENAI_BASE_URL"
    )
    if "base_url" not in resolved:
        if configured_base_url:
            resolved["base_url"] = configured_base_url
        elif _env_first("OPENAI_API_KEY") and not _env_first("DASHSCOPE_API_KEY", "GSB_API_KEY"):
            # Let the OpenAI SDK use its default endpoint for OpenAI-compatible
            # local configs that only provide OPENAI_API_KEY.
            pass
        else:
            resolved["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    text_models = _model_pool(
        resolved,
        "text_models",
        ["text_model", "model"],
        [
            "GSB_TEXT_MODELS",
            "DASHSCOPE_TEXT_MODELS",
            "OPENAI_TEXT_MODELS",
            "GSB_TEXT_MODEL",
            "DASHSCOPE_TEXT_MODEL",
            "OPENAI_TEXT_MODEL",
        ],
        DEFAULT_TEXT_MODELS,
    )
    vision_models = _model_pool(
        resolved,
        "vision_models",
        ["vision_model"],
        [
            "GSB_VISION_MODELS",
            "DASHSCOPE_VISION_MODELS",
            "OPENAI_VISION_MODELS",
            "GSB_VISION_MODEL",
            "DASHSCOPE_VISION_MODEL",
            "OPENAI_VISION_MODEL",
            "VISION_MODEL",
        ],
        DEFAULT_VISION_MODELS,
    )
    resolved["text_models"] = text_models
    resolved["vision_models"] = vision_models
    resolved.setdefault("text_model", text_models[0] if text_models else "")
    resolved.setdefault("vision_model", vision_models[0] if vision_models else "")
    resolved.setdefault(
        "api_key_env",
        _env_first("GSB_API_KEY_ENV") or "DASHSCOPE_API_KEY",
    )
    if "vision_base_url" not in resolved:
        vision_base_url = _env_first(
            "GSB_VISION_BASE_URL", "DASHSCOPE_VISION_BASE_URL", "VISION_BASE_URL"
        )
        if vision_base_url:
            resolved["vision_base_url"] = vision_base_url
    if "vision_api_key_env" not in resolved:
        vision_key_env = _env_first("GSB_VISION_API_KEY_ENV", "VISION_API_KEY_ENV")
        if vision_key_env:
            resolved["vision_api_key_env"] = vision_key_env
    return resolved


def _env_from_names(*names: Optional[str]) -> Optional[str]:
    for name in names:
        if name:
            value = os.getenv(name)
            if value:
                return value
    return None


def _api_key_from_config(config: Dict[str, Any], role: str) -> Optional[str]:
    if role == "vision":
        direct = config.get("vision_api_key") or config.get("api_key")
        if direct:
            return str(direct)
        return _env_from_names(
            config.get("vision_api_key_env"),
            config.get("api_key_env"),
            "GSB_VISION_API_KEY",
            "VISION_API_KEY",
            "GSB_API_KEY",
            "DASHSCOPE_API_KEY",
            "OPENAI_API_KEY",
        )

    direct = config.get("api_key")
    if direct:
        return str(direct)
    return _env_from_names(
        config.get("api_key_env"),
        "GSB_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
    )


def _extract_json_object(text: str) -> Dict[str, Any]:
    """从模型回复中提取 JSON 对象。

    模型偶尔会包一层 Markdown 代码块，或在 JSON 前后加解释文字；这里做宽松
    解析，但最终仍要求结果必须是 object，避免后续字段访问悄悄错位。
    """

    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("model response JSON must be an object")
    return parsed


def _is_solution_request(request: Dict[str, Any]) -> bool:
    variant = request.get("diagram_variant") or request.get("variant")
    return variant == "solution" or request.get("disclosure_policy") == "annotated"


def _solution_reuse_id(request: Dict[str, Any]) -> str:
    return str(
        request.get("reuse_geometry_from")
        or request.get("reuse_from")
        or request.get("base_diagram_job_id")
        or ""
    ).strip()


def _resolve_reuse_job_dir(request: Dict[str, Any], out_dir: Path) -> Path:
    explicit = request.get("reuse_geometry_dir") or request.get("base_job_dir")
    if explicit:
        path = Path(str(explicit))
        return path if path.is_absolute() else (out_dir / path).resolve()
    reuse_id = _solution_reuse_id(request)
    if not reuse_id:
        raise ValueError("solution diagram job requires reuse_geometry_from")
    return (out_dir.parent / reuse_id).resolve()


def _wl_symbol(name: str) -> str:
    symbol = _point_label(name)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", symbol):
        raise ValueError(f"invalid Wolfram point symbol: {name}")
    return symbol


def _wl_number(value: float) -> str:
    text = f"{float(value):.12g}"
    if text == "-0":
        return "0"
    return text


def _wl_point_rules(points: Dict[str, List[float]]) -> str:
    rules = []
    for name, coord in points.items():
        pair = _numeric_pair(coord)
        if pair is None:
            raise ValueError(f"invalid coordinate for point {name}: {coord}")
        rules.append(f"{_wl_symbol(name)} -> {{{_wl_number(pair[0])}, {_wl_number(pair[1])}}}")
    return "{" + ", ".join(rules) + "}"


def _wl_point_list(points: List[str]) -> str:
    return "{" + ", ".join(_wl_symbol(name) for name in points) + "}"


def _merge_lists(base: Any, delta: Any) -> List[Any]:
    merged: List[Any] = []
    if isinstance(base, list):
        merged.extend(base)
    if isinstance(delta, list):
        merged.extend(delta)
    elif delta not in (None, "", []):
        merged.append(delta)
    return merged


def _merge_dict(base: Any, delta: Any) -> Dict[str, Any]:
    merged = dict(base) if isinstance(base, dict) else {}
    if isinstance(delta, dict):
        merged.update(delta)
    return merged


def _base_diagram_spec_from_renderer_spec(base_spec: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": base_spec.get("type") or "synthetic_geometry",
        "segments": base_spec.get("segments") or [],
        "polygons": base_spec.get("polygons") or [],
        "markers": base_spec.get("markers") or [],
        "labels": base_spec.get("labels") or {},
        "teaching_focus": base_spec.get("teaching_focus") or [],
        "constraints": base_spec.get("constraints") or [],
    }


def _merge_diagram_spec(base_spec: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base_spec)
    for key in ("objects", "segments", "polygons", "markers", "teaching_focus", "constraints"):
        merged[key] = _merge_lists(base_spec.get(key), delta.get(key))
    merged["labels"] = _merge_dict(base_spec.get("labels"), delta.get("labels"))
    annotations = _merge_lists(base_spec.get("annotations"), delta.get("annotations"))
    if annotations:
        merged["annotations"] = annotations
    return merged


def _solution_model_json(
    request: Dict[str, Any],
    base_renderer_spec: Dict[str, Any],
    history: List[Dict[str, Any]],
    round_index: int,
    skills_context: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    add_auxiliary = request.get("add_auxiliary")
    if isinstance(add_auxiliary, dict) and add_auxiliary.get("hypotheses_wl"):
        return {
            "auxiliary_points": _compact_list(add_auxiliary.get("add_points") or add_auxiliary.get("points")),
            "auxiliary_hypotheses_wl": _compact_list(add_auxiliary.get("hypotheses_wl")),
            "diagram_spec_delta": add_auxiliary.get("diagram_spec_delta") or {},
            "rationale": "Used structured add_auxiliary from request.",
            "model_attempts": [],
        }

    model_config = _resolved_model_config(request.get("model_config", {}))
    client = _make_client(model_config, "text")
    models = model_config.get("text_models", [])
    if not models:
        raise RuntimeError("No text models configured")

    system_prompt = (
        "You generate Wolfram Language auxiliary constraints for annotated "
        "geometry teaching diagrams. Return only valid JSON. Do not use Import, "
        "Get, file operations, URL access, or process execution. The existing "
        "prompt diagram points are already fixed to solved coordinates by the "
        "workflow; you must only add auxiliary points, Wolfram hypotheses for "
        "those points, and renderer-visible diagram_spec_delta. Do not recompute "
        "or move existing points.\n\n"
        "Use the following local skills as binding implementation guidance:\n\n"
        f"{(skills_context or {}).get('generate', '')}"
    )
    feedback = history[-1].get("vision_result") if history else None
    user_payload = {
        "problem_text": request.get("problem_text", ""),
        "teaching_focus": request.get("teaching_focus", []),
        "objects_hint": request.get("objects_hint", {}),
        "solution_intent": request.get("solution_intent") or request.get("diagram_intent", ""),
        "base_points_locked": base_renderer_spec.get("points", {}),
        "base_visible_spec": _base_diagram_spec_from_renderer_spec(base_renderer_spec),
        "round_index": round_index,
        "previous_feedback": feedback,
        "required_json_schema": {
            "auxiliary_points": ["New point labels only, e.g. H"],
            "auxiliary_hypotheses_wl": [
                "Wolfram expressions appended to GeometricScene hypotheses, e.g. H == TriangleCenter[{A,B,C}, {\"Foot\", A}]"
            ],
            "diagram_spec_delta": {
                "segments": [["A", "H"]],
                "markers": [{"type": "right_angle", "vertex": "H", "arms": ["A", "B"]}],
                "labels": {"H": {"text": "H"}},
                "teaching_focus": [],
            },
            "rationale": "Short reason for the auxiliary construction.",
        },
    }

    attempts = []
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=float(model_config.get("temperature", 0.2)),
                timeout=float(model_config.get("request_timeout_s", 120)),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
            )
            content = response.choices[0].message.content or "{}"
            payload = _extract_json_object(content)
            if "auxiliary_hypotheses_wl" not in payload:
                raise ValueError("text model response missing auxiliary_hypotheses_wl")
            payload["model_used"] = model
            payload["raw_response"] = content
            payload["model_attempts"] = attempts + [
                {
                    "role": "text",
                    "model": model,
                    "status": "ok",
                    "raw_response": content,
                }
            ]
            return payload
        except Exception as exc:
            attempts.append(_model_error_record("text", model, exc))
            if not _is_retryable_model_error(exc):
                break

    raise ModelPoolError("text", attempts)


def _solution_scene_payload(
    request: Dict[str, Any],
    out_dir: Path,
    history: List[Dict[str, Any]],
    round_index: int,
    skills_context: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """生成“解答图”的 GeometricScene payload。

    解答图与普通 prompt 图最大的区别是：已有点坐标必须从 base renderer spec
    锁定复用，模型只能追加辅助点、辅助约束和可视标记。这样可以保证同一道题的
    prompt 图与 solution 图几何形状一致，只是讲解层信息更多。
    """

    base_dir = _resolve_reuse_job_dir(request, out_dir)
    base_spec_path = base_dir / "final_renderer_spec.json"
    base_renderer_spec = _read_json(base_spec_path)
    base_points = base_renderer_spec.get("points")
    if not isinstance(base_points, dict) or not base_points:
        raise ValueError(f"base renderer spec has no points: {base_spec_path}")

    auxiliary_payload = _solution_model_json(
        request,
        base_renderer_spec,
        history,
        round_index,
        skills_context,
    )
    aux_points = [_wl_symbol(str(item)) for item in _compact_list(auxiliary_payload.get("auxiliary_points"))]
    hypotheses = [str(item).strip() for item in _compact_list(auxiliary_payload.get("auxiliary_hypotheses_wl")) if str(item).strip()]
    if not hypotheses and aux_points:
        raise ValueError("solution auxiliary points require auxiliary_hypotheses_wl")

    fixed_rules = _wl_point_rules(base_points)
    aux_list = _wl_point_list(aux_points) if aux_points else "{}"
    hypotheses_wl = "{\n    " + ",\n    ".join(hypotheses) + "\n  }" if hypotheses else "{}"
    scene_code = (
        "GeometricScene[\n"
        f"  Join[{fixed_rules}, {aux_list}],\n"
        f"  {hypotheses_wl}\n"
        "]"
    )

    base_diagram_spec = _base_diagram_spec_from_renderer_spec(base_renderer_spec)
    delta = auxiliary_payload.get("diagram_spec_delta")
    if not isinstance(delta, dict):
        delta = {}
    diagram_spec = _merge_diagram_spec(base_diagram_spec, delta)
    diagram_spec["type"] = diagram_spec.get("type") or request.get("diagram_type") or "synthetic_geometry"
    diagram_spec["constraints"] = _merge_lists(diagram_spec.get("constraints"), hypotheses)
    diagram_spec.setdefault("teaching_focus", request.get("teaching_focus", []))

    return {
        "scene_code": scene_code,
        "points": list(base_points.keys()) + aux_points,
        "diagram_spec": diagram_spec,
        "rationale": auxiliary_payload.get("rationale", "Annotated solution diagram reusing locked prompt geometry."),
        "solution_reuse": {
            "reuse_geometry_from": _solution_reuse_id(request),
            "base_job_dir": str(base_dir),
            "base_renderer_spec": str(base_spec_path),
            "locked_points": list(base_points.keys()),
            "auxiliary_points": aux_points,
        },
        "model_used": auxiliary_payload.get("model_used", ""),
        "raw_response": auxiliary_payload.get("raw_response", ""),
        "model_attempts": auxiliary_payload.get("model_attempts", []),
    }


def _make_client(model_config: Dict[str, Any], role: str = "text"):
    if OpenAI is None:
        raise RuntimeError("Missing dependency: install openai>=1.0.0")
    config = _resolved_model_config(model_config)
    if role == "vision":
        api_key = _api_key_from_config(config, role)
        base_url = config.get("vision_base_url") or config.get("base_url")
    else:
        api_key = _api_key_from_config(config, role)
        base_url = config.get("base_url")
    if not api_key:
        raise RuntimeError(f"Missing OpenAI-compatible API key for {role} model")
    kwargs = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _text_model_json(
    request: Dict[str, Any],
    history: List[Dict[str, Any]],
    round_index: int,
    skills_context: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """调用文本模型生成普通几何图的 GeometricScene 和可视化 spec。

    返回值不是直接给 SVG renderer 的最终 spec，而是“模型意图 + Wolfram
    scene_code”。真正的点坐标要等 Wolfram 求解后再编译出来。
    """

    model_config = _resolved_model_config(request.get("model_config", {}))
    client = _make_client(model_config, "text")
    models = model_config.get("text_models", [])
    if not models:
        raise RuntimeError("No text models configured")

    system_prompt = (
        "You generate Wolfram Language GeometricScene code for math teaching diagrams. "
        "Return only valid JSON. Do not use Import, Get, file operations, URL access, "
        "or process execution. Prefer readable, non-degenerate diagrams. The PNG is "
        "only for optional evaluation; the final teaching renderer will consume the "
        "solved point coordinates plus diagram_spec. Make diagram_spec renderer-friendly: "
        "declare visible segments, polygons, labels, and teaching markers such as "
        "right_angle, equal_ticks, angle_arc when they are important.\n\n"
        "Use the following local skills as binding implementation guidance:\n\n"
        f"{(skills_context or {}).get('generate', '')}"
    )
    feedback = history[-1].get("vision_result") if history else None
    user_payload = {
        "problem_text": request.get("problem_text", ""),
        "grade_or_topic": request.get("grade_or_topic", ""),
        "teaching_focus": request.get("teaching_focus", []),
        "objects_hint": request.get("objects_hint", {}),
        "diagram_intent": request.get("diagram_intent", "synthetic_geometry"),
        "round_index": round_index,
        "previous_feedback": feedback,
        "required_json_schema": {
            "scene_code": "A complete Wolfram GeometricScene[...] expression.",
            "points": ["Point labels used in the scene, e.g. A, B, C"],
            "diagram_spec": {
                "type": "synthetic_geometry | coordinate_geometry",
                "objects": [],
                "segments": [["A", "B"]],
                "polygons": [{"points": ["A", "B", "C"]}],
                "markers": [
                    {"type": "right_angle", "vertex": "D", "arms": ["A", "B"]}
                ],
                "teaching_focus": [],
            },
            "rationale": "Short reason for the chosen constraints.",
        },
    }

    attempts = []
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=float(model_config.get("temperature", 0.2)),
                timeout=float(model_config.get("request_timeout_s", 120)),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(user_payload, ensure_ascii=False),
                    },
                ],
            )
            content = response.choices[0].message.content or "{}"
            payload = _extract_json_object(content)
            if "scene_code" not in payload:
                raise ValueError("text model response missing scene_code")
            payload["model_used"] = model
            payload["raw_response"] = content
            payload["model_attempts"] = attempts + [
                {
                    "role": "text",
                    "model": model,
                    "status": "ok",
                    "raw_response": content,
                }
            ]
            return payload
        except Exception as exc:
            attempts.append(_model_error_record("text", model, exc))
            if not _is_retryable_model_error(exc):
                break

    raise ModelPoolError("text", attempts)


def _validate_scene_code(scene_code: str) -> None:
    """对模型生成的 Wolfram 代码做最小安全门禁。"""

    if "GeometricScene" not in scene_code:
        raise ValueError("scene_code must contain GeometricScene")
    for token in FORBIDDEN_WL_TOKENS:
        if token in scene_code:
            raise ValueError(f"scene_code contains forbidden token: {token}")


def _render_worker(
    queue: mp.Queue,
    wl_kernel: str,
    wl_dir: str,
    scene_code: str,
    seed: int,
    timeout_s: int,
    render_image: bool,
    image_abs: str,
) -> None:
    """在独立进程中运行 Wolfram。

    Wolfram kernel 或 GeometricScene 求解可能长时间卡住；因此 worker 只负责
    把结果放进 queue，进程生命周期由主进程的 _render_scene 统一看门。
    """

    try:
        if WOLFRAM_IMPORT_ERROR is not None:
            raise RuntimeError(f"Missing wolframclient: {WOLFRAM_IMPORT_ERROR}")
        with WolframLanguageSession(wl_kernel) as session:  # type: ignore[misc]
            wl_root = Path(wl_dir)
            session.evaluate(wl.Get(str(wl_root / "scene_builders.wl")))  # type: ignore[union-attr]
            session.evaluate(wl.Get(str(wl_root / "bench_core.wl")))  # type: ignore[union-attr]
            session.evaluate(wlexpr("1+1"))  # type: ignore[misc]
            scene = session.evaluate(wlexpr(scene_code))  # type: ignore[misc]
            result = session.evaluate(  # type: ignore[operator]
                Global.SolveAndMeasure(
                    scene,
                    int(seed),
                    int(timeout_s),
                    bool(render_image),
                    Path(image_abs).as_posix() if image_abs else "",
                )
            )
            raw = dict(result) if hasattr(result, "items") else {}
            queue.put(_wl_to_python(raw))
    except Exception as exc:
        queue.put(
            {
                "success": False,
                "fail_type": "runtime_error",
                "message": redact_secrets(exc),
                "solve_time_s": 0,
            }
        )


def _wl_to_python(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return {_wl_to_python(k): _wl_to_python(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wl_to_python(item) for item in value]
    if hasattr(value, "name"):
        return str(value)
    if hasattr(value, "head") and hasattr(value, "args"):
        return [_wl_to_python(item) for item in value.args]
    return value


def _point_label(value: Any) -> str:
    label = str(value).strip()
    if "`" in label:
        label = label.rsplit("`", 1)[-1]
    return label


def _numeric_pair(value: Any) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None


def _normalize_solver_points(parameters: Any) -> Dict[str, List[float]]:
    """Normalize Wolfram point rules into renderer-friendly point coordinates.

    Wolfram 返回的点规则可能是 dict、规则列表或嵌套结构；renderer 只需要
    {"A": [x, y]} 这种稳定格式，所以这里集中做兼容处理。
    """
    points: Dict[str, List[float]] = {}
    if isinstance(parameters, dict):
        iterable = parameters.items()
    elif isinstance(parameters, (list, tuple)):
        iterable = []
        for item in parameters:
            if isinstance(item, dict):
                iterable.extend(item.items())
            elif isinstance(item, (list, tuple)) and len(item) == 2:
                iterable.append((item[0], item[1]))
    else:
        iterable = []

    for name, coord in iterable:
        pair = _numeric_pair(coord)
        if pair is not None:
            points[_point_label(name)] = pair
    return points


def _compact_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return [item for item in value if item not in ("", None, [])]
    if value in ("", None):
        return []
    return [value]


def _point_names(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    names = [_point_label(item) for item in value if isinstance(item, (str, int, float))]
    return [name for name in names if name]


def _segment_from(value: Any) -> Optional[Dict[str, str]]:
    if isinstance(value, dict):
        start = value.get("from") or value.get("start") or value.get("a")
        end = value.get("to") or value.get("end") or value.get("b")
        if start and end:
            return {"from": _point_label(start), "to": _point_label(end)}
        names = _point_names(value.get("points"))
        if len(names) >= 2:
            return {"from": names[0], "to": names[1]}
    names = _point_names(value)
    if len(names) >= 2:
        return {"from": names[0], "to": names[1]}
    return None


def _polygon_from(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        names = _point_names(value.get("points") or value.get("vertices"))
        if len(names) >= 3:
            polygon = {k: v for k, v in value.items() if k not in {"points", "vertices"}}
            polygon["points"] = names
            return polygon
    names = _point_names(value)
    if len(names) >= 3:
        return {"points": names}
    return None


def _dedupe_dicts(items: List[Dict[str, Any]], key_fn) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _extend_render_objects(
    segments: List[Dict[str, str]],
    polygons: List[Dict[str, Any]],
    markers: List[Dict[str, Any]],
    source: Any,
) -> None:
    """从 objects_hint 或模型 diagram_spec 中收集 renderer 可画对象。

    支持两种输入风格：直接的 segments/polygons/markers 字段，以及 objects
    里按 type/kind 描述的对象。这里只做结构归一化，不做坐标求解。
    """

    if not isinstance(source, dict):
        return

    for item in _compact_list(source.get("segments")):
        segment = _segment_from(item)
        if segment:
            segments.append(segment)
    for item in _compact_list(source.get("polygons")):
        polygon = _polygon_from(item)
        if polygon:
            polygons.append(polygon)
    for item in _compact_list(source.get("markers")):
        if isinstance(item, dict) and item.get("type"):
            markers.append(item)

    objects = source.get("objects")
    if isinstance(objects, dict):
        _extend_render_objects(segments, polygons, markers, objects)
    elif isinstance(objects, list):
        for item in objects:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or item.get("kind") or "").lower()
            if kind in {"segment", "line"}:
                segment = _segment_from(item)
                if segment:
                    segments.append(segment)
            elif kind in {"triangle", "polygon"}:
                polygon = _polygon_from(item)
                if polygon:
                    polygons.append(polygon)
            elif kind in {"marker", "right_angle", "equal_ticks", "angle_arc"}:
                marker = dict(item)
                marker.setdefault("type", kind)
                markers.append(marker)


def _normalize_marker(marker: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(marker)
    marker_type = str(normalized.get("type", "")).lower()
    if marker_type == "equal_tick":
        marker_type = "equal_ticks"
    if marker_type:
        normalized["type"] = marker_type
    vertex = normalized.get("vertex") or normalized.get("at")
    if vertex:
        normalized["vertex"] = _point_label(vertex)
        normalized.pop("at", None)
    if isinstance(normalized.get("arms"), list):
        normalized["arms"] = _point_names(normalized["arms"])
    if isinstance(normalized.get("segments"), list):
        segments = []
        for segment in normalized["segments"]:
            parsed = _segment_from(segment)
            if parsed:
                segments.append([parsed["from"], parsed["to"]])
        normalized["segments"] = segments
    return normalized


def _compile_renderer_spec(
    request: Dict[str, Any],
    scene_payload: Dict[str, Any],
    render_result: Dict[str, Any],
) -> Dict[str, Any]:
    """把模型意图和 Wolfram 求解结果合并成 renderer 的最终输入。

    数据来源有三层：
    1. Wolfram render_result 提供可靠点坐标；
    2. 模型 diagram_spec 提供要画哪些线段、多边形、标记；
    3. request.objects_hint 作为题目侧的保底提示。

    这里会过滤掉引用不存在点的线段/多边形，避免下游 renderer 因脏引用崩溃。
    """

    diagram_spec = scene_payload.get("diagram_spec")
    if not isinstance(diagram_spec, dict):
        diagram_spec = {}
    objects_hint = request.get("objects_hint")
    if not isinstance(objects_hint, dict):
        objects_hint = {}

    points = _normalize_solver_points(
        render_result.get("parameters")
        or render_result.get("points")
        or diagram_spec.get("points")
        or objects_hint.get("points")
    )

    segments: List[Dict[str, str]] = []
    polygons: List[Dict[str, Any]] = []
    markers: List[Dict[str, Any]] = []
    _extend_render_objects(segments, polygons, markers, objects_hint)
    _extend_render_objects(segments, polygons, markers, diagram_spec)

    point_names = set(points.keys())
    if point_names:
        segments = [
            item for item in segments if item.get("from") in point_names and item.get("to") in point_names
        ]
        polygons = [
            item for item in polygons if all(name in point_names for name in item.get("points", []))
        ]

    segments = _dedupe_dicts(
        segments,
        lambda item: tuple(sorted([item.get("from", ""), item.get("to", "")])),
    )
    polygons = _dedupe_dicts(polygons, lambda item: tuple(item.get("points", [])))
    markers = [_normalize_marker(marker) for marker in markers]

    labels = diagram_spec.get("labels") if isinstance(diagram_spec.get("labels"), dict) else {}
    normalized_labels = {
        name: labels.get(name, {"text": name}) if isinstance(labels.get(name), dict) else {"text": name}
        for name in points
    }

    return {
        "schema_version": "geometry-render-spec/v1",
        "status": "ready" if points else "missing_coordinates",
        "type": diagram_spec.get("type")
        or request.get("diagram_type")
        or request.get("diagram_intent")
        or "synthetic_geometry",
        "points": points,
        "polygons": polygons,
        "segments": segments,
        "markers": markers,
        "labels": normalized_labels,
        "teaching_focus": _compact_list(
            diagram_spec.get("teaching_focus") or request.get("teaching_focus")
        ),
        "constraints": _compact_list(
            diagram_spec.get("constraints") or objects_hint.get("constraints")
        ),
        "source": {
            "solver": "wolfram_geometric_scene",
            "scene_code_path": "final_geometric_scene.wl",
            "model_diagram_spec": diagram_spec,
            "render_image_requested": render_result.get("render_image_requested", True),
            "render_fail_type": render_result.get("fail_type", ""),
        },
    }


def _render_scene(
    scene_code: str,
    out_dir: Path,
    round_index: int,
    request: Dict[str, Any],
) -> Dict[str, Any]:
    """求解单轮 GeometricScene，并按需生成 Wolfram 调试 PNG。

    主进程只负责准备 round 目录、启动 worker、执行硬超时和校验 PNG 是否真的
    生成；Wolfram 相关调用都在 _render_worker 里完成。
    """

    _validate_scene_code(scene_code)
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    scene_path = round_dir / "scene.wl"
    scene_path.write_text(scene_code, encoding="utf-8")

    render_image = bool(request.get("wolfram_render_image", request.get("render_images", True)))
    image_rel = f"rounds/round_{round_index}/scene.png" if render_image else ""
    image_abs = out_dir / image_rel if image_rel else None
    queue: mp.Queue = mp.Queue(maxsize=1)
    timeout_s = int(request.get("wolfram_timeout_s", request.get("timeout_s", 60)))
    hard_timeout_s = int(request.get("wolfram_hard_timeout_s", timeout_s + 20))
    wl_kernel = resolve_wolfram_kernel(request.get("wl_kernel"))
    wl_dir = resolve_wl_dir()

    proc = mp.Process(
        target=_render_worker,
        args=(
            queue,
            wl_kernel,
            wl_dir.as_posix(),
            scene_code,
            int(request.get("seed", round_index + 1)),
            timeout_s,
            render_image,
            str(image_abs) if image_abs else "",
        ),
    )
    proc.start()
    proc.join(timeout=hard_timeout_s)
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=5)
        if proc.is_alive():
            proc.kill()
        return {
            "success": False,
            "fail_type": "host_watchdog_timeout",
            "message": f"Wolfram render exceeded {hard_timeout_s}s",
            "image_path": image_rel,
            "render_image_requested": render_image,
        }

    if queue.empty():
        return {
            "success": False,
            "fail_type": "worker_no_result",
            "message": "Wolfram worker returned no result",
            "image_path": image_rel,
            "render_image_requested": render_image,
        }

    result = queue.get()
    result["render_image_requested"] = render_image
    if result.get("success") and render_image:
        if image_abs and image_abs.exists():
            result["image_path"] = image_rel
        else:
            result["success"] = False
            result["fail_type"] = "missing_rendered_image"
            result["message"] = "Wolfram reported render success but PNG was not created"
            result["image_path"] = image_rel
    elif result.get("success"):
        result["image_path"] = ""
    return result


def _solution_reuse_check(
    request: Dict[str, Any],
    out_dir: Path,
    render_result: Dict[str, Any],
    tolerance: float = 1e-7,
) -> Dict[str, Any]:
    """校验 solution 图没有移动 prompt 图的既有点。

    解答图可以添加辅助点，但不能改变基础图坐标；一旦发现 drift，调用方会把本轮
    render 标记为失败，迫使下一轮重新生成辅助约束。
    """

    if not _is_solution_request(request) or not render_result.get("success"):
        return {}
    base_dir = _resolve_reuse_job_dir(request, out_dir)
    base_spec = _read_json(base_dir / "final_renderer_spec.json")
    base_points = base_spec.get("points") if isinstance(base_spec.get("points"), dict) else {}
    solved_points = _normalize_solver_points(render_result.get("parameters"))
    drift: List[Dict[str, Any]] = []
    missing: List[str] = []
    for name, expected in base_points.items():
        expected_pair = _numeric_pair(expected)
        actual_pair = _numeric_pair(solved_points.get(str(name)))
        if expected_pair is None:
            continue
        if actual_pair is None:
            missing.append(str(name))
            continue
        dx = abs(expected_pair[0] - actual_pair[0])
        dy = abs(expected_pair[1] - actual_pair[1])
        if dx > tolerance or dy > tolerance:
            drift.append(
                {
                    "point": str(name),
                    "expected": expected_pair,
                    "actual": actual_pair,
                    "max_abs_delta": max(dx, dy),
                }
            )
    return {
        "reuse_geometry_from": _solution_reuse_id(request),
        "base_job_dir": str(base_dir),
        "locked_point_count": len(base_points),
        "locked_points_same": not drift and not missing,
        "drift": drift,
        "missing": missing,
    }


def _image_data_url(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _evaluate_image(
    request: Dict[str, Any],
    render_result: Dict[str, Any],
    out_dir: Path,
    skills_context: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """用视觉模型评估调试图是否适合学生讲义。

    如果请求关闭了 Wolfram PNG 渲染，则进入 spec_only 模式：只要 Wolfram
    求解成功，就跳过视觉评价，让最终 renderer spec 继续向下游流转。
    """

    if not render_result.get("success"):
        return {
            "usable": False,
            "score": 1,
            "defects": [render_result.get("fail_type", "render_failed")],
            "suggested_constraint_feedback": render_result.get(
                "message", "Render failed; generate a simpler valid GeometricScene."
            ),
        }

    if render_result.get("render_image_requested") is False:
        return {
            "usable": True,
            "score": "",
            "defects": [],
            "evaluation_mode": "spec_only",
            "suggested_constraint_feedback": "",
        }

    image_rel = render_result.get("image_path")
    image_path = out_dir / image_rel if image_rel else None
    if not image_path or not image_path.exists():
        return {
            "usable": False,
            "score": 1,
            "defects": ["missing_image"],
            "suggested_constraint_feedback": "The render did not produce a PNG.",
        }

    model_config = _resolved_model_config(request.get("model_config", {}))
    client = _make_client(model_config, "vision")
    vision_models = model_config.get("vision_models", [])
    if not vision_models:
        raise RuntimeError("No vision models configured")

    prompt = {
        "task": "Evaluate whether this geometry diagram is usable for a student-facing math explanation.",
        "problem_text": request.get("problem_text", ""),
        "teaching_focus": request.get("teaching_focus", []),
        "local_skill_guidance": (skills_context or {}).get("evaluate", ""),
        "criteria": [
            "matches the problem objects and constraints",
            "not degenerate",
            "important points/segments/regions are visible",
            "labels would be placeable/readable",
            "coordinate axes are readable when needed",
            "does not visually imply false special properties",
        ],
        "required_json_schema": {
            "usable": "boolean",
            "score": "integer 1-5",
            "defects": ["short defect strings"],
            "suggested_constraint_feedback": "short actionable feedback for the next GeometricScene attempt",
        },
    }

    attempts = []
    for vision_model in vision_models:
        try:
            response = client.chat.completions.create(
                model=vision_model,
                temperature=float(model_config.get("vision_temperature", 0.0)),
                timeout=float(model_config.get("vision_request_timeout_s", model_config.get("request_timeout_s", 120))),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(prompt, ensure_ascii=False),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": _image_data_url(image_path)},
                            },
                        ],
                    }
                ],
            )
            content = response.choices[0].message.content or "{}"
            payload = _extract_json_object(content)
            return {
                "usable": bool(payload.get("usable")),
                "score": int(payload.get("score", 1)),
                "defects": payload.get("defects", []),
                "suggested_constraint_feedback": payload.get(
                    "suggested_constraint_feedback", ""
                ),
                "model_used": vision_model,
                "raw_response": content,
                "model_attempts": attempts
                + [
                    {
                        "role": "vision",
                        "model": vision_model,
                        "status": "ok",
                        "raw_response": content,
                    }
                ],
            }
        except Exception as exc:
            attempts.append(_model_error_record("vision", vision_model, exc))
            if not _is_retryable_model_error(exc):
                break

    raise ModelPoolError("vision", attempts)


def generate_scene_node(state: WorkflowState) -> WorkflowState:
    """生成节点：根据当前轮次和上一轮反馈产出 scene_payload.json。

    普通图走 _text_model_json；solution 图走 _solution_scene_payload，以便复用
    base 图坐标。失败时不抛出到外层，而是写入 state/status，保证后续节点仍能
    生成结构化失败产物。
    """

    request = state["request"]
    round_index = state.get("round_index", 0)
    history = state.get("history", [])
    out_dir = Path(state["out_dir"])
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    _emit_event(out_dir, "generate.start", round_index=round_index)

    try:
        if _is_solution_request(request):
            scene_payload = _solution_scene_payload(
                request,
                out_dir,
                history,
                round_index,
                state.get("skills_context") or load_skills_context(),
            )
        else:
            scene_payload = _text_model_json(
                request,
                history,
                round_index,
                state.get("skills_context") or load_skills_context(),
            )
        _write_json(round_dir / "scene_payload.json", scene_payload)
        state["scene_payload"] = scene_payload
        _emit_event(
            out_dir,
            "generate.end",
            round_index=round_index,
            status="ok",
            model_used=scene_payload.get("model_used", ""),
            scene_chars=len(scene_payload.get("scene_code", "")),
        )
    except ModelPoolError as exc:
        scene_payload = {"model_attempts": exc.attempts}
        _write_json(round_dir / "scene_payload.json", scene_payload)
        state["scene_payload"] = scene_payload
        state["status"] = "failed"
        state["error"] = f"generate_scene_failed: {redact_secrets(exc)}"
        _emit_event(
            out_dir,
            "generate.end",
            round_index=round_index,
            status="failed",
            error=state["error"],
        )
    except Exception as exc:
        scene_payload = {"model_attempts": [], "error": redact_secrets(exc)}
        _write_json(round_dir / "scene_payload.json", scene_payload)
        state["scene_payload"] = scene_payload
        state["status"] = "failed"
        state["error"] = f"generate_scene_failed: {redact_secrets(exc)}"
        _emit_event(
            out_dir,
            "generate.end",
            round_index=round_index,
            status="failed",
            error=state["error"],
        )
    return state


def render_wolfram_node(state: WorkflowState) -> WorkflowState:
    """渲染/求解节点：执行 Wolfram，并写出 render_result.json。"""

    out_dir = Path(state["out_dir"])
    round_index = state.get("round_index", 0)
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    _emit_event(out_dir, "render.start", round_index=round_index)
    if state.get("status") == "failed":
        render_result = {
            "success": False,
            "fail_type": "skipped",
            "message": state.get("error", "previous workflow step failed"),
        }
        _write_json(round_dir / "render_result.json", render_result)
        state["render_result"] = render_result
        _emit_event(
            out_dir,
            "render.end",
            round_index=round_index,
            status="skipped",
            fail_type=render_result["fail_type"],
        )
        return state
    try:
        scene_code = state["scene_payload"]["scene_code"]
        render_result = _render_scene(scene_code, out_dir, round_index, state["request"])
        reuse_check = _solution_reuse_check(state["request"], out_dir, render_result)
        if reuse_check:
            render_result["solution_reuse_check"] = reuse_check
            if not reuse_check.get("locked_points_same", False):
                render_result["success"] = False
                render_result["fail_type"] = "solution_base_point_drift"
                render_result["message"] = "Solution diagram did not preserve prompt point coordinates"
        _write_json(round_dir / "render_result.json", render_result)
        state["render_result"] = render_result
        image_rel = render_result.get("image_path")
        image_exists = bool(image_rel and (out_dir / image_rel).exists())
        _emit_event(
            out_dir,
            "render.end",
            round_index=round_index,
            status="ok" if render_result.get("success") else "failed",
            fail_type=render_result.get("fail_type", ""),
            solve_time_s=render_result.get("solve_time_s", ""),
            image_path=image_rel or "",
            image_exists=image_exists,
            render_image_requested=render_result.get("render_image_requested", True),
        )
    except Exception as exc:
        render_result = {
            "success": False,
            "fail_type": "render_exception",
            "message": redact_secrets(exc),
        }
        _write_json(round_dir / "render_result.json", render_result)
        state["render_result"] = render_result
        _emit_event(
            out_dir,
            "render.end",
            round_index=round_index,
            status="failed",
            fail_type=render_result["fail_type"],
            error=render_result["message"],
        )
    return state


def evaluate_image_node(state: WorkflowState) -> WorkflowState:
    """视觉评估节点：把 render_result 转成下一轮可用的反馈。"""

    out_dir = Path(state["out_dir"])
    round_index = state.get("round_index", 0)
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    _emit_event(out_dir, "vision.start", round_index=round_index)
    if state.get("status") == "failed":
        vision_result = {
            "usable": False,
            "score": 1,
            "defects": ["skipped"],
            "suggested_constraint_feedback": state.get("error", "previous workflow step failed"),
        }
        _write_json(round_dir / "vision_result.json", vision_result)
        state["vision_result"] = vision_result
        _emit_event(
            out_dir,
            "vision.end",
            round_index=round_index,
            status="skipped",
            usable=False,
        )
        return state
    try:
        vision_result = _evaluate_image(
            state["request"],
            state["render_result"],
            out_dir,
            state.get("skills_context") or load_skills_context(),
        )
    except ModelPoolError as exc:
        vision_result = {
            "usable": False,
            "score": 1,
            "defects": ["vision_model_pool_failed"],
            "suggested_constraint_feedback": redact_secrets(exc),
            "model_attempts": exc.attempts,
        }
    except Exception as exc:
        vision_result = {
            "usable": False,
            "score": 1,
            "defects": ["vision_evaluation_failed"],
            "suggested_constraint_feedback": redact_secrets(exc),
        }
    _write_json(round_dir / "vision_result.json", vision_result)
    state["vision_result"] = vision_result
    _emit_event(
        out_dir,
        "vision.end",
        round_index=round_index,
        status="ok"
        if vision_result.get("usable")
        or "model_used" in vision_result
        or state.get("render_result", {}).get("success") is False
        else "failed",
        usable=vision_result.get("usable", False),
        score=vision_result.get("score", ""),
        model_used=vision_result.get("model_used", ""),
        defects=vision_result.get("defects", []),
    )
    return state


def update_history_node(state: WorkflowState) -> WorkflowState:
    """把本轮产物追加进 history，并决定成功、失败或进入下一轮。"""

    history = state.get("history", [])
    history.append(
        {
            "round_index": state.get("round_index", 0),
            "scene_payload": state.get("scene_payload", {}),
            "render_result": state.get("render_result", {}),
            "vision_result": state.get("vision_result", {}),
        }
    )
    state["history"] = history
    if state.get("vision_result", {}).get("usable"):
        state["status"] = "ok"
    elif state.get("round_index", 0) >= state.get("max_retries", 3):
        state["status"] = "failed"
        state["error"] = "max_retries_exhausted"
    else:
        state["round_index"] = state.get("round_index", 0) + 1
    return state


def should_continue(state: WorkflowState) -> str:
    return "done" if state.get("status") in {"ok", "failed"} else "retry"


def _collect_model_attempts(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    attempts: List[Dict[str, Any]] = []
    for round_item in history:
        scene_payload = round_item.get("scene_payload", {})
        vision_result = round_item.get("vision_result", {})
        attempts.extend(scene_payload.get("model_attempts", []))
        attempts.extend(vision_result.get("model_attempts", []))
    return attempts


def finalize_node(state: WorkflowState) -> WorkflowState:
    """收尾节点：写出最终 Wolfram、renderer spec、diagram spec 和总结果。

    即使前面状态是 failed，也会尽量编译已有信息，方便调用方或人工排查失败原因。
    """

    out_dir = Path(state["out_dir"])
    history = state.get("history", [])
    final_round = history[-1] if history else {}
    scene_payload = final_round.get("scene_payload", {})
    render_result = final_round.get("render_result", {})

    if scene_payload.get("scene_code"):
        (out_dir / "final_geometric_scene.wl").write_text(
            scene_payload["scene_code"], encoding="utf-8"
        )
        if scene_payload.get("solution_reuse"):
            (out_dir / "final_annotated_scene.wl").write_text(
                scene_payload["scene_code"], encoding="utf-8"
            )
    renderer_spec = _compile_renderer_spec(
        state.get("request", {}),
        scene_payload,
        render_result,
    )
    _write_json(out_dir / "final_renderer_spec.json", renderer_spec)
    final_spec = {
        "schema_version": "gsb-diagram-spec/v1",
        "status": state.get("status", "failed"),
        "diagram_spec": scene_payload.get("diagram_spec", {}),
        "renderer_spec": renderer_spec,
        "renderer_spec_path": "final_renderer_spec.json",
        "scene_code_path": "final_geometric_scene.wl",
        "image_path": render_result.get("image_path"),
        "round_count": len(history),
    }
    if scene_payload.get("solution_reuse"):
        final_spec["solution_reuse"] = scene_payload.get("solution_reuse")
        final_spec["solution_reuse_check"] = render_result.get("solution_reuse_check", {})
    _write_json(out_dir / "final_diagram_spec.json", final_spec)

    result = {
        "status": state.get("status", "failed"),
        "error": state.get("error", ""),
        "out_dir": str(out_dir),
        "final_diagram_spec": "final_diagram_spec.json",
        "final_renderer_spec": "final_renderer_spec.json",
        "final_image_path": render_result.get("image_path"),
        "skills_used": SKILL_SETS,
        "model_attempts": _collect_model_attempts(history),
        "rounds": history,
    }
    if scene_payload.get("solution_reuse"):
        result["solution_reuse"] = scene_payload.get("solution_reuse")
        result["solution_reuse_check"] = render_result.get("solution_reuse_check", {})
    _write_json(out_dir / "workflow_result.json", result)
    _emit_event(
        out_dir,
        "workflow.finalize",
        status=result["status"],
        error=result.get("error", ""),
        final_image_path=result.get("final_image_path") or "",
        round_count=len(history),
    )
    return state


def _run_without_langgraph(state: WorkflowState) -> WorkflowState:
    """当前默认编排：generate -> render -> evaluate -> history 的重试循环。"""

    while True:
        state = generate_scene_node(state)
        state = render_wolfram_node(state)
        state = evaluate_image_node(state)
        state = update_history_node(state)
        if should_continue(state) == "done":
            return finalize_node(state)


def build_graph():
    # Phase 1 keeps orchestration in a simple Python loop. The step functions
    # above can be mapped to LangGraph nodes later without changing contracts.
    return None


def run_workflow(request: Dict[str, Any], out_dir: Path, request_path: Path) -> Dict[str, Any]:
    """执行完整 workflow。

    这是 CLI --action run 的主入口：准备输出目录、复制原始 request、初始化
    WorkflowState，然后交给图编排或当前的 Python 循环编排。
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rounds").mkdir(exist_ok=True)
    shutil.copy2(request_path, out_dir / "request.json")

    state: WorkflowState = {
        "request": request,
        "out_dir": str(out_dir),
        "round_index": 0,
        "max_retries": int(request.get("max_retries", 3)),
        "history": [],
        "skills_context": load_skills_context(),
    }
    app = build_graph()
    if app is None:
        final_state = _run_without_langgraph(state)
    else:
        final_state = app.invoke(state)

    result_path = out_dir / "workflow_result.json"
    if result_path.exists():
        return _read_json(result_path)
    return {
        "status": final_state.get("status", "failed"),
        "error": final_state.get("error", "workflow_result_missing"),
        "out_dir": str(out_dir),
    }


def generate_candidate_action(
    request: Dict[str, Any],
    out_dir: Path,
    round_index: int,
    history_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """只执行生成步骤，供调试或外部编排逐步调用。"""

    history: List[Dict[str, Any]] = []
    if history_path and history_path.exists():
        loaded = _read_json(history_path)
        if isinstance(loaded.get("rounds"), list):
            history = loaded["rounds"]
        elif isinstance(loaded.get("history"), list):
            history = loaded["history"]
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    if _is_solution_request(request):
        payload = _solution_scene_payload(
            request,
            out_dir,
            history,
            round_index,
            load_skills_context(),
        )
    else:
        payload = _text_model_json(
            request,
            history,
            round_index,
            load_skills_context(),
        )
    _write_json(round_dir / "scene_payload.json", payload)
    return {
        "status": "ok",
        "action": "generate",
        "round_index": round_index,
        "scene_payload_path": str(round_dir / "scene_payload.json"),
        "skills_used": SKILL_SETS["generate"],
    }


def render_candidate_action(
    request: Dict[str, Any],
    scene_payload_path: Path,
    out_dir: Path,
    round_index: int,
) -> Dict[str, Any]:
    """只执行 Wolfram 求解/渲染步骤，输入上一阶段的 scene_payload.json。"""

    payload = _read_json(scene_payload_path)
    if "scene_code" not in payload:
        raise ValueError("scene_payload missing scene_code")
    render_result = _render_scene(payload["scene_code"], out_dir, round_index, request)
    reuse_check = _solution_reuse_check(request, out_dir, render_result)
    if reuse_check:
        render_result["solution_reuse_check"] = reuse_check
        if not reuse_check.get("locked_points_same", False):
            render_result["success"] = False
            render_result["fail_type"] = "solution_base_point_drift"
            render_result["message"] = "Solution diagram did not preserve prompt point coordinates"
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    _write_json(round_dir / "render_result.json", render_result)
    return {
        "status": "ok" if render_result.get("success") else "failed",
        "action": "render",
        "round_index": round_index,
        "render_result_path": str(round_dir / "render_result.json"),
        "render_result": render_result,
    }


def evaluate_image_action(
    request: Dict[str, Any],
    render_result_path: Path,
    out_dir: Path,
    round_index: int,
) -> Dict[str, Any]:
    """只执行视觉评估步骤，输入上一阶段的 render_result.json。"""

    render_result = _read_json(render_result_path)
    vision_result = _evaluate_image(
        request,
        render_result,
        out_dir,
        load_skills_context(),
    )
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    _write_json(round_dir / "vision_result.json", vision_result)
    return {
        "status": "ok",
        "action": "evaluate",
        "round_index": round_index,
        "vision_result_path": str(round_dir / "vision_result.json"),
        "vision_result": vision_result,
        "skills_used": SKILL_SETS["evaluate"],
    }


def skill_context_action(out_dir: Path) -> Dict[str, Any]:
    """导出本 workflow 会注入 prompt 的本地 skill 上下文。"""

    context = load_skills_context()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "skills_context.json"
    _write_json(path, {"status": "ok", "skills_used": SKILL_SETS, "context": context})
    return {
        "status": "ok",
        "action": "skill_context",
        "skills_context_path": str(path),
        "skills_used": SKILL_SETS,
    }


def main() -> None:
    """命令行入口。

    run 是完整重试循环；generate/render/evaluate 是拆开的单步动作，方便人工
    调试某一轮模型输出或 Wolfram 结果。
    """

    parser = argparse.ArgumentParser(description="Run agentic GeometricScene workflow")
    parser.add_argument(
        "--action",
        choices=["run", "generate", "render", "evaluate", "skill_context"],
        default="run",
        help="workflow action; run executes the full retry loop",
    )
    parser.add_argument("--request", help="workflow request JSON path")
    parser.add_argument("--out", help="output directory")
    parser.add_argument("--round-index", type=int, default=0, help="round index for single-step actions")
    parser.add_argument("--history", help="workflow_result.json or history JSON for generate action")
    parser.add_argument("--scene-payload", help="scene_payload.json path for render action")
    parser.add_argument("--render-result", help="render_result.json path for evaluate action")
    args = parser.parse_args()

    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = _default_out_dir("workflow")

    try:
        if args.action == "skill_context":
            result = skill_context_action(out_dir)
        else:
            if not args.request:
                raise ValueError("--request is required for this action")
            request_path = Path(args.request)
            if not request_path.exists():
                raise FileNotFoundError(f"Request file not found: {request_path}")
            request = _normalize_workflow_request(_read_json(request_path))

            if args.action == "run":
                result = run_workflow(request, out_dir, request_path)
            elif args.action == "generate":
                result = generate_candidate_action(
                    request,
                    out_dir,
                    args.round_index,
                    Path(args.history) if args.history else None,
                )
            elif args.action == "render":
                if not args.scene_payload:
                    raise ValueError("--scene-payload is required for render action")
                result = render_candidate_action(
                    request,
                    Path(args.scene_payload),
                    out_dir,
                    args.round_index,
                )
            elif args.action == "evaluate":
                if not args.render_result:
                    raise ValueError("--render-result is required for evaluate action")
                result = evaluate_image_action(
                    request,
                    Path(args.render_result),
                    out_dir,
                    args.round_index,
                )
            else:
                raise ValueError(f"Unknown action: {args.action}")
    except Exception as exc:
        print(json.dumps({"status": "error", "message": redact_secrets(exc)}, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, default=_json_default))


if __name__ == "__main__":
    main()
