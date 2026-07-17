#!/usr/bin/env python3
"""Deterministic helpers and single-step tools for geometry diagram workflow."""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
import os
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

CORE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = CORE_DIR.parents[1]
sys.path.insert(0, str(CORE_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from diagram_contracts import (  # noqa: E402
    DiagramJobRequest,
    DiagramJobResult,
    DiagramModelConfig,
    GeometryRendererResult,
    GeometryRenderSpec,
    ModelAttempt,
    RenderCandidateResult,
    ScenePayload,
    WolframRenderResult,
    WorkflowRound,
)
from runtime import (  # noqa: E402
    configure_utf8_stdio,
    project_root,
    redact_secrets,
    resolve_wolfram_kernel,
    wl_dir as resolve_wl_dir,
)

configure_utf8_stdio()

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
    "scene_writer": [
        "math-geometry-diagram-renderer",
        "wolfram-geometricscene-reference",
        "dimensionless-constraints-library",
    ],
    "generate": [
        "math-geometry-diagram-renderer",
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
    "revision": [
        "diagram-human-revision",
    ],
}


def _json_default(value: object) -> str:
    return str(value)
def _model_dump_json(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value
def _dict_from_model(value: object) -> Dict[str, object]:
    dumped = _model_dump_json(value)
    if not isinstance(dumped, dict):
        raise ValueError("expected model/dict to serialize to a JSON object")
    return dumped
def _read_json(path: Path) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("workflow request must be a JSON object")
    return data
def _read_json_if_exists(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    return _read_json(path)
def _compact_string_parts(*values: object) -> str:
    return "\n".join(str(value).strip() for value in values if str(value or "").strip())
def _normalize_workflow_request(request: Dict[str, object]) -> Dict[str, object]:
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

    request_model = DiagramJobRequest.model_validate(request)
    request = request_model.model_dump(mode="json", by_alias=True)
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
            "max_retries": engine_options.get("max_retries", 0),
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
def _write_json(path: Path, data: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_model_dump_json(data), f, ensure_ascii=False, indent=2, default=_json_default)
def _emit_event(out_dir: Path, event: str, **fields: object) -> None:
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
def _agent_cwd() -> Path:
    return SCRIPTS_DIR
def _skills_root() -> Path:
    return _project_root() / ".codex" / "skills"
def _skill_path(skill_name: str) -> Path:
    embedded = _skills_root() / skill_name / "SKILL.md"
    if embedded.exists():
        return embedded
    repository_skill = SCRIPTS_DIR.parents[1] / ".codex" / "skills" / skill_name / "SKILL.md"
    return repository_skill
def _skill_inputs_for_group(group: str) -> List[Dict[str, str]]:
    skills: List[Dict[str, str]] = []
    for name in SKILL_SETS.get(group, []):
        path = _skill_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Required Codex skill not found: {path}")
        skills.append({"name": name, "path": str(path)})
    return skills
def _all_skill_inputs(*, include_revision: bool = False) -> List[Dict[str, str]]:
    if not include_revision:
        return _skill_inputs_for_group("scene_writer")
    skills: List[Dict[str, str]] = []
    seen: set[str] = set()
    groups = ["generate", "evaluate", "finalize", "revision"]
    for group in groups:
        for item in _skill_inputs_for_group(group):
            if item["name"] in seen:
                continue
            seen.add(item["name"])
            skills.append(item)
    return skills
def _skill_names_for_group(group: str) -> str:
    return ", ".join(SKILL_SETS.get(group, [])) or "none"
def _all_skill_names(*, include_revision: bool = False) -> str:
    return ", ".join(
        item["name"] for item in _all_skill_inputs(include_revision=include_revision)
    )


def _skill_inputs_for_request(request: Dict[str, object]) -> List[Dict[str, str]]:
    return _all_skill_inputs(include_revision=isinstance(request.get("human_revision"), dict))
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
def _configured_value(value: object) -> bool:
    return value not in (None, "", [], {})
def _prune_empty_model_config(config: Dict[str, object]) -> Dict[str, object]:
    return {
        key: value
        for key, value in dict(config).items()
        if _configured_value(value)
    }
def _float_config(config: Dict[str, object], key: str, default: float) -> float:
    value = config.get(key)
    if not _configured_value(value):
        return float(default)
    return float(value)
def _resolved_codex_config(model_config: Dict[str, object]) -> Dict[str, object]:
    """归一化 Codex SDK 运行配置。"""
    load_local_env()
    if not isinstance(model_config, dict):
        model_config = {}
    resolved = _prune_empty_model_config(model_config)
    config_model = DiagramModelConfig.model_validate(resolved)
    config = {
        "model": config_model.model,
        "codex_model": config_model.codex_model,
        "codex_bin": config_model.codex_bin,
        "model_reasoning_effort": config_model.model_reasoning_effort,
        "service_tier": config_model.service_tier,
        "fast_mode": config_model.fast_mode,
        "codex_timeout_s": config_model.codex_timeout_s,
    }
    # Keep diagram-agent latency and runtime compatibility deterministic. A
    # per-job model config may still override these repository defaults.
    config["codex_model"] = str(
        resolved.get("codex_model")
        or resolved.get("model")
        or "gpt-5.5"
    )
    config["model_reasoning_effort"] = str(
        resolved.get("model_reasoning_effort") or "medium"
    )
    config["service_tier"] = str(resolved.get("service_tier") or "fast")
    config["fast_mode"] = bool(
        resolved.get("fast_mode")
        if resolved.get("fast_mode") is not None
        else config["service_tier"] == "fast"
    )
    # 仅在题目配置或环境变量明确指定时覆盖 SDK runtime；留空时由
    # openai_codex 选择随 SDK 安装、适配当前平台的固定版本。
    config["codex_bin"] = str(
        resolved.get("codex_bin")
        or os.environ.get("CODEX_DIAGRAM_BIN")
        or ""
    )
    config["codex_timeout_s"] = _float_config(resolved, "codex_timeout_s", 120)
    return config
def _extract_json_object(text: str) -> Dict[str, object]:
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
def _is_solution_request(request: Dict[str, object]) -> bool:
    variant = request.get("diagram_variant") or request.get("variant")
    return variant == "solution" or request.get("disclosure_policy") == "annotated"
def _solution_reuse_id(request: Dict[str, object]) -> str:
    return str(
        request.get("reuse_geometry_from")
        or request.get("reuse_from")
        or request.get("base_diagram_job_id")
        or ""
    ).strip()
def _resolve_reuse_job_dir(request: Dict[str, object], out_dir: Path) -> Path:
    explicit = request.get("reuse_geometry_dir") or request.get("base_job_dir")
    if explicit:
        path = Path(str(explicit))
        return path if path.is_absolute() else (out_dir / path).resolve()
    reuse_id = _solution_reuse_id(request)
    if not reuse_id:
        raise ValueError("solution diagram job requires reuse_geometry_from")
    return (out_dir.parent / reuse_id).resolve()
def _merge_lists(base: object, delta: object) -> List[object]:
    merged: List[object] = []
    if isinstance(base, list):
        merged.extend(base)
    if isinstance(delta, list):
        merged.extend(delta)
    elif delta not in (None, "", []):
        merged.append(delta)
    return merged
def _validate_scene_code(
    scene_code: str,
    *,
    allow_fixed_metrics: bool = False,
    coordinate_policy: str = "",
    allowed_coordinate_anchors: List[str] | None = None,
) -> None:
    """对模型生成的 Wolfram 代码做最小安全门禁。"""

    if "GeometricScene" not in scene_code:
        raise ValueError("scene_code must contain GeometricScene")
    unsupported_regions = [
        token
        for token in ("LineSegment", "Ray")
        if re.search(rf"\b{token}\s*\[", scene_code)
    ]
    if unsupported_regions:
        raise ValueError(
            "scene_code uses unsupported region constructor(s) "
            f"{unsupported_regions}; use Line for segments, InfiniteLine for full lines, "
            "and HalfLine for rays"
        )
    nested_first_argument = re.search(r"GeometricScene\s*\[\s*\{\s*\{", scene_code)
    scalar_parameter_form = re.search(
        r"GeometricScene\s*\[\s*\{\s*\{[^{}]+\}\s*,\s*\{[^{}]*\}\s*\}\s*,",
        scene_code,
    )
    if nested_first_argument and not scalar_parameter_form:
        raise ValueError(
            "scene_code must use a flat point list or the scalar-parameter form, e.g. "
            "GeometricScene[{A, B, C}, {...}] or "
            "GeometricScene[{{A, B, C}, {r}}, {...}]"
        )
    fixed_points = set(
        re.findall(
            r"\b([A-Za-z][A-Za-z0-9_]*)\s*==\s*\{\s*[^{},]+\s*,\s*[^{}]+\}",
            scene_code,
        )
    )
    allowed_anchors = set(allowed_coordinate_anchors or [])
    if coordinate_policy == "symbolic_only" and fixed_points:
        raise ValueError(
            "symbolic_only scene_code cannot fix point coordinates; use native geometric constraints"
        )
    if coordinate_policy == "allow_single_anchor" and (
        len(fixed_points) > 1 or not fixed_points.issubset(allowed_anchors)
    ):
        raise ValueError(
            "allow_single_anchor scene_code may fix only the explicitly authorized anchor"
        )
    repeated_metric_constraints = re.search(
        r"\b(?:EuclideanDistance|PlanarAngle|TriangleMeasurement|Area)\s*\[",
        scene_code,
    )
    if len(fixed_points) > 1 and repeated_metric_constraints and not allow_fixed_metrics:
        raise ValueError(
            "scene_code fixes multiple triangle vertices while also adding metric constraints; "
            "keep the points symbolic and use a baseline orientation assertion"
        )
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
def _wl_to_python(value: object) -> object:
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
def _point_label(value: object) -> str:
    label = str(value).strip()
    if "`" in label:
        label = label.rsplit("`", 1)[-1]
    return label
def _numeric_pair(value: object) -> Optional[List[float]]:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        return None
def _normalize_solver_points(parameters: object) -> Dict[str, List[float]]:
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


def _prepare_solution_reuse_context(
    request: Dict[str, object],
    out_dir: Path,
) -> Dict[str, object]:
    """Attach finalized prompt coordinates to an in-memory solution request.

    The public request artifact keeps the stable ``reuse_geometry_from`` contract.
    Normal solution generation additionally needs the actual finalized base points,
    because the Scene Writer is intentionally forbidden from reading job artifacts.
    """

    reuse_id = _solution_reuse_id(request)
    if not reuse_id:
        return dict(request)

    base_dir = _resolve_reuse_job_dir(request, out_dir)
    base_spec_path = base_dir / "final_renderer_spec.json"
    if not base_spec_path.is_file():
        raise FileNotFoundError(
            f"solution base geometry is not finalized: {base_spec_path}"
        )
    base_spec = _read_json(base_spec_path)
    raw_points = base_spec.get("points")
    if not isinstance(raw_points, dict):
        raise ValueError("solution base renderer spec has no points map")

    locked_points: Dict[str, List[float]] = {}
    for raw_name, raw_coord in raw_points.items():
        name = _point_label(raw_name)
        pair = _numeric_pair(raw_coord)
        if name and pair is not None:
            locked_points[name] = pair
    if not locked_points:
        raise ValueError("solution base renderer spec has no numeric points to lock")

    prepared = dict(request)
    prepared["locked_base_points"] = locked_points
    prepared["locked_base_point_names"] = list(locked_points)
    return prepared


def _wolfram_number(value: object) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("solution base coordinates must be finite numbers")
    text = format(number, ".17g")
    return re.sub(r"[eE]([+-]?\d+)$", r"*^\1", text)


def _solution_base_lock_constraints(locked_points: object) -> List[str]:
    if not isinstance(locked_points, dict):
        return []
    constraints: List[str] = []
    for raw_name, raw_coord in locked_points.items():
        name = str(raw_name).strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ValueError(f"unsupported Wolfram point symbol in base geometry: {name!r}")
        pair = _numeric_pair(raw_coord)
        if pair is None:
            raise ValueError(f"solution base point {name} has invalid coordinates")
        constraints.append(
            f"{name} == {{{_wolfram_number(pair[0])}, {_wolfram_number(pair[1])}}}"
        )
    return constraints


def _second_argument_list_insert_position(scene_code: str) -> tuple[int, bool]:
    """Locate the hypotheses list in one top-level GeometricScene expression."""

    match = re.search(r"\bGeometricScene\s*\[", scene_code)
    if match is None:
        raise ValueError("scene_code must contain GeometricScene")
    open_square = scene_code.find("[", match.start())
    square_depth = 1
    curly_depth = 0
    paren_depth = 0
    in_string = False
    escaped = False
    separator = -1
    for index in range(open_square + 1, len(scene_code)):
        char = scene_code[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "[":
            square_depth += 1
        elif char == "]":
            square_depth -= 1
            if square_depth == 0:
                break
        elif char == "{":
            curly_depth += 1
        elif char == "}":
            curly_depth -= 1
        elif char == "(":
            paren_depth += 1
        elif char == ")":
            paren_depth -= 1
        elif (
            char == ","
            and square_depth == 1
            and curly_depth == 0
            and paren_depth == 0
        ):
            separator = index
            break
    if separator < 0:
        raise ValueError("scene_code must provide GeometricScene hypotheses")

    second_start = separator + 1
    while second_start < len(scene_code) and scene_code[second_start].isspace():
        second_start += 1
    if second_start >= len(scene_code) or scene_code[second_start] != "{":
        raise ValueError("GeometricScene hypotheses must be a literal list")
    next_token = second_start + 1
    while next_token < len(scene_code) and scene_code[next_token].isspace():
        next_token += 1
    return second_start + 1, next_token < len(scene_code) and scene_code[next_token] != "}"


def _inject_solution_base_locks(
    scene_code: str,
    locked_points: object,
) -> str:
    constraints = [
        item
        for item in _solution_base_lock_constraints(locked_points)
        if item not in scene_code
    ]
    if not constraints:
        return scene_code
    insert_at, has_hypotheses = _second_argument_list_insert_position(scene_code)
    insertion = ", ".join(constraints)
    if has_hypotheses:
        insertion += ", "
    return scene_code[:insert_at] + insertion + scene_code[insert_at:]


def _validate_solution_base_locks(
    scene_code: str,
    request: Dict[str, object],
    scene_points: object,
) -> None:
    constraints = _solution_base_lock_constraints(request.get("locked_base_points"))
    if not constraints:
        return
    declared_points = set(_point_names(scene_points))
    missing_points = [
        name
        for name in request.get("locked_base_point_names", [])
        if str(name) not in declared_points
    ]
    if missing_points:
        raise ValueError(
            "solution scene omits locked base point(s): " + ", ".join(missing_points)
        )
    missing_constraints = [item for item in constraints if item not in scene_code]
    if missing_constraints:
        raise ValueError(
            "solution scene is missing Host-injected base point lock(s): "
            + "; ".join(missing_constraints)
        )
def _compact_list(value: object) -> List[object]:
    if isinstance(value, list):
        return [item for item in value if item not in ("", None, [])]
    if value in ("", None):
        return []
    return [value]
def _point_names(value: object) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    names = [_point_label(item) for item in value if isinstance(item, (str, int, float))]
    return [name for name in names if name]
def _segment_from(value: object) -> Optional[Dict[str, str]]:
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
def _polygon_from(value: object) -> Optional[Dict[str, object]]:
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
def _dedupe_dicts(items: List[Dict[str, object]], key_fn) -> List[Dict[str, object]]:
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
    polygons: List[Dict[str, object]],
    markers: List[Dict[str, object]],
    source: object,
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
def _normalize_marker(marker: Dict[str, object]) -> Dict[str, object]:
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
    request: Dict[str, object],
    scene_payload: Dict[str, object],
    render_result: Dict[str, object],
) -> Dict[str, object]:
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
    polygons: List[Dict[str, object]] = []
    markers: List[Dict[str, object]] = []
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

    return _dict_from_model(GeometryRenderSpec.model_validate({
        "schema_version": "geometry-render-spec/v1",
        "status": "ready" if points else "missing_coordinates",
        "type": diagram_spec.get("type")
        or request.get("diagram_type")
        or request.get("diagram_intent")
        or "synthetic_geometry",
        "render_profile": request.get("render_profile") or {},
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
    }))
def _render_scene(
    scene_code: str,
    out_dir: Path,
    round_index: int,
    request: Dict[str, object],
) -> Dict[str, object]:
    """求解单轮 GeometricScene，并按需生成 Wolfram 调试 PNG。

    主进程只负责准备 round 目录、启动 worker、执行硬超时和校验 PNG 是否真的
    生成；Wolfram 相关调用都在 _render_worker 里完成。
    """

    execution_plan = request.get("execution_plan")
    if not isinstance(execution_plan, dict):
        execution_plan = {}
    _validate_scene_code(
        scene_code,
        allow_fixed_metrics=bool(_solution_reuse_id(request)),
        coordinate_policy=str(execution_plan.get("coordinate_policy") or ""),
        allowed_coordinate_anchors=[
            str(value) for value in (execution_plan.get("allowed_coordinate_anchors") or [])
        ],
    )
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
        return _dict_from_model(WolframRenderResult.model_validate({
            "success": False,
            "fail_type": "host_watchdog_timeout",
            "message": f"Wolfram render exceeded {hard_timeout_s}s",
            "image_path": image_rel,
            "render_image_requested": render_image,
        }))

    if queue.empty():
        return _dict_from_model(WolframRenderResult.model_validate({
            "success": False,
            "fail_type": "worker_no_result",
            "message": "Wolfram worker returned no result",
            "image_path": image_rel,
            "render_image_requested": render_image,
        }))

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
    return _dict_from_model(WolframRenderResult.model_validate(result))
def _solution_reuse_check(
    request: Dict[str, object],
    out_dir: Path,
    render_result: Dict[str, object],
    tolerance: float = 1e-5,
) -> Dict[str, object]:
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
    def canonicalize_parameter(name: str, expected_pair: List[float]) -> None:
        parameters = render_result.get("parameters")
        if isinstance(parameters, dict):
            for raw_name, raw_coord in list(parameters.items()):
                if _point_label(raw_name) == name and _numeric_pair(raw_coord) is not None:
                    parameters[raw_name] = list(expected_pair)
                    return
        if isinstance(parameters, list):
            for item in parameters:
                if isinstance(item, dict):
                    for raw_name, raw_coord in list(item.items()):
                        if _point_label(raw_name) == name and _numeric_pair(raw_coord) is not None:
                            item[raw_name] = list(expected_pair)
                            return
                elif isinstance(item, list) and len(item) == 2:
                    if _point_label(item[0]) == name and _numeric_pair(item[1]) is not None:
                        item[1] = list(expected_pair)
                        return

    drift: List[Dict[str, object]] = []
    missing: List[str] = []
    canonicalization_candidates: Dict[str, List[float]] = {}
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
        coordinate_scale = max(abs(expected_pair[0]), abs(expected_pair[1]), 1.0)
        numeric_tolerance = max(tolerance, 5e-9 * coordinate_scale)
        if dx > numeric_tolerance or dy > numeric_tolerance:
            drift.append(
                {
                    "point": str(name),
                    "expected": expected_pair,
                    "actual": actual_pair,
                    "max_abs_delta": max(dx, dy),
                    "tolerance": numeric_tolerance,
                }
            )
        else:
            canonicalization_candidates[str(name)] = expected_pair
    canonicalized: List[str] = []
    if not drift and not missing:
        for name, expected_pair in canonicalization_candidates.items():
            canonicalize_parameter(name, expected_pair)
            canonicalized.append(name)
    return {
        "reuse_geometry_from": _solution_reuse_id(request),
        "base_job_dir": str(base_dir),
        "locked_point_count": len(base_points),
        "locked_points_same": not drift and not missing,
        "drift": drift,
        "missing": missing,
        "canonicalized_points": canonicalized,
    }
def _collect_model_attempts(history: List[Dict[str, object]]) -> List[Dict[str, object]]:
    attempts: List[Dict[str, object]] = []
    for round_item in history:
        scene_payload = round_item.get("scene_payload", {})
        vision_result = round_item.get("vision_result", {})
        attempts.extend(scene_payload.get("model_attempts", []))
        attempts.extend(vision_result.get("model_attempts", []))
    return [_dict_from_model(ModelAttempt.model_validate(item)) for item in attempts]
def _validate_final_agent_artifacts(out_dir: Path) -> Dict[str, object]:
    result_path = out_dir / "workflow_result.json"
    if not result_path.exists():
        raise FileNotFoundError(f"missing workflow_result.json: {result_path}")
    result = _read_json(result_path)
    DiagramJobResult.model_validate(result)
    if result.get("status") != "ok":
        raise ValueError(f"workflow_result status is not ok: {result.get('status')}")

    spec_rel = str(result.get("final_renderer_spec") or "final_renderer_spec.json")
    spec_path = out_dir / spec_rel
    if not spec_path.exists():
        raise FileNotFoundError(f"missing final_renderer_spec: {spec_path}")
    renderer_spec = _read_json(spec_path)
    GeometryRenderSpec.model_validate(renderer_spec)

    renderer_result_path = out_dir / "renderer_result.json"
    if not renderer_result_path.exists():
        raise FileNotFoundError(f"missing renderer_result.json: {renderer_result_path}")
    renderer_result = _read_json(renderer_result_path)
    GeometryRendererResult.model_validate(renderer_result)
    if renderer_result.get("status") != "ok":
        raise ValueError(f"renderer_result status is not ok: {renderer_result.get('status')}")

    fragment_rel = (
        renderer_result.get("tikz_fragment_path")
        or renderer_result.get("tikz_source_path")
        or result.get("final_tikz_fragment_path")
        or ""
    )
    fragment_path = out_dir / str(fragment_rel)
    if not fragment_rel or not fragment_path.exists() or fragment_path.stat().st_size == 0:
        raise FileNotFoundError(f"missing final TikZ fragment: {fragment_rel}")

    labels = renderer_spec.get("labels") if isinstance(renderer_spec.get("labels"), dict) else {}
    for name, label in labels.items():
        bad_name = _bad_label_text(name)
        bad_label = _bad_label_text(label)
        if bad_name or bad_label:
            raise ValueError(bad_name or bad_label)
    return result
def _write_failed_workflow_result(
    out_dir: Path,
    request: Dict[str, object],
    fail_type: str,
    message: str,
) -> Dict[str, object]:
    result = _dict_from_model(DiagramJobResult.model_validate({
        "schema_version": "diagram-job-result/v2",
        "job_id": request.get("diagram_job_id") or request.get("job_id", ""),
        "status": "failed",
        "fail_type": fail_type,
        "message": redact_secrets(message),
        "out_dir": str(out_dir),
        "request": "request.json",
        "workflow_events": "workflow_events.jsonl",
        "scene_payload": "scene_payload.json",
        "final_diagram_spec": "final_diagram_spec.json",
        "final_renderer_spec": "final_renderer_spec.json",
        "wolfram": {"success": False},
        "model": {"text_model_used": "codex-diagram-agent", "attempts": []},
        "policy_warnings": [],
        "skills_used": SKILL_SETS,
        "model_attempts": [],
        "rounds": [],
    }))
    _write_json(out_dir / "workflow_result.json", result)
    _emit_event(out_dir, "workflow.finalize", status="failed", error=result["message"])
    return result
def render_candidate_action(
    request: Dict[str, object],
    scene_payload_path: Path,
    out_dir: Path,
    round_index: int,
) -> Dict[str, object]:
    """只执行 Wolfram 求解/渲染步骤，输入上一阶段的 scene_payload.json。"""

    request = _prepare_solution_reuse_context(request, out_dir)
    payload = _read_json(scene_payload_path)
    scene_payload = ScenePayload.model_validate(payload)
    locked_scene_code = _inject_solution_base_locks(
        scene_payload.scene_code,
        request.get("locked_base_points"),
    )
    reuse_metadata = dict(scene_payload.solution_reuse)
    if request.get("locked_base_points"):
        reuse_metadata.update(
            {
                "reuse_geometry_from": _solution_reuse_id(request),
                "lock_strategy": "host_injected_exact_coordinates",
                "locked_base_points": request["locked_base_points"],
            }
        )
    normalized_payload = scene_payload.model_dump(mode="json", by_alias=True)
    normalized_payload["scene_code"] = locked_scene_code
    normalized_payload["solution_reuse"] = reuse_metadata
    scene_payload = ScenePayload.model_validate(normalized_payload)
    _validate_solution_base_locks(
        scene_payload.scene_code,
        request,
        scene_payload.points,
    )
    _write_json(scene_payload_path, scene_payload)
    render_result = _render_scene(scene_payload.scene_code, out_dir, round_index, request)
    reuse_check = _solution_reuse_check(request, out_dir, render_result)
    if reuse_check:
        render_result["solution_reuse_check"] = reuse_check
        if not reuse_check.get("locked_points_same", False):
            render_result["success"] = False
            render_result["fail_type"] = "solution_base_point_drift"
            render_result["message"] = "Solution diagram did not preserve prompt point coordinates"
        render_result = _dict_from_model(WolframRenderResult.model_validate(render_result))
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    _write_json(round_dir / "render_result.json", render_result)
    result = RenderCandidateResult(
        status="ok" if render_result.get("success") else "failed",
        action="render",
        round_index=round_index,
        render_result_path=str(round_dir / "render_result.json"),
        render_result=WolframRenderResult.model_validate(render_result),
    )
    return _dict_from_model(result)
def compile_spec_action(
    request: Dict[str, object],
    scene_payload_path: Path,
    render_result_path: Path,
    out_dir: Path,
    round_index: int,
) -> Dict[str, object]:
    scene_payload = _read_json(scene_payload_path)
    render_result = _read_json(render_result_path)
    renderer_spec = _compile_renderer_spec(request, scene_payload, render_result)
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    round_dir.mkdir(parents=True, exist_ok=True)
    spec_path = round_dir / "final_renderer_spec.json"
    _write_json(spec_path, renderer_spec)
    return {
        "status": "ok" if renderer_spec.get("status") == "ready" else "failed",
        "action": "compile_spec",
        "round_index": round_index,
        "renderer_spec_path": str(spec_path),
        "renderer_spec": renderer_spec,
    }
def _relative_path(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def _bad_label_text(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("text", "")
    text = str(value)
    forbidden = ["ref", "GeometricPoint", "[[", "]]", "C[\"", "Centroid"]
    if any(item in text for item in forbidden):
        return f"bad serialized label text: {text[:80]}"
    if len(text) > 24:
        return f"label text too long: {text[:80]}"
    return ""


def finalize_round_action(
    request: Dict[str, object],
    scene_payload_path: Path,
    render_result_path: Path,
    renderer_spec_path: Path,
    renderer_result_path: Path,
    audit_result_path: Path,
    out_dir: Path,
    round_index: int,
) -> Dict[str, object]:
    scene_payload = _read_json(scene_payload_path)
    render_result = _read_json(render_result_path)
    renderer_spec = _read_json(renderer_spec_path)
    renderer_result = _read_json(renderer_result_path)
    audit_result = _read_json(audit_result_path)
    if audit_result.get("status") != "pass":
        raise ValueError(f"cannot finalize blocked round: {audit_result.get('issues', [])}")

    human_revision = request.get("human_revision")
    if isinstance(human_revision, dict):
        requested_round = int(human_revision.get("requested_round", -1))
        base_round = int(human_revision.get("base_round", -1))
        if round_index != requested_round:
            raise ValueError(
                f"human revision must finalize requested Round {requested_round}, got {round_index}"
            )
        evidence_path = out_dir / "rounds" / f"round_{round_index}" / "visual_inspection.json"
        evidence = _read_json_if_exists(evidence_path)
        current_preview = (
            out_dir / "rounds" / f"round_{round_index}" / "rendered" / "prompt.preview.png"
        )
        base_preview = (
            out_dir / "rounds" / f"round_{base_round}" / "rendered" / "prompt.preview.png"
        )
        if (
            evidence.get("status") != "pass"
            or evidence.get("base_round") != base_round
            or evidence.get("requested_round") != requested_round
            or int(evidence.get("inspection_count", 0)) < 2
        ):
            raise ValueError(
                "cannot finalize human revision before opening the base and current preview images"
            )
        for label, preview, field in (
            ("base", base_preview, "base_preview_sha256"),
            ("current", current_preview, "current_preview_sha256"),
        ):
            if not preview.is_file():
                raise ValueError(f"cannot finalize human revision without {label} preview: {preview}")
            digest = hashlib.sha256(preview.read_bytes()).hexdigest()
            if evidence.get(field) != digest:
                raise ValueError(
                    f"cannot finalize human revision: {label} preview changed after visual inspection"
                )

    out_dir.mkdir(parents=True, exist_ok=True)
    round_dir = out_dir / "rounds" / f"round_{round_index}"
    rendered_dir = round_dir / "rendered"
    if rendered_dir.exists():
        shutil.copytree(rendered_dir, out_dir / "rendered", dirs_exist_ok=True)

    (out_dir / "final_geometric_scene.wl").write_text(
        str(scene_payload.get("scene_code", "")),
        encoding="utf-8",
    )
    _write_json(out_dir / "scene_payload.json", scene_payload)
    _write_json(out_dir / "final_renderer_spec.json", renderer_spec)
    _write_json(out_dir / "audit_result.json", audit_result)
    renderer_result["renderer_spec"] = "final_renderer_spec.json"
    _write_json(out_dir / "renderer_result.json", renderer_result)

    final_spec = {
        "schema_version": "gsb-diagram-spec/v1",
        "status": "ok",
        "diagram_spec": scene_payload.get("diagram_spec", {}),
        "renderer_spec": renderer_spec,
        "renderer_spec_path": "final_renderer_spec.json",
        "scene_code_path": "final_geometric_scene.wl",
        "image_path": render_result.get("image_path", ""),
        "round_count": round_index + 1,
        "selected_round": round_index,
        "audit_result": _relative_path(audit_result_path, out_dir),
    }
    _write_json(out_dir / "final_diagram_spec.json", final_spec)

    rounds: List[Dict[str, object]] = []
    for idx in range(round_index + 1):
        item_dir = out_dir / "rounds" / f"round_{idx}"
        item_scene = _read_json_if_exists(item_dir / "scene_payload.json")
        item_render = _read_json_if_exists(item_dir / "render_result.json")
        item_audit = _read_json_if_exists(item_dir / "audit_result.json")
        issues = item_audit.get("issues", []) if isinstance(item_audit.get("issues"), list) else []
        rounds.append(
            _dict_from_model(WorkflowRound.model_validate({
                "round_index": idx,
                "scene_payload": item_scene,
                "render_result": item_render,
                "vision_result": {
                    "usable": item_audit.get("status") == "pass",
                    "score": "" if item_audit else 1,
                    "defects": issues,
                    "suggested_constraint_feedback": "; ".join(str(issue) for issue in issues),
                    "evaluation_mode": "agent_audit",
                },
            }))
        )

    model_attempts = _collect_model_attempts(rounds)
    workflow_result = _dict_from_model(DiagramJobResult.model_validate({
        "schema_version": "diagram-job-result/v2",
        "job_id": request.get("diagram_job_id") or request.get("job_id", ""),
        "status": "ok",
        "fail_type": "",
        "message": "",
        "out_dir": str(out_dir),
        "request": "request.json",
        "workflow_events": "workflow_events.jsonl",
        "scene_payload": "scene_payload.json",
        "final_diagram_spec": "final_diagram_spec.json",
        "final_renderer_spec": "final_renderer_spec.json",
        "final_tikz_fragment_path": renderer_result.get("tikz_fragment_path", ""),
        "wolfram": {
            "success": bool(render_result.get("success")),
            "solve_time_s": render_result.get("solve_time_s", 0) or 0,
            "seed": render_result.get("seed"),
        },
        "model": {
            "text_model_used": scene_payload.get("model_used", "codex-diagram-agent"),
            "attempts": model_attempts,
        },
        "policy_warnings": [],
        "skills_used": SKILL_SETS,
        "model_attempts": model_attempts,
        "rounds": rounds,
    }))
    _write_json(out_dir / "workflow_result.json", workflow_result)
    _emit_event(
        out_dir,
        "workflow.finalize",
        status="ok",
        final_tikz_fragment_path=workflow_result.get("final_tikz_fragment_path", ""),
        round_count=round_index + 1,
    )
    return {
        "status": "ok",
        "action": "finalize_round",
        "round_index": round_index,
        "workflow_result_path": str(out_dir / "workflow_result.json"),
    }
def skill_context_action(out_dir: Path) -> Dict[str, object]:
    """导出本 workflow 会交给 Codex SDK 的 skill manifest，不读取 skill 正文。"""

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "skills_manifest.json"
    manifest = {
        group: _skill_inputs_for_group(group)
        for group in SKILL_SETS
    }
    _write_json(path, {"status": "ok", "skills_used": SKILL_SETS, "skill_inputs": manifest})
    return {
        "status": "ok",
        "action": "skill_context",
        "skills_manifest_path": str(path),
        "skills_used": SKILL_SETS,
    }
