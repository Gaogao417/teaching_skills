#!/usr/bin/env python3
"""FastAPI service for reviewing formal question banks and staging exam papers."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field


PACKAGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    AssetClassificationIssue,
    AssetClassificationResolution,
    IssueResolution,
    ReviewIssue,
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
    unresolved_issues,
)
from triangle_candidate_review_adapter import (  # noqa: E402
    BANK_ID as TRIANGLE_CANDIDATE_BANK_ID,
    TriangleCandidateReviewStore,
)
import explanations_ai  # noqa: E402
from explanations_ai import AiAssistError  # noqa: E402
import teaching_approach as ta  # noqa: E402
import canonical_export as ce  # noqa: E402
from teaching_approach import TeachingApproachError  # noqa: E402
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_BANK_ROOT = REPO_ROOT / "artifacts" / "题库"
DEFAULT_STAGING_ROOT = REPO_ROOT / "artifacts" / "试卷整理"
DEFAULT_NUMBER_REVIEW_URL = "http://127.0.0.1:8876/"
DEFAULT_TRIANGLE_CANDIDATES = PACKAGE_DIR / "data" / "triangle-cosine-question-candidates.yaml"
DEFAULT_TRIANGLE_QUESTION_REVIEW = PACKAGE_DIR / "data" / "triangle-cosine-question-review.yaml"
REVIEW_SCHEMA = "math_exam_item_review/v1"
SOURCE_SCHEMA = "math_exam_item_source/v1"
PAPER_SCHEMA = "math_exam_paper/v1"
# 小题讲解/解答 sidecar：讲解与解答以小题为单位成对存放，批准后导出 teaching-tools
# blueprint candidate。文件在 items/<item>/explanations.yaml，录音资产在 assets/explanations/。
EXPLANATIONS_SCHEMA = "math_item_explanations/v1"
EXPLANATIONS_FILE = "explanations.yaml"
EXPLANATIONS_AUDIO_DIR = "assets/explanations"
QUESTION_TYPES = {"choice", "fillin", "problem", "short_answer"}
PREVIEW_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
EDITABLE_IMAGE_TARGETS = {
    "question_evidence",
    "prompt",
    "official_solution",
    "solution_step",
}
MAX_PASTED_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PASTED_IMAGE_PIXELS = 40_000_000

# paper.id 形如 <YEAR>-<DISTRICT>-<TYPE>[-<SUFFIX>]（例 2025-JINGAN-YIMO）。
# TYPE token → 中文试卷类型；MIDTERM/ZHONGKAO 数据中暂无，留作前瞻枚举。
EXAM_TYPE_TOKENS: dict[str, str] = {
    "YIMO": "一模",
    "ERMO": "二模",
    "MIDTERM": "期中",
    "TERM": "期末",
    "ZHONGKAO": "中考",
}
_EXAM_TYPE_PATTERN = re.compile(
    r"(?P<type>YIMO|ERMO|MIDTERM|TERM|ZHONGKAO)\b",
)
# 截断 -DOC-BENCHMARK 这类后缀；多区（BAOSHAN-JIADING）合并保留。
_PAPER_ID_SUFFIX_NOISE = re.compile(
    r"-(?:DOC-BENCHMARK|BENCHMARK|OFFICIAL|SAMPLE)(?=-|$|$)",
)


def parse_paper_id(paper_id: str) -> dict[str, str]:
    """从 paper.id 解析 year/exam_type/district。

    兼容：``2025-JINGAN-YIMO``、``GEN-TERM``（无 year/district）、
    ``2012-BAOSHAN-JIADING-ERMO``（多 district）、
    ``2012-YANGPU-ERMO-DOC-BENCHMARK``（后缀噪声）。
    """
    raw = (paper_id or "").strip()
    if not raw:
        return {"year": "", "exam_type": "", "district": ""}
    cleaned = _PAPER_ID_SUFFIX_NOISE.sub("", raw)
    match = _EXAM_TYPE_PATTERN.search(cleaned)
    if not match:
        return {"year": "", "exam_type": "", "district": ""}
    exam_type = EXAM_TYPE_TOKENS[match.group("type")]
    head = cleaned[: match.start()].rstrip("-")
    tail = cleaned[match.end():].lstrip("-")
    year = ""
    districts: list[str] = []
    for token in head.split("-") if head else []:
        if token.isdigit() and len(token) == 4:
            year = token
        elif token and token != "GEN":
            districts.append(token)
    if tail:
        districts.append(tail)
    return {
        "year": year,
        "exam_type": exam_type,
        "district": "-".join(districts),
    }


@dataclass(frozen=True)
class BankRecord:
    bank_id: str
    directory: Path
    manifest: dict[str, Any]
    kind: Literal["formal_bank", "staging_exam"] = "formal_bank"
    assignment_path: Path | None = None
    crop_manifest_path: Path | None = None


# Catalog 读模型快照（§4.1）：不可变，读侧只拿引用，写侧构造新对象后原子替换。
# 一个 snapshot 同时承载 summaries、facets、errors、整卷 detail、AssetIndex，让常态
# 读请求全部 O(1) 内存命中，写后通过 _invalidate_bank 精准重建受影响 bank 再整体替换。
@dataclass(frozen=True)
class CatalogSnapshot:
    generation: int
    records_by_id: dict[str, BankRecord]
    summaries: list[dict[str, Any]]
    summaries_by_id: dict[str, dict[str, Any]]
    facets: dict[str, list[str]]
    errors: list[str]
    # 整卷 detail（含 items），供 /api/banks/{id} 与图片写操作回取单题使用。
    details_by_bank: dict[str, dict[str, Any]]
    items_by_bank_item: dict[tuple[str, str], dict[str, Any]]
    # AssetIndex（§8.4）：value = (path, mtime_ns)，mtime_ns 用于 ?v= 缓存破坏。
    asset_paths: dict[tuple[str, str, str], tuple[Path, int]]
    source_page_paths: dict[tuple[str, str, str, int], tuple[Path, int]]
    # 粗粒度新鲜度指纹（§5.4）：bank_id → 该 bank 关键文件 mtime_ns 的汇总哈希。
    # 详情/资产路由在返回缓存前 stat 受影响 bank 的几份关键文件，与快照里的指纹比对，
    # 不一致就精准重建该 bank（catch 外部脚本直接改 source.yaml/review.yaml 这类写入，
    # 它们不会触发服务端 _invalidate_bank）。仅 stat 单 bank，不退化成 O(items) 全扫。
    bank_fingerprints: dict[str, str] = field(default_factory=dict)
    # .catalog-version mtime_ns（§5.3 快速路径）：受控 writer bump 后变化，比指纹层少
    # stat 很多文件。bank 目录下没有该文件则不在此 dict（退化到指纹层）。
    catalog_versions: dict[str, int] = field(default_factory=dict)


class ReviewNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=4000)


class ApproachCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subquestion_id: str = Field(min_length=1)
    title: str = Field(default="", max_length=200)


class ApproachUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    explanation_text: str | None = None
    solution_text: str | None = None


class ExplanationGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["explanation", "solution"]


class TeachingApproachCreate(BaseModel):
    """Phase 3 + ADR-005：新建教学策略（part 级绑定，空 = 整题/无小问题）。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    author: str = Field(default="", max_length=100)
    part_id: str = Field(default="", max_length=3)


class TeachingApproachUpdate(BaseModel):
    """Phase 3：编辑 title/goal/entry_signal/steps/part_id；steps 整体替换并重排 step_id。

    任何实际改动都会：批准态回到 draft、追加 manual_edit_note（P3-03/P3-06）。
    """

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    goal: str | None = None
    entry_signal: str | None = None
    steps: list[dict[str, Any]] | None = None
    part_id: str | None = Field(default=None, max_length=3)
    editor: str = Field(default="question-bank-review-ui", max_length=100)


class TeachingStepsInitRequest(BaseModel):
    """P3-05：从 assignment teaching/solution_steps 初始化 TeachingStep 草稿。"""

    model_config = ConfigDict(extra="forbid")

    use_ai: bool = True
    replace: bool = False


class TeachingApproachApproveRequest(BaseModel):
    """P3-07：批准冻结 ApprovedTeachingApproach.v1（reviewer + review note 必留）。"""

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1, max_length=100)
    review_note: str = Field(default="", max_length=4000)


class ReviewDecision(ReviewNote):
    decision: Literal["approved", "rejected"]


class TextUpdate(BaseModel):
    """P2-03：题干/选项/答案/提示/解答步骤的文本修订（staging 专用）。

    全部字段可选——只更新提交的字段；未提交字段保持原值。保存即重算
    content_hash（与 materialize 同公式），旧 review 自动 stale，
    transcription.human_review 回到 pending，且追加 text-edits.yaml 修订痕迹。
    """

    model_config = ConfigDict(extra="forbid")

    stem_latex: str | None = None
    choices: list[str] | None = None
    answer: str | None = None
    clue: str | None = None
    solution_steps: list[str] | None = None
    solution_notes: list[str] | None = None
    editor: str = "question-bank-review-ui"


class TranscriptionIssueDecision(ReviewNote):
    decision: Literal[
        "accept_candidate", "accept_baseline", "manual",
        "diagram", "mixed_content",
    ]
    accepted_window_id: str | None = None
    manual_value: str | None = None


def _read_yaml(path: Path) -> dict[str, Any]:
    _GLOBAL_YAML_PARSE_COUNT[0] += 1
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"无法读取 {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} 不是 YAML 对象")
    return payload


# YAML 解析计数器（进程级）：_read_yaml 是模块级函数，无法访问 catalog 实例，
# 用一个可变单元素列表当累加点；catalog.stats() 在调用点把进程级计数并进结果。
# 这里的计数对测试 / bench 已足够（单进程单 worker，§2.2）。
_GLOBAL_YAML_PARSE_COUNT: list[int] = [0]


def _bank_fingerprint(record: BankRecord) -> str:
    """汇总 bank 关键文件的 mtime_ns（§5.4 粗粒度新鲜度层）。

    覆盖 manifest + staging 的每题 source/review/teacher.resolved/student.resolved。
    外部脚本改其中任一份都会改变指纹，让读路由触发精准重建。只 stat 单 bank 的文件，
    不退化成全库扫描；缺失文件记 0 保持稳定。
    """
    parts: list[str] = [record.bank_id]
    manifest_path = (
        record.directory / "paper.yaml"
        if record.kind == "staging_exam"
        else record.directory / "question-bank.yaml"
    )
    try:
        parts.append(str(manifest_path.stat().st_mtime_ns))
    except OSError:
        parts.append("0")
    if record.kind == "staging_exam":
        for name in ("review-issues.yaml", "review-resolutions.yaml"):
            try:
                parts.append(str((record.directory / name).stat().st_mtime_ns))
            except OSError:
                parts.append("0")
        for item_id in QuestionBankCatalog._staging_item_ids(record):
            item_dir = record.directory / "items" / item_id
            for name in (
                "source.yaml",
                "review.yaml",
                "teacher.resolved.assignment.yaml",
                "student.resolved.assignment.yaml",
            ):
                try:
                    parts.append(str((item_dir / name).stat().st_mtime_ns))
                except OSError:
                    parts.append("0")
    else:
        for item in record.manifest.get("items", []):
            if not isinstance(item, dict):
                continue
            for key in ("student_assignment", "teacher_assignment"):
                rel = item.get(key)
                if not isinstance(rel, str) or not rel.strip():
                    continue
                try:
                    parts.append(str((record.directory / rel).stat().st_mtime_ns))
                except OSError:
                    parts.append("0")
    return "|".join(parts)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _safe_file(base: Path, relative: str, bank_dir: Path) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("缺少文件路径")
    bank_root = bank_dir.resolve()
    lexical = Path(os.path.abspath(base / relative))
    if not _inside(lexical, bank_root):
        raise ValueError("文件不存在或超出题库范围")
    current = lexical
    while current != bank_root:
        if current.is_symlink():
            raise ValueError("不允许通过符号链接读取题库文件")
        current = current.parent
    candidate = lexical.resolve()
    if not _inside(candidate, bank_root) or not candidate.is_file():
        raise ValueError("文件不存在或超出题库范围")
    return candidate


def _practice_block(payload: dict[str, Any], item_id: str) -> dict[str, Any]:
    for section in payload.get("sections", []):
        if not isinstance(section, dict):
            continue
        for block in section.get("blocks", []):
            if isinstance(block, dict) and block.get("id") == item_id:
                return block
    raise ValueError(f"assignment 中找不到题块 {item_id}")


def _first_practice_block(payload: dict[str, Any]) -> dict[str, Any]:
    found = [
        block
        for section in payload.get("sections", [])
        if isinstance(section, dict) and section.get("type") == "practice"
        for block in section.get("blocks", [])
        if isinstance(block, dict) and block.get("type") in QUESTION_TYPES
    ]
    if len(found) != 1:
        raise ValueError(f"assignment 应有且仅有一道题，实际为 {len(found)} 道")
    return found[0]


def _diagram_preview(
    diagram: Any,
    assignment_path: Path,
    bank_dir: Path,
) -> Path | None:
    if not isinstance(diagram, dict):
        return None
    image_path = diagram.get("image_path")
    if image_path:
        try:
            image = _safe_file(assignment_path.parent, image_path, bank_dir)
        except ValueError:
            return None
        if image.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
            return image
        return None
    tikz_path = diagram.get("tikz_path")
    if not tikz_path:
        return None
    try:
        fragment = _safe_file(assignment_path.parent, tikz_path, bank_dir)
    except ValueError:
        return None
    name = fragment.name
    prefix = name.removesuffix(".fragment.tex") if name.endswith(".fragment.tex") else fragment.stem
    for suffix in (".preview.svg", ".preview.png"):
        try:
            return _safe_file(fragment.parent, prefix + suffix, bank_dir)
        except ValueError:
            continue
    return None


def _asset_url(bank_id: str, item_id: str, role: str, path: Path) -> str:
    """Version preview URLs so regenerated diagrams bypass browser caches."""

    return f"/api/assets/{bank_id}/{item_id}/{role}?v={path.stat().st_mtime_ns}"


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(encoded)


# Staging content-hash 必须与 materialize_staging 的 hash_payload 逐字节一致
# （teacher + student + crop_hashes + attribution_reviews，固定四角色顺序），
# 否则 UI 换图/改文本后任何一次 materialize 重跑都会改变 hash、把 review 打回
# stale。此前 UI 端缺 attribution_reviews 段，属公式漂移（P2-03 修正）。
_STAGING_HASH_ROLES = (
    "question_evidence",
    "prompt",
    "solution",
    "official_solution",
)


def _staging_content_hash(
    source: dict[str, Any], teacher: dict[str, Any], student: dict[str, Any]
) -> str:
    crops = source.get("crops") or {}
    if not isinstance(crops, dict):
        crops = {}

    def _entries(role: str) -> list[Any]:
        entries = crops.get(role) or []
        return entries if isinstance(entries, list) else []

    return _canonical_hash(
        {
            "teacher": teacher,
            "student": student,
            "crop_hashes": {
                role: [
                    crop.get("output_sha256")
                    for crop in _entries(role)
                    if isinstance(crop, dict)
                ]
                for role in _STAGING_HASH_ROLES
            },
            "attribution_reviews": {
                role: [
                    crop.get("attribution_review") if isinstance(crop, dict) else None
                    for crop in _entries(role)
                ]
                for role in _STAGING_HASH_ROLES
            },
        }
    )


def _page_number_from_source(source_path: str) -> int | None:
    """页图路径 → 页码（word/pages/006.png 或 pages-pages/004.png 的数字词干）。"""
    name = Path(str(source_path)).name
    stem = Path(name).stem
    if stem.isdigit():
        return int(stem)
    if stem.startswith("page-") and stem.removeprefix("page-").isdigit():
        return int(stem.removeprefix("page-"))
    return None


# 目标角色 → word_evidence 角色（题图类必须落在题干页；解答类必须落在解答页）。
_TARGET_EVIDENCE_ROLE = {
    "question_evidence": "question",
    "prompt": "question",
    "solution_step": "official_solution",
    "official_solution": "official_solution",
}


def _crop_source_location_issues(
    source: dict[str, Any], *, target: str | None = None
) -> list[str]:
    """P2-04：crop 的来源页必须落在本题 word_evidence 声明的页集合内。

    只校验来源确实指向页图（数字词干）的 crop；手工粘贴图的 source 指向
    item 内 PNG（manual-*），无从判定页归属，跳过。返回可读问题列表（空 = 通过）。
    """
    word_evidence = source.get("word_evidence") or {}
    if not isinstance(word_evidence, dict) or not word_evidence:
        return []
    allowed = {
        role: {
            _page_number_from_source(entry.get("page_image", ""))
            for entry in (word_evidence.get(role) or [])
            if isinstance(entry, dict)
        }
        - {None}
        for role in ("question", "official_solution")
    }
    issues: list[str] = []
    crops = source.get("crops") or {}
    if not isinstance(crops, dict):
        return []
    for role, entries in crops.items():
        if not isinstance(entries, list):
            continue
        evidence_role = _TARGET_EVIDENCE_ROLE.get(str(role))
        if evidence_role is None:
            continue
        for index, crop in enumerate(entries):
            if not isinstance(crop, dict):
                continue
            page = _page_number_from_source(crop.get("source", ""))
            if page is None:
                continue
            if page not in allowed[evidence_role]:
                issues.append(
                    f"{role}[{index}]: 来源页 {page} 不在本题 "
                    f"word_evidence.{evidence_role} 页 {sorted(allowed[evidence_role])} 内"
                )
    return issues


def _atomic_write_yaml(path: Path, payload: dict[str, Any]) -> None:
    if path.is_symlink():
        raise ValueError(f"{path.name} 不允许为符号链接")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        yaml.safe_dump(
            payload, handle, allow_unicode=True, sort_keys=False, width=1000
        )
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _first_question_block(payload: dict[str, Any]) -> dict[str, Any]:
    return _first_practice_block(payload)


# 小题切分：识别 （1）/(2)/① 三类小问标记；少于 2 个标记按单一"整题"处理。
_SUBQUESTION_MARKER = re.compile(
    r"（\s*[0-9一二三四五六七八九十]{1,3}\s*）"
    r"|\(\s*[0-9]{1,2}\s*\)"
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫]"
)


def _derive_subquestions(stem_latex: str) -> list[dict[str, Any]]:
    stem = str(stem_latex or "").strip()
    matches = list(_SUBQUESTION_MARKER.finditer(stem))
    if len(matches) < 2:
        return [{"id": "sq1", "label": "", "stem_latex": stem}]
    subquestions: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(stem)
        subquestions.append(
            {
                "id": f"sq{index + 1}",
                "label": match.group(0),
                "stem_latex": stem[match.start() : end].strip(),
            }
        )
    return subquestions


def _explanations_path(item_dir: Path) -> Path:
    return item_dir / EXPLANATIONS_FILE


def _load_explanations(item_dir: Path) -> dict[str, Any] | None:
    """读取 sidecar；不存在、为符号链接、schema 不符或损坏时按无数据处理。"""
    path = _explanations_path(item_dir)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = _read_yaml(path)
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("schema") != EXPLANATIONS_SCHEMA:
        return None
    if not isinstance(payload.get("subquestions"), list):
        return None
    return payload


def _normalize_approach(approach: Any) -> dict[str, Any] | None:
    if not isinstance(approach, dict) or not str(approach.get("id", "")).strip():
        return None
    explanation = approach.get("explanation") if isinstance(approach.get("explanation"), dict) else {}
    solution = approach.get("solution") if isinstance(approach.get("solution"), dict) else {}
    return {
        "id": str(approach["id"]),
        "title": str(approach.get("title", "")),
        "explanation": {
            "text": str(explanation.get("text", "")),
            "status": str(explanation.get("status", "draft")),
            "source": str(explanation.get("source", "manual")),
            "transcript": str(explanation.get("transcript", "")),
            "audio_path": explanation.get("audio_path"),
        },
        "solution": {
            "text": str(solution.get("text", "")),
            "status": str(solution.get("status", "draft")),
            "source": str(solution.get("source", "manual")),
        },
        "created_at": approach.get("created_at"),
        "approved_at": approach.get("approved_at"),
        "blueprint": approach.get("blueprint") if isinstance(approach.get("blueprint"), dict) else None,
    }


def _subquestion_split_preview(
    *, stem: str, answer: str, solution_steps: list[str]
) -> dict[str, Any]:
    """ADR-005 审题面板的小问切分预览：确定性建议 + 对齐告警（只读）。

    与 canonical_export v2 组装同一套切分函数；promote 的 fail closed 门禁
    是权威，这里只是让审题人在批准前看到切分结果并对齐告警。
    """
    parts = ce.split_subquestions(stem)
    if not parts:
        return {"parts": [], "aligned": True, "warnings": [], "note": "无小问：真值保持整题顶层存储"}
    part_ids = [part["part_id"] for part in parts]
    answers = ce.split_marked_segments(answer, part_ids)
    solution = ce.split_marked_segments("\n".join(solution_steps), part_ids)
    warnings: list[str] = []
    if answers is None:
        warnings.append("官方答案与 (1)(2) 小问标记未对齐：promote 将拒绝，请先调整答案文本")
    if solution is None:
        warnings.append("解答步骤与 (1)(2) 小问标记未对齐：promote 将拒绝，请先调整解答文本")
    preview_parts: list[dict[str, Any]] = []
    for part in parts:
        part_id = part["part_id"]
        segment_answer = (answers or {}).get(part_id, "")
        value, range_text = (
            ce.extract_range_constraint(segment_answer) if segment_answer else ("", None)
        )
        preview_parts.append(
            {
                "part_id": part_id,
                "prompt": part["prompt"],
                "answer": value,
                "range_constraint": range_text,
                "solution": (solution or {}).get(part_id, ""),
            }
        )
    return {
        "parts": preview_parts,
        "aligned": not warnings,
        "warnings": warnings,
        "note": "v2 promote 将按此切分写入小问级真值（审题人工确认）",
    }


def _merged_explanations(
    item_dir: Path,
    teacher_block: dict[str, Any],
    item_id: str,
    canonical_parts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """派生小题骨架 + sidecar 中已存的讲解-解答对合并成 API 视图。

    ADR-005 派生收敛：canonical_parts（QT current 版本的小问清单）给定时
    以它为骨架，不再从 stem 正则重推（消除 stem/小问双源漂移）；缺省回退
    正则派生（无 canonical 绑定的题）。
    """
    if canonical_parts:
        derived = [
            {
                "id": str(part.get("part_id") or ""),
                "label": f"（{part.get('part_id')}）",
                "stem_latex": str(part.get("prompt") or ""),
            }
            for part in canonical_parts
        ]
    else:
        derived = _derive_subquestions(str(teacher_block.get("stem_latex", "")))
    stored = _load_explanations(item_dir)
    stored_entries: dict[str, dict[str, Any]] = {}
    extra_entries: list[dict[str, Any]] = []
    derived_ids = {entry["id"] for entry in derived}
    for entry in stored.get("subquestions", []) if stored else []:
        if not isinstance(entry, dict):
            continue
        entry_id = str(entry.get("id", ""))
        approaches = [
            normalized
            for normalized in (
                _normalize_approach(approach) for approach in entry.get("approaches", []) or []
            )
            if normalized is not None
        ]
        if entry_id in derived_ids:
            stored_entries[entry_id] = approaches
        elif entry_id:
            extra_entries.append(
                {
                    "id": entry_id,
                    "label": str(entry.get("label", "")),
                    "stem_latex": str(entry.get("stem_latex", "")),
                    "approaches": approaches,
                }
            )
    subquestions = [
        {
            "id": entry["id"],
            "label": entry["label"],
            "stem_latex": entry["stem_latex"],
            "approaches": stored_entries.get(entry["id"], []),
        }
        for entry in derived
    ]
    subquestions.extend(extra_entries)
    return {"schema": EXPLANATIONS_SCHEMA, "item_id": item_id, "subquestions": subquestions}


def _iter_approaches(
    payload: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for subquestion in payload.get("subquestions", []) or []:
        for approach in subquestion.get("approaches", []) or []:
            pairs.append((subquestion, approach))
    return pairs


def _default_explanations_summary() -> dict[str, Any]:
    return {
        "has_sidecar": False,
        "approach_count": 0,
        "approved_count": 0,
        "missing_explanation": True,
        "missing_solution_count": 0,
    }


def _explanations_summary(item_dir: Path) -> dict[str, Any]:
    """列表级状态：无 sidecar 即视为缺讲解；讲解齐但解答缺记为缺解答数。"""
    stored = _load_explanations(item_dir)
    if stored is None:
        return _default_explanations_summary()
    approaches = [pair[1] for pair in _iter_approaches(stored)]
    with_explanation = [
        approach
        for approach in approaches
        if (approach.get("explanation") or {}).get("text", "").strip()
    ]
    return {
        "has_sidecar": True,
        "approach_count": len(approaches),
        "approved_count": sum(
            1
            for approach in approaches
            if (approach.get("explanation") or {}).get("status") == "approved"
            and (approach.get("solution") or {}).get("status") == "approved"
        ),
        "missing_explanation": not with_explanation,
        "missing_solution_count": sum(
            1
            for approach in with_explanation
            if not (approach.get("solution") or {}).get("text", "").strip()
        ),
    }


def _solution_steps_text(teacher_block: dict[str, Any], label: str = "") -> str:
    """把大题 solution_steps 拼成文本；有小问标记时优先取该小问对应步骤。"""
    normalized = _normalized_solution_steps(teacher_block)
    if label:
        matched = [step for step in normalized if label in step["title"]]
        if matched:
            normalized = matched
    lines = [
        content if not title else f"{title}：{content}"
        for title, content in ((step["title"], step["content"]) for step in normalized)
        if content.strip()
    ]
    return "\n".join(lines)


def _normalized_solution_steps(teacher_block: dict[str, Any]) -> list[dict[str, str]]:
    """solution_steps 归一成 {title, content}（字符串步骤按无标题处理）。"""
    normalized: list[dict[str, str]] = []
    for step in teacher_block.get("solution_steps", []) or []:
        if isinstance(step, str):
            normalized.append({"title": "", "content": step})
        elif isinstance(step, dict):
            normalized.append(
                {
                    "title": str(step.get("title", "")),
                    "content": str(step.get("content") or step.get("content_latex", "")),
                }
            )
    return normalized


def _resolve_teaching_tools_root(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit)
    env_root = os.environ.get("TEACHING_TOOLS_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    return REPO_ROOT.parent / "teaching-tools"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_student_assignment(teacher: dict[str, Any]) -> dict[str, Any]:
    """Keep the review server self-contained while matching the normal derivation."""

    import copy

    teacher_only = {
        "answer",
        "clue",
        "solution_steps",
        "solution_notes",
        "source_solution_images",
        "teaching",
    }

    def is_solution_diagram(value: Any) -> bool:
        return isinstance(value, dict) and (
            value.get("variant") == "solution"
            or value.get("disclosure_policy") == "annotated"
        )

    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: strip(child)
                for key, child in value.items()
                if key not in teacher_only and not is_solution_diagram(child)
            }
        if isinstance(value, list):
            return [strip(child) for child in value]
        return value

    student = copy.deepcopy(teacher)
    meta = student.setdefault("meta", {})
    meta["version"] = "student"
    meta["show_answers"] = False
    title = str(meta.get("title", ""))
    meta["title"] = title.replace("· 教师版", "· 学生版").replace(
        "（教师版）", "（学生版）"
    )
    kept_sections = []
    for section in student.get("sections", []):
        if not isinstance(section, dict):
            continue
        if section.get("type") == "answer_key" or section.get("visibility") == "teacher":
            continue
        section = strip(section)
        section["visibility"] = "student"
        kept_sections.append(section)
    student["sections"] = kept_sections
    return student


class QuestionBankCatalog:
    def __init__(self, bank_root: str | Path, canonical_root: str | Path | None = None):
        self.bank_root = Path(bank_root).expanduser().resolve()
        # 讲解批准后 blueprint candidate batch 的输出仓库（可被 app 工厂覆盖）。
        self.teaching_tools_root = _resolve_teaching_tools_root()
        # Phase 3：canonical 注册表根（question-truth / teaching-approach / id 账本）。
        self.canonical_root = (
            Path(canonical_root).expanduser().resolve()
            if canonical_root is not None
            else Path(ce.CANONICAL_ROOT).resolve()
        )
        self.ta_ledger_path = self.canonical_root / "id-allocations.yaml"
        # 单进程读写模型（§6.1）：RLock 保护 snapshot 的构建与替换。
        self._lock = threading.RLock()
        self._snapshot: CatalogSnapshot | None = None
        # 可观测计数器（§11 阶段 0）：供测试与 bench 确认"不再每个请求都全量扫描"，
        # 并量化读模型各层命中情况。discover_count 已先存在，其余为本阶段新增。
        self.discover_count = 0
        self.yaml_parse_count = 0
        self.snapshot_hits = 0
        self.snapshot_misses = 0
        self.asset_index_hits = 0
        self.asset_index_misses = 0
        # perf_counter 累计耗时（秒），bench / stats 用。非原子累加在单进程足够，
        # 读侧只用于观测，偶发竞争最多丢一次累加，不影响正确性。
        self.discover_seconds = 0.0
        self.summary_seconds = 0.0
        self.staging_detail_seconds = 0.0
        # 单题详情缓存（§8.3 item cache，阶段 5）：key=(bank_id,item_id)，value=(generation, item)。
        # 与 snapshot 同 generation：snapshot 重建时 _rebuild_snapshot 会把整个 item_cache 清空，
        # 保证写后/外部写后的新快照不会回吐旧单题。锁内读写。
        self._item_cache: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
        # TTL watcher 停止信号（§5.2）：默认不启动，start_ttl_watcher 时创建。
        self._stop_watcher: threading.Event | None = None

    def stats(self) -> dict[str, Any]:
        """快照各计数器与累计耗时，供 /healthz 与 bench 读取（§11 阶段 0）。"""
        snapshot = self._snapshot
        return {
            "discover_count": self.discover_count,
            "yaml_parse_count": _GLOBAL_YAML_PARSE_COUNT[0],
            "snapshot_hits": self.snapshot_hits,
            "snapshot_misses": self.snapshot_misses,
            "asset_index_hits": self.asset_index_hits,
            "asset_index_misses": self.asset_index_misses,
            "discover_seconds": round(self.discover_seconds, 4),
            "summary_seconds": round(self.summary_seconds, 4),
            "staging_detail_seconds": round(self.staging_detail_seconds, 4),
            "snapshot_generation": snapshot.generation if snapshot else None,
        }

    def discover(self) -> tuple[list[BankRecord], list[str]]:
        self.discover_count += 1
        started = time.perf_counter()
        try:
            return self._discover_impl()
        finally:
            self.discover_seconds += time.perf_counter() - started

    def _discover_impl(self) -> tuple[list[BankRecord], list[str]]:
        records_by_id: dict[str, BankRecord] = {}
        errors: list[str] = []
        duplicate_ids: set[str] = set()
        for manifest_path in sorted(self.bank_root.glob("*/question-bank.yaml")):
            try:
                payload = _read_yaml(manifest_path)
                if payload.get("schema") != "math_topic_question_bank/v1":
                    continue
                bank = payload.get("bank")
                if not isinstance(bank, dict) or not isinstance(bank.get("id"), str):
                    raise ValueError("缺少 bank.id")
                bank_id = bank["id"]
                if bank_id in records_by_id:
                    duplicate_ids.add(bank_id)
                    errors.append(f"{manifest_path.parent.name}: 重复 bank.id: {bank_id}")
                    continue
                records_by_id[bank_id] = BankRecord(bank_id, manifest_path.parent.resolve(), payload)
            except ValueError as exc:
                errors.append(f"{manifest_path.parent.name}: {exc}")
        for bank_id in duplicate_ids:
            records_by_id.pop(bank_id, None)
        for paper_path in sorted(self.bank_root.glob("*/staging/*/paper.yaml")):
            try:
                payload = _read_yaml(paper_path)
                if payload.get("schema") != PAPER_SCHEMA:
                    continue
                paper = payload.get("paper")
                if not isinstance(paper, dict) or not isinstance(paper.get("id"), str):
                    raise ValueError("缺少 paper.id")
                source_bank_name = paper_path.parents[2].name
                paper_id = paper["id"]
                if "/" in paper_id or "\\" in paper_id:
                    raise ValueError("paper.id 不能包含路径分隔符")
                bank_id = f"staging:{source_bank_name}:{paper_id}"
                if bank_id in records_by_id:
                    duplicate_ids.add(bank_id)
                    errors.append(f"{paper_path.parent.name}: 重复 staging id: {bank_id}")
                    continue
                records_by_id[bank_id] = BankRecord(
                    bank_id,
                    paper_path.parent.resolve(),
                    payload,
                    kind="staging_exam",
                )
            except ValueError as exc:
                errors.append(f"{paper_path.parent.name}: {exc}")
        for bank_id in duplicate_ids:
            records_by_id.pop(bank_id, None)
        records = sorted(records_by_id.values(), key=lambda record: record.directory.name)
        return records, errors

    def record(self, bank_id: str) -> BankRecord:
        record = self.snapshot().records_by_id.get(bank_id)
        if record is None:
            raise KeyError(bank_id)
        return record

    # ------------------------------------------------------------------
    # Catalog snapshot（读模型，§4/§5/§6）
    # ------------------------------------------------------------------

    def snapshot(self) -> CatalogSnapshot:
        """读侧入口：返回当前快照，miss 时惰性触发一次全量重建。

        热态下所有读请求都走这里 → O(1) 内存命中；写操作通过 ``_invalidate_bank``
        精准重建受影响 bank 后整体替换快照引用（Python 引用赋值原子）。
        """
        snapshot = self._snapshot
        if snapshot is not None:
            self.snapshot_hits += 1
            return snapshot
        self.snapshot_misses += 1
        return self._rebuild_snapshot()

    def _rebuild_snapshot(self) -> CatalogSnapshot:
        """COW 全量重建（§6.3 四步）：锁内读 generation → 锁外构建 → 锁内校验 → 原子安装。"""
        with self._lock:
            current = self._snapshot
            base_generation = current.generation if current else 0
        # 锁外构建：扫描+解析全部 bank（耗时主体），不阻塞读者持有旧快照。
        new_snapshot = self._build_snapshot(base_generation + 1)
        with self._lock:
            # 期间若有别的线程先安装了更新的快照，丢弃本次结果，直接返回那个。
            if self._snapshot is not None and self._snapshot.generation > base_generation:
                return self._snapshot
            self._snapshot = new_snapshot
            # 单题缓存随 snapshot 一同失效：清掉所有旧 generation 的条目（§8.3）。
            # 新请求 miss 后再解析当前题，最多 3 份 YAML，而非整卷。
            self._item_cache.clear()
            return new_snapshot

    def _invalidate_bank(self, bank_id: str) -> CatalogSnapshot:
        """写后精准失效（§5.2/§6.2）：审核/换图/删图后刷新读模型。

        只重建受影响 bank 的 summary/detail/AssetIndex，再基于当前 snapshot 做
        copy-on-write 替换。图片写接口必须等待这个结果后才能返回新预览 URL；如果
        退化成全量重建，题库多时一次粘贴会阻塞数十秒，前端看起来像没有保存。
        """
        snapshot = self.snapshot()
        if bank_id not in snapshot.records_by_id:
            raise KeyError(bank_id)
        # 内部写串行安装：读者仍可无锁持有旧 snapshot；锁内只解析当前一份试卷，
        # 避免两个并发写用同一 generation 互相覆盖。
        with self._lock:
            current = self._snapshot or snapshot
            record = current.records_by_id.get(bank_id)
            if record is None:
                raise KeyError(bank_id)

            detail, preview_files = self._detail_for_record(record)
            summary = self.summary(record)

            summaries = [
                summary if item.get("id") == bank_id else item
                for item in current.summaries
            ]
            summaries_by_id = dict(current.summaries_by_id)
            summaries_by_id[bank_id] = summary
            details_by_bank = dict(current.details_by_bank)
            details_by_bank[bank_id] = detail

            items_by_bank_item = {
                key: value
                for key, value in current.items_by_bank_item.items()
                if key[0] != bank_id
            }
            for item in detail.get("items", []):
                items_by_bank_item[(bank_id, str(item.get("id", "")))] = item

            asset_paths = {
                key: value
                for key, value in current.asset_paths.items()
                if key[0] != bank_id
            }
            for (item_id, role), path in preview_files.items():
                try:
                    asset_paths[(bank_id, item_id, role)] = (
                        path,
                        path.stat().st_mtime_ns,
                    )
                except OSError:
                    continue

            source_page_paths = {
                key: value
                for key, value in current.source_page_paths.items()
                if key[0] != bank_id
            }
            if record.kind == "staging_exam":
                for item_id, role, index, path in self._collect_source_page_paths(record):
                    try:
                        source_page_paths[(bank_id, item_id, role, index)] = (
                            path,
                            path.stat().st_mtime_ns,
                        )
                    except OSError:
                        continue

            bank_fingerprints = dict(current.bank_fingerprints)
            bank_fingerprints[bank_id] = _bank_fingerprint(record)
            catalog_versions = dict(current.catalog_versions)
            version_file = record.directory / ".catalog-version"
            try:
                catalog_versions[bank_id] = version_file.stat().st_mtime_ns
            except OSError:
                catalog_versions.pop(bank_id, None)

            updated = CatalogSnapshot(
                generation=current.generation + 1,
                records_by_id=dict(current.records_by_id),
                summaries=summaries,
                summaries_by_id=summaries_by_id,
                facets=self._facets_from_summaries(summaries),
                errors=list(current.errors),
                details_by_bank=details_by_bank,
                items_by_bank_item=items_by_bank_item,
                asset_paths=asset_paths,
                source_page_paths=source_page_paths,
                bank_fingerprints=bank_fingerprints,
                catalog_versions=catalog_versions,
            )
            self._snapshot = updated
            self._item_cache = {
                key: value
                for key, value in self._item_cache.items()
                if key[0] != bank_id
            }
            return updated

    def reindex_bank(self, bank_id: str) -> CatalogSnapshot:
        """外部受控写触发的精准失效（§5.2/§8.5）：POST /api/admin/reindex?bank=<id>。

        与 _invalidate_bank 等价（都走全量 COW 重建）；单独命名让 admin 路由语义清晰，
        也方便后续阶段把这里改成「只重建受影响 bank」而不动内部写路径。
        """
        return self._rebuild_snapshot()

    def reindex_all(self) -> CatalogSnapshot:
        """全量重建（§8.5）：POST /api/admin/reindex（不带 bank）。
        显式入口，供 watcher/TTL/手工触发，绕过 snapshot 命中检查。
        """
        return self._rebuild_snapshot()

    def start_ttl_watcher(self, interval_seconds: float = 30.0) -> None:
        """不受约束外部写的兜底（§5.2）：低频后台线程 stat 所有 bank 指纹，变了即重建。

        覆盖「手工编辑 YAML、既不 bump .catalog-version 也不调 reindex」的场景。
        默认不启用（create_question_bank_app 经 external_write_ttl 开启），避免在
        测试 / 单进程里制造后台线程。守护线程在快照变化前 sleep，避免忙等。
        """
        if interval_seconds <= 0:
            return
        def _watch() -> None:
            while not self._stop_watcher.is_set():
                try:
                    snapshot = self._snapshot
                    if snapshot is not None:
                        for bank_id, record in snapshot.records_by_id.items():
                            cached = snapshot.bank_fingerprints.get(bank_id)
                            if cached is None or _bank_fingerprint(record) == cached:
                                continue
                            # 任一 bank 指纹变 → 整体重建一次即可，跳出内层循环。
                            self._rebuild_snapshot()
                            break
                except Exception:  # noqa: BLE001 — 后台线程绝不能因异常退出
                    pass
                self._stop_watcher.wait(interval_seconds)
        self._stop_watcher = threading.Event()
        thread = threading.Thread(target=_watch, name="catalog-ttl-watcher", daemon=True)
        thread.start()

    def bump_catalog_version(self, bank_id: str) -> bool:
        """受控 writer bump ``<bank>/.catalog-version``（§5.3）。

        供 notify_catalog_version.py CLI 与 POST /api/admin/reindex?bump=1 调用。
        写一个原子时间戳文件，让 ensure_bank_fresh 的快速路径在下一个读请求触发重建。
        文件本身不入库（.gitignore 忽略，可重建）。返回是否成功 bump（bank 不存在则 False）。
        """
        snapshot = self.snapshot()
        record = snapshot.records_by_id.get(bank_id)
        if record is None:
            return False
        version_path = record.directory / ".catalog-version"
        try:
            version_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=version_path.parent, delete=False
            ) as handle:
                handle.write(f"{datetime.now(timezone.utc).isoformat()}\n")
                temporary = Path(handle.name)
            os.replace(temporary, version_path)
        except OSError:
            return False
        return True

    def ensure_bank_fresh(self, bank_id: str) -> CatalogSnapshot:
        """读路由新鲜度兜底（§5.4）：stat 该 bank 关键文件，变了就精准重建。

        捕获服务端写路径之外的修改（外部脚本直接改 source.yaml/review.yaml、
        teacher.resolved.assignment.yaml 重新生成等），这些不会触发 _invalidate_bank。
        只 stat 单 bank 的几份文件，不退化成 O(items) 全库扫描。

        §5.3 两层：先 stat ``.catalog-version``（受控 writer bump 的 O(1) 快速路径），
        命中变化即重建；未变化再走指纹层（catch 不 bump 的外部脚本写）。
        """
        snapshot = self.snapshot()
        record = snapshot.records_by_id.get(bank_id)
        if record is None:
            return snapshot
        # .catalog-version 快速路径：受控 writer（ingestion/geometry/resolved）写完
        # bump 这个文件（见 notify_catalog_version.py / POST /api/admin/reindex）。
        version_path = record.directory / ".catalog-version"
        cached_version = snapshot.catalog_versions.get(bank_id)
        try:
            current_version = version_path.stat().st_mtime_ns
        except OSError:
            current_version = None
        # 文件 mtime 变化，或「缓存里没有但文件现在存在」（运行时首次 bump）→ 重建。
        if (cached_version is None and current_version is not None) or (
            cached_version is not None and current_version != cached_version
        ):
            return self._rebuild_snapshot()
        cached = snapshot.bank_fingerprints.get(bank_id)
        if cached is not None and _bank_fingerprint(record) == cached:
            return snapshot
        return self._rebuild_snapshot()

    def _build_snapshot(self, generation: int) -> CatalogSnapshot:
        """构建一个不可变快照。调用方负责并发替换（见 ``_rebuild_snapshot``）。"""
        records, errors = self.discover()
        records_by_id = {record.bank_id: record for record in records}
        summaries = []
        for record in records:
            started = time.perf_counter()
            try:
                summaries.append(self.summary(record))
            finally:
                self.summary_seconds += time.perf_counter() - started
        summaries_by_id = {summary["id"]: summary for summary in summaries}
        facets = self._facets_from_summaries(summaries)

        details_by_bank: dict[str, dict[str, Any]] = {}
        items_by_bank_item: dict[tuple[str, str], dict[str, Any]] = {}
        asset_paths: dict[tuple[str, str, str], tuple[Path, int]] = {}
        source_page_paths: dict[tuple[str, str, str, int], tuple[Path, int]] = {}
        bank_fingerprints: dict[str, str] = {}
        catalog_versions: dict[str, int] = {}
        for record in records:
            detail, preview_files = self._detail_for_record(record)
            details_by_bank[record.bank_id] = detail
            for item in detail.get("items", []):
                items_by_bank_item[(record.bank_id, str(item.get("id", "")))] = item
            for (item_id, role), path in preview_files.items():
                try:
                    mtime = path.stat().st_mtime_ns
                except OSError:
                    continue
                asset_paths[(record.bank_id, item_id, role)] = (path, mtime)
            if record.kind == "staging_exam":
                for item_id, role, index, path in self._collect_source_page_paths(record):
                    try:
                        mtime = path.stat().st_mtime_ns
                    except OSError:
                        continue
                    source_page_paths[(record.bank_id, item_id, role, index)] = (path, mtime)
            bank_fingerprints[record.bank_id] = _bank_fingerprint(record)
            version_file = record.directory / ".catalog-version"
            try:
                catalog_versions[record.bank_id] = version_file.stat().st_mtime_ns
            except OSError:
                pass  # 该 bank 没有 .catalog-version，ensure_bank_fresh 退化到指纹层。
        return CatalogSnapshot(
            generation=generation,
            records_by_id=records_by_id,
            summaries=summaries,
            summaries_by_id=summaries_by_id,
            facets=facets,
            errors=list(errors),
            details_by_bank=details_by_bank,
            items_by_bank_item=items_by_bank_item,
            asset_paths=asset_paths,
            source_page_paths=source_page_paths,
            bank_fingerprints=bank_fingerprints,
            catalog_versions=catalog_versions,
        )

    @staticmethod
    def _facets_from_summaries(summaries: list[dict[str, Any]]) -> dict[str, list[str]]:
        """聚合 facets（与原 ``/api/banks/facets`` 路由同序：exam_types 按 EXAM_TYPE_TOKENS）。"""
        grades: set[str] = set()
        years: set[str] = set()
        exam_types: set[str] = set()
        kinds: set[str] = set()
        for item in summaries:
            kinds.add(item.get("kind", "formal_bank"))
            if item.get("grade"):
                grades.add(item["grade"])
            if item.get("year"):
                years.add(item["year"])
            if item.get("exam_type"):
                exam_types.add(item["exam_type"])
        ordered_exam_types = [
            label for token, label in EXAM_TYPE_TOKENS.items() if label in exam_types
        ]
        return {
            "kinds": sorted(kinds),
            "grades": sorted(grades),
            "years": sorted(years, reverse=True),
            "exam_types": ordered_exam_types,
            "errors": [],  # errors 在 snapshot 顶层单独维护，这里留空避免重复。
        }

    @staticmethod
    def _collect_source_page_paths(
        record: BankRecord,
    ) -> list[tuple[str, str, int, Path]]:
        """扫描 staging source.yaml 的 word_evidence，产出 (item_id, role, index, path)。

        与 ``/api/source-pages`` 路由及 ``_word_evidence_pages`` 同源：来源页路径来自
        ``source.word_evidence[role][index].page_image``，当前未进入 ``preview_files``，
        AssetIndex 必须单独消费这一数据源（§8.4 注意）。
        """
        if record.kind != "staging_exam":
            return []
        results = []
        for item_id in QuestionBankCatalog._staging_item_ids(record):
            source_path = record.directory / "items" / item_id / "source.yaml"
            if not source_path.is_file():
                continue
            try:
                source = _read_yaml(source_path)
            except (OSError, ValueError):
                continue
            word_evidence = source.get("word_evidence")
            if not isinstance(word_evidence, dict):
                continue
            for role in ("question", "official_solution"):
                spans = word_evidence.get(role)
                if not isinstance(spans, list):
                    continue
                for index, entry in enumerate(spans):
                    if not isinstance(entry, dict):
                        continue
                    page_image = Path(str(entry.get("page_image") or ""))
                    if not page_image.is_absolute():
                        page_image = REPO_ROOT / page_image
                    try:
                        page_image = page_image.resolve()
                    except OSError:
                        continue
                    if not _inside(page_image, REPO_ROOT) or not page_image.is_file():
                        continue
                    results.append((item_id, role, index, page_image))
        return results

    @staticmethod
    def summary(record: BankRecord) -> dict[str, Any]:
        if record.kind == "staging_exam":
            paper = record.manifest.get("paper", {})
            item_ids = QuestionBankCatalog._staging_item_ids(record)
            review_counts = {
                "approved_count": 0,
                "rejected_count": 0,
                "stale_count": 0,
            }
            for item_id in item_ids:
                try:
                    source = _read_yaml(
                        _safe_file(
                            record.directory / "items" / item_id,
                            "source.yaml",
                            record.directory,
                        )
                    )
                    review = QuestionBankCatalog._review_state(
                        record.directory / "items" / item_id, source
                    )
                except ValueError:
                    continue
                if review["stale"]:
                    review_counts["stale_count"] += 1
                elif review["status"] == "approved":
                    review_counts["approved_count"] += 1
                elif review["status"] == "rejected":
                    review_counts["rejected_count"] += 1
            parsed = parse_paper_id(paper.get("id", ""))
            return {
                "id": record.bank_id,
                "kind": record.kind,
                "paper_id": paper.get("id", ""),
                "topic": paper.get("title", paper.get("id", record.bank_id)),
                "grade": paper.get("grade", ""),
                "subject": paper.get("subject", ""),
                "status": "staging",
                "target_count": len(item_ids),
                "item_count": len(item_ids),
                "enabled_count": review_counts["approved_count"],
                "exam_type": parsed["exam_type"],
                "year": parsed["year"],
                "district": parsed["district"],
                **review_counts,
            }
        bank = record.manifest.get("bank", {})
        items = record.manifest.get("items", [])
        return {
            "id": record.bank_id,
            "kind": record.kind,
            "topic": bank.get("topic", record.bank_id),
            "grade": bank.get("grade", ""),
            "subject": bank.get("subject", ""),
            "status": bank.get("status", ""),
            "target_count": bank.get("target_count", len(items)),
            "item_count": len(items),
            "enabled_count": sum(bool(item.get("enabled", True)) for item in items if isinstance(item, dict)),
            "exam_type": "",
            "year": "",
            "district": "",
        }

    @staticmethod
    def _staging_item_ids(record: BankRecord) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for section in record.manifest.get("sections", []):
            if not isinstance(section, dict):
                continue
            for item_id in section.get("item_ids", []):
                if isinstance(item_id, str) and item_id not in seen:
                    ordered.append(item_id)
                    seen.add(item_id)
        return ordered

    @staticmethod
    def _review_state(item_dir: Path, source: dict[str, Any]) -> dict[str, Any]:
        review_path = item_dir / "review.yaml"
        state: dict[str, Any] = {
            "status": "pending",
            "note": "",
            "notes": [],
            "reviewer": "",
            "reviewed_at": None,
            "stale": False,
        }
        if not review_path.exists():
            return state
        try:
            review = _read_yaml(_safe_file(item_dir, "review.yaml", item_dir))
            if review.get("schema") != REVIEW_SCHEMA:
                raise ValueError(f"review.yaml schema 必须为 {REVIEW_SCHEMA}")
            if review.get("item_id") != source.get("item_id"):
                raise ValueError("review.yaml item_id 与 source.yaml 不一致")
            if review.get("source_key") != source.get("source_key"):
                raise ValueError("review.yaml source_key 与 source.yaml 不一致")
            notes = review.get("notes", [])
            if not isinstance(notes, list):
                raise ValueError("review.yaml notes 必须为列表")
            state.update(
                {
                    "status": review.get("status", "pending"),
                    "note": "\n".join(str(note) for note in notes),
                    "notes": [str(note) for note in notes],
                    "reviewer": str(review.get("reviewer", "")),
                    "reviewed_at": review.get("reviewed_at"),
                    "stale": review.get("content_hash") != source.get("content_hash"),
                }
            )
        except ValueError as exc:
            state["status"] = "invalid"
            state["error"] = str(exc)
        return state

    @staticmethod
    def _crop_previews(
        entries: Any,
        *,
        record: BankRecord,
        item_id: str,
        item_dir: Path,
        role_prefix: str,
        edit_target: str,
        title_prefix: str,
        preview_files: dict[tuple[str, str], Path],
    ) -> list[dict[str, Any]]:
        previews: list[dict[str, Any]] = []
        if not isinstance(entries, list):
            return previews
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            try:
                image = _safe_file(item_dir, entry.get("output", ""), item_dir)
            except ValueError:
                continue
            if image.suffix.lower() not in PREVIEW_SUFFIXES:
                continue
            role = f"{role_prefix}-{index}"
            preview_files[(item_id, role)] = image
            # Surface pending-attribution metadata when present. A crop without
            # an attribution_review block is treated as accepted/confirmed.
            review = entry.get("attribution_review")
            if isinstance(review, dict):
                attribution_state = str(review.get("state") or "accepted")
                attribution_confidence = review.get("confidence")
                attribution_id = review.get("attribution_id")
            else:
                attribution_state = "accepted"
                attribution_confidence = None
                attribution_id = None
            previews.append(
                {
                    "title": f"{title_prefix} {index + 1}",
                    "url": _asset_url(record.bank_id, item_id, role, image),
                    "edit_index": index,
                    "edit_target": edit_target,
                    "attribution_state": attribution_state,
                    "attribution_confidence": attribution_confidence,
                    "attribution_id": attribution_id,
                }
            )
        return previews

    @staticmethod
    def _word_evidence_pages(
        entries: Any, *, bank_id: str, item_id: str, role: str
    ) -> list[dict[str, Any]]:
        """把整页图证据渲染成页码胶囊数据：page + url。

        url 指向 source-pages 路由，能服务 documents/ 下的整页 PNG（_asset_url 受
        bank_dir 限制无法服务仓库根下的来源图）。
        """
        rendered: list[dict[str, Any]] = []
        if not isinstance(entries, list):
            return rendered
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            page_image = str(entry.get("page_image") or "")
            page_number = entry.get("page_number")
            if not page_image or not isinstance(page_number, int):
                continue
            image_path = Path(page_image)
            if not image_path.is_absolute():
                image_path = REPO_ROOT / page_image
            image_path = image_path.resolve()
            if not _inside(image_path, REPO_ROOT) or not image_path.is_file():
                continue
            mtime = image_path.stat().st_mtime_ns
            rendered.append(
                {
                    "page": page_number,
                    "url": f"/api/source-pages/{bank_id}/{item_id}/{role}/{index}?v={mtime}",
                }
            )
        return rendered

    def _staging_detail(
        self, record: BankRecord
    ) -> tuple[dict[str, Any], dict[tuple[str, str], Path]]:
        preview_files: dict[tuple[str, str], Path] = {}
        rendered_items: list[dict[str, Any]] = []
        issues, resolutions = self._review_issue_sidecars(record)
        pending_ids = {
            issue.issue_id for issue in unresolved_issues(issues, resolutions)
        } if issues else set()
        resolution_by_id = {
            resolution.issue_id: resolution.model_dump(mode="json")
            for resolution in (resolutions.resolutions if resolutions else [])
        }
        issues_by_item: dict[str, list[dict[str, Any]]] = {}
        if issues:
            for issue in issues.issues:
                item_id = issue.item_id if isinstance(issue, ReviewIssue) else None
                if not item_id:
                    continue
                payload = issue.model_dump(mode="json")
                payload["resolved"] = issue.issue_id not in pending_ids
                payload["resolution"] = resolution_by_id.get(issue.issue_id)
                issues_by_item.setdefault(item_id, []).append(payload)
        for item_id in self._staging_item_ids(record):
            item_dir = record.directory / "items" / item_id
            rendered: dict[str, Any] = {
                "id": item_id,
                "title": item_id,
                "question_type": "",
                "difficulty": "",
                "skill_tags": [],
                "stem_latex": "",
                "choices": {},
                "answer": "",
                "clue": "",
                "solution_steps": [],
                "solution_notes": [],
                "source_question_previews": [],
                "source_question_pages": [],
                "prompt_previews": [],
                "official_solution_previews": [],
                "official_solution_pages": [],
                # crops whose attribution is still needs_review (0 when none/unknown).
                "pending_image_count": 0,
                # word_evidence.question + official_solution 合并去重后的整卷来源页，
                # 按 page_number 升序。题干/解答 evidence 分组不是业务需求（review ui 只做
                # 整卷溯源定位），故前端只渲染这一个合并视图；旧 role 字段保留供路由/兼容。
                "source_pages": [],
                "prompt_preview_url": None,
                "solution_preview_url": None,
                "solution_previews": [],
                "explanations_summary": _default_explanations_summary(),
                "review_issues": issues_by_item.get(item_id, []),
                "review": {
                    "status": "pending",
                    "note": "",
                    "notes": [],
                    "reviewer": "",
                    "reviewed_at": None,
                    "stale": False,
                },
            }
            try:
                source_path = _safe_file(item_dir, "source.yaml", record.directory)
                source = _read_yaml(source_path)
                if source.get("schema") != SOURCE_SCHEMA:
                    raise ValueError(f"source.yaml schema 必须为 {SOURCE_SCHEMA}")
                if source.get("item_id") != item_id:
                    raise ValueError("source.yaml item_id 与目录名不一致")
                student_path = _safe_file(
                    item_dir, "student.resolved.assignment.yaml", record.directory
                )
                teacher_path = _safe_file(
                    item_dir, "teacher.resolved.assignment.yaml", record.directory
                )
                student_block = _first_practice_block(_read_yaml(student_path))
                teacher_block = _first_practice_block(_read_yaml(teacher_path))
                rendered["explanations_summary"] = _explanations_summary(item_dir)
                teaching = teacher_block.get("teaching", {})
                if not isinstance(teaching, dict):
                    teaching = {}
                transcription = source.get("transcription", {})
                if not isinstance(transcription, dict):
                    transcription = {}
                rendered.update(
                    {
                        "title": f"第 {source.get('question_number', item_id)} 题",
                        "source_key": source.get("source_key", ""),
                        "question_number": source.get("question_number"),
                        "question_type": source.get("question_type", teacher_block.get("type", "")),
                        "points": source.get("points", teacher_block.get("points")),
                        "section_title": source.get("section_title", ""),
                        "difficulty": teaching.get("difficulty", ""),
                        "skill_tags": teaching.get("skill_tags", []),
                        "stem_latex": str(
                            student_block.get("stem_latex")
                            or student_block.get("stem")
                            or ""
                        ),
                        "choices": student_block.get("choices", {}),
                        "answer": str(teacher_block.get("answer", "")),
                        "clue": str(teacher_block.get("clue", "")),
                        "solution_notes": teacher_block.get("solution_notes", []),
                        "prompt_status": transcription.get(
                            "prompt_status", "author_pass"
                        ),
                        "prompt_review_notes": transcription.get(
                            "prompt_review_notes", []
                        ),
                        "solution_status": transcription.get(
                            "solution_status", "author_pass"
                        ),
                        "solution_review_notes": transcription.get(
                            "solution_review_notes", []
                        ),
                        "content_hash": source.get("content_hash", ""),
                    }
                )
                rendered["subquestion_split_preview"] = _subquestion_split_preview(
                    stem=str(
                        student_block.get("stem_latex")
                        or student_block.get("stem")
                        or ""
                    ),
                    answer=str(teacher_block.get("answer", "")),
                    solution_steps=[
                        str(step) if isinstance(step, str) else str(step.get("content", ""))
                        for step in teacher_block.get("solution_steps", [])
                        if isinstance(step, (str, dict))
                    ],
                )
                rendered["solution_steps"] = []
                for step_index, step in enumerate(
                    teacher_block.get("solution_steps", []), start=1
                ):
                    # 旧卷 solution_steps 常是字符串数组（逐条复刻原解答），归一成
                    # {content: str} 让前端按统一结构渲染；title 留空前端不显示标题行。
                    if isinstance(step, str):
                        step = {"content": step}
                    elif not isinstance(step, dict):
                        continue
                    rendered_step = {
                        "title": str(step.get("title", "")),
                        "content": str(step.get("content", "")),
                        "preview_url": None,
                        "preview_title": f"解析图 {step_index}",
                        "edit_target": "solution_step",
                        "edit_index": step_index - 1,
                    }
                    step_diagram = _diagram_preview(
                        step.get("diagram_col"), teacher_path, record.directory
                    )
                    if step_diagram:
                        role = f"solution-step-{step_index}"
                        preview_files[(item_id, role)] = step_diagram
                        rendered_step["preview_url"] = _asset_url(
                            record.bank_id, item_id, role, step_diagram
                        )
                    rendered["solution_steps"].append(rendered_step)
                crops = source.get("crops", {})
                if not isinstance(crops, dict):
                    crops = {}
                rendered["source_question_previews"] = self._crop_previews(
                    crops.get("question_evidence"),
                    record=record,
                    item_id=item_id,
                    item_dir=item_dir,
                    role_prefix="source-question",
                    edit_target="question_evidence",
                    title_prefix="原题截图",
                    preview_files=preview_files,
                )
                rendered["prompt_previews"] = self._crop_previews(
                    crops.get("prompt"),
                    record=record,
                    item_id=item_id,
                    item_dir=item_dir,
                    role_prefix="prompt",
                    edit_target="prompt",
                    title_prefix="题图",
                    preview_files=preview_files,
                )
                rendered["official_solution_previews"] = self._crop_previews(
                    crops.get("official_solution"),
                    record=record,
                    item_id=item_id,
                    item_dir=item_dir,
                    role_prefix="official-solution",
                    edit_target="official_solution",
                    title_prefix="官方解答原图",
                    preview_files=preview_files,
                )
                # Count crops whose attribution is still pending human confirmation,
                # so the UI can show a per-item "归因待确认" hint at the item level.
                pending = 0
                for key in (
                    "source_question_previews",
                    "prompt_previews",
                    "official_solution_previews",
                ):
                    for p in rendered.get(key, []) or []:
                        if p.get("attribution_state") == "needs_review":
                            pending += 1
                rendered["pending_image_count"] = pending
                word_evidence = source.get("word_evidence", {})
                if not isinstance(word_evidence, dict):
                    word_evidence = {}
                rendered["source_question_pages"] = self._word_evidence_pages(
                    word_evidence.get("question"),
                    bank_id=record.bank_id,
                    item_id=item_id,
                    role="question",
                )
                rendered["official_solution_pages"] = self._word_evidence_pages(
                    word_evidence.get("official_solution"),
                    bank_id=record.bank_id,
                    item_id=item_id,
                    role="official_solution",
                )
                # 合并题干/解答两路来源页，按 page_number 去重（同页两角色都标 → 取先出现
                # 的一条，URL 仍指向其原 role 的 source-pages 路由），再按页码升序输出。
                merged: dict[int, dict[str, Any]] = {}
                for entries in (
                    rendered["source_question_pages"],
                    rendered["official_solution_pages"],
                ):
                    for entry in entries:
                        page = entry.get("page")
                        if isinstance(page, int) and page not in merged:
                            merged[page] = entry
                rendered["source_pages"] = [
                    merged[page] for page in sorted(merged)
                ]
                # P2-04：页归属校验结果随 detail 下发（空列表 = 无错配）。
                rendered["source_location_issues"] = _crop_source_location_issues(
                    source
                )
                # P2-03：是否已有 UI 文本修订痕迹（P2-08 门禁 3 的展示位）。
                rendered["text_edited"] = (item_dir / "text-edits.yaml").is_file()
                if not rendered["prompt_previews"]:
                    prompt = _diagram_preview(
                        student_block.get("diagram_col"), student_path, record.directory
                    )
                    if prompt:
                        preview_files[(item_id, "prompt")] = prompt
                        rendered["prompt_previews"] = [
                            {
                                "title": "题图",
                                "url": _asset_url(
                                    record.bank_id, item_id, "prompt", prompt
                                ),
                                "edit_target": "prompt",
                                "edit_index": 0,
                            }
                        ]
                rendered["prompt_preview_url"] = (
                    rendered["prompt_previews"][0]["url"]
                    if rendered["prompt_previews"]
                    else None
                )
                rendered["solution_previews"] = rendered["official_solution_previews"]
                rendered["solution_preview_url"] = (
                    rendered["official_solution_previews"][0]["url"]
                    if rendered["official_solution_previews"]
                    else None
                )
                rendered["review"] = self._review_state(item_dir, source)
            except (OSError, ValueError) as exc:
                rendered["load_error"] = str(exc)
            rendered_items.append(rendered)
        summary = self.summary(record)
        summary["review_mode_active"] = issues is not None
        summary["review_issue_count"] = len(issues.issues) if issues else 0
        summary["unresolved_review_issue_count"] = len(pending_ids)
        summary["items"] = rendered_items
        return summary, preview_files

    @staticmethod
    def _review_issue_sidecars(
        record: BankRecord,
    ) -> tuple[ReviewIssuesBundle | None, ReviewResolutionsBundle | None]:
        issue_path = record.directory / "review-issues.yaml"
        if not issue_path.is_file():
            return None, None
        issues = ReviewIssuesBundle.model_validate(_read_yaml(issue_path))
        resolution_path = record.directory / "review-resolutions.yaml"
        resolutions = (
            ReviewResolutionsBundle.model_validate(_read_yaml(resolution_path))
            if resolution_path.is_file()
            else None
        )
        if issues.paper_id != str(record.manifest.get("paper", {}).get("id", "")):
            raise ValueError("review-issues.yaml paper_id 与 staging 试卷不匹配")
        return issues, resolutions

    @staticmethod
    def _manual_source_path(path: Path) -> str:
        resolved = path.resolve()
        try:
            return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
        except ValueError:
            return str(resolved)

    @staticmethod
    def _decode_pasted_image(raw: bytes) -> tuple[bytes, int, int]:
        if not raw:
            raise ValueError("剪贴板中没有图片")
        if len(raw) > MAX_PASTED_IMAGE_BYTES:
            raise ValueError("图片超过 20 MB，请先缩小后再粘贴")
        try:
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_PASTED_IMAGE_PIXELS:
                    raise ValueError("图片尺寸无效或超过 4000 万像素")
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
                output = io.BytesIO()
                image.save(output, format="PNG", optimize=True)
        except (UnidentifiedImageError, OSError) as exc:
            raise ValueError("无法识别粘贴的图片，请粘贴 PNG、JPEG 或 WebP") from exc
        return output.getvalue(), width, height

    def replace_staging_image(
        self,
        bank_id: str,
        item_id: str,
        target: str,
        index: int,
        raw: bytes,
    ) -> dict[str, Any]:
        record = self.record(bank_id)
        if (
            record.kind != "staging_exam"
            or item_id not in self._staging_item_ids(record)
            or target not in EDITABLE_IMAGE_TARGETS
        ):
            raise KeyError((bank_id, item_id, target))
        if index < 0:
            raise ValueError("图片位置无效")

        item_dir = (record.directory / "items" / item_id).resolve()
        if not _inside(item_dir, record.directory.resolve()):
            raise ValueError("staging item 超出试卷范围")
        source_path = _safe_file(item_dir, "source.yaml", record.directory)
        teacher_path = _safe_file(
            item_dir, "teacher.resolved.assignment.yaml", record.directory
        )
        student_path = _safe_file(
            item_dir, "student.resolved.assignment.yaml", record.directory
        )
        source = _read_yaml(source_path)
        teacher = _read_yaml(teacher_path)
        if source.get("schema") != SOURCE_SCHEMA or source.get("item_id") != item_id:
            raise ValueError("source.yaml 与 staging item 不匹配")
        crops = source.get("crops")
        if not isinstance(crops, dict):
            raise ValueError("source.yaml 缺少 crops")

        png, width, height = self._decode_pasted_image(raw)
        digest = _sha256_bytes(png)
        short_hash = digest.removeprefix("sha256:")[:16]
        role = "solution" if target == "solution_step" else target
        output_rel = f"assets/manual-{role}-{index + 1}-{short_hash}.png"
        output_path = Path(os.path.abspath(item_dir / output_rel))
        if not _inside(output_path, item_dir) or output_path.is_symlink():
            raise ValueError("手工图片路径不安全")

        role_crops = crops.setdefault(role, [])
        if not isinstance(role_crops, list):
            raise ValueError(f"crops.{role} 必须为列表")
        teacher_block = _first_question_block(teacher)
        previous_output: str | None = None

        if target == "solution_step":
            steps = teacher_block.get("solution_steps")
            if not isinstance(steps, list) or index >= len(steps) or not isinstance(steps[index], dict):
                raise ValueError("对应的解题步骤不存在")
            diagram = steps[index].get("diagram_col")
            if isinstance(diagram, dict):
                previous_output = str(diagram.get("image_path") or "")
            crop_index = next(
                (
                    position
                    for position, crop in enumerate(role_crops)
                    if isinstance(crop, dict) and crop.get("output") == previous_output
                ),
                len(role_crops),
            )
        else:
            if index > len(role_crops):
                raise ValueError("只能替换现有图片或追加到末尾")
            crop_index = index
            if index < len(role_crops) and isinstance(role_crops[index], dict):
                previous_output = str(role_crops[index].get("output") or "")

        crop_record = {
            "source": self._manual_source_path(output_path),
            "source_sha256": digest,
            "box_px": [0, 0, width, height],
            "whiteout_px": [],
            "output": output_rel,
            "output_sha256": digest,
        }
        if crop_index < len(role_crops):
            role_crops[crop_index] = crop_record
        else:
            role_crops.append(crop_record)

        if target == "prompt":
            if index != 0:
                raise ValueError("当前 assignment 只支持一张主题图")
            prompt_payload = {
                "image_path": output_rel,
                "variant": "prompt",
                "disclosure_policy": "clean",
            }
            stem_image = teacher_block.get("stem_image")
            if isinstance(stem_image, dict) and (
                stem_image.get("image_path") == previous_output
                or not isinstance(teacher_block.get("diagram_col"), dict)
            ):
                prompt_payload = {**stem_image, **prompt_payload}
                teacher_block["stem_image"] = prompt_payload
            else:
                diagram_col = teacher_block.get("diagram_col")
                if isinstance(diagram_col, dict):
                    prompt_payload = {**diagram_col, **prompt_payload}
                teacher_block["diagram_col"] = prompt_payload
            transcription = source.setdefault("transcription", {})
            if isinstance(transcription, dict):
                transcription["prompt_status"] = "review_pass"
                transcription["prompt_review_notes"] = []
        elif target == "solution_step":
            teacher_block["solution_steps"][index]["diagram_col"] = {
                "image_path": output_rel,
                "variant": "solution",
                "disclosure_policy": "teacher_only",
            }
            transcription = source.setdefault("transcription", {})
            if isinstance(transcription, dict):
                transcription["solution_status"] = "review_pass"
                transcription["solution_review_notes"] = []
        elif target == "official_solution":
            images = teacher_block.setdefault("source_solution_images", [])
            if not isinstance(images, list):
                raise ValueError("source_solution_images 必须为列表")
            while len(images) < index:
                prior_crop = role_crops[len(images)]
                if not isinstance(prior_crop, dict) or not prior_crop.get("output"):
                    raise ValueError("官方解答原图记录不完整")
                images.append(
                    {
                        "image_path": prior_crop["output"],
                        "width": "0.96\\linewidth",
                        "variant": "source_solution",
                        "disclosure_policy": "teacher_only",
                        "label": f"官方解答原图 {len(images) + 1}",
                    }
                )
            image_payload = {
                "image_path": output_rel,
                "width": "0.96\\linewidth",
                "variant": "source_solution",
                "disclosure_policy": "teacher_only",
                "label": f"官方解答原图 {index + 1}",
            }
            if index < len(images):
                images[index] = image_payload
            elif index == len(images):
                images.append(image_payload)
            else:
                raise ValueError("只能替换现有图片或追加到末尾")

        student = _derive_student_assignment(teacher)
        # P2-04：写入前校验本题既有 crop 的页归属（页图类 crop 不得跨题错配）。
        location_issues = _crop_source_location_issues(source, target=target)
        if location_issues:
            raise ValueError("来源页归属校验失败：" + "; ".join(location_issues))
        source["content_hash"] = _staging_content_hash(source, teacher, student)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "wb", dir=output_path.parent, delete=False
        ) as handle:
            handle.write(png)
            temporary_image = Path(handle.name)
        try:
            os.replace(temporary_image, output_path)
            _atomic_write_yaml(teacher_path, teacher)
            _atomic_write_yaml(student_path, student)
            _atomic_write_yaml(source_path, source)
        finally:
            if temporary_image.exists():
                temporary_image.unlink()

        # 写后失效该 bank（刷 AssetIndex + summary counts），再从新快照回取单题 detail。
        new_snapshot = self._invalidate_bank(bank_id)
        updated = new_snapshot.items_by_bank_item.get((bank_id, item_id))
        if updated is None:
            # 失效后该题仍缺失（理论不应发生，因为 record 仍有效）→ 兜底重建。
            detail, _ = self._staging_detail(record)
            updated = next(item for item in detail["items"] if item["id"] == item_id)
        return updated

    def delete_staging_image(
        self,
        bank_id: str,
        item_id: str,
        target: str,
        index: int,
    ) -> dict[str, Any]:
        record = self.record(bank_id)
        if (
            record.kind != "staging_exam"
            or item_id not in self._staging_item_ids(record)
            or target not in EDITABLE_IMAGE_TARGETS
        ):
            raise KeyError((bank_id, item_id, target))
        if index < 0:
            raise ValueError("图片位置无效")

        item_dir = (record.directory / "items" / item_id).resolve()
        if not _inside(item_dir, record.directory.resolve()):
            raise ValueError("staging item 超出试卷范围")
        source_path = _safe_file(item_dir, "source.yaml", record.directory)
        teacher_path = _safe_file(
            item_dir, "teacher.resolved.assignment.yaml", record.directory
        )
        student_path = _safe_file(
            item_dir, "student.resolved.assignment.yaml", record.directory
        )
        source = _read_yaml(source_path)
        teacher = _read_yaml(teacher_path)
        if source.get("schema") != SOURCE_SCHEMA or source.get("item_id") != item_id:
            raise ValueError("source.yaml 与 staging item 不匹配")
        crops = source.get("crops")
        if not isinstance(crops, dict):
            raise ValueError("source.yaml 缺少 crops")

        role = "solution" if target == "solution_step" else target
        role_crops = crops.get(role)
        if not isinstance(role_crops, list):
            raise ValueError(f"crops.{role} 必须为列表")
        teacher_block = _first_question_block(teacher)

        if target == "solution_step":
            steps = teacher_block.get("solution_steps")
            if (
                not isinstance(steps, list)
                or index >= len(steps)
                or not isinstance(steps[index], dict)
            ):
                raise ValueError("对应的解题步骤不存在")
            diagram = steps[index].get("diagram_col")
            if not isinstance(diagram, dict) or not diagram.get("image_path"):
                raise ValueError("这个解析图槽位已经是空的")
            removed_output = str(diagram["image_path"])
            crop_index = next(
                (
                    position
                    for position, crop in enumerate(role_crops)
                    if isinstance(crop, dict) and crop.get("output") == removed_output
                ),
                None,
            )
            if crop_index is not None:
                role_crops.pop(crop_index)
            steps[index].pop("diagram_col", None)
            transcription = source.setdefault("transcription", {})
            if isinstance(transcription, dict):
                transcription["solution_status"] = "needs_human_crop"
                transcription["solution_review_notes"] = [
                    "解答图已从审核槽位移除，请点击加号后粘贴正确解答图。"
                ]
        else:
            if index >= len(role_crops):
                raise ValueError("图片位置不存在")
            removed = role_crops.pop(index)
            removed_output = (
                str(removed.get("output") or "") if isinstance(removed, dict) else ""
            )

            if target == "prompt":
                for field in ("stem_image", "diagram_col"):
                    payload = teacher_block.get(field)
                    if isinstance(payload, dict) and payload.get("image_path") == removed_output:
                        teacher_block.pop(field, None)
                transcription = source.setdefault("transcription", {})
                if isinstance(transcription, dict):
                    transcription["prompt_status"] = "needs_human_crop"
                    transcription["prompt_review_notes"] = [
                        "题图已从审核槽位移除，请点击加号后粘贴正确题图。"
                    ]
            elif target == "official_solution":
                images = teacher_block.get("source_solution_images")
                if isinstance(images, list):
                    matching_index = next(
                        (
                            position
                            for position, image in enumerate(images)
                            if isinstance(image, dict)
                            and image.get("image_path") == removed_output
                        ),
                        index if index < len(images) else None,
                    )
                    if matching_index is not None:
                        images.pop(matching_index)

        student = _derive_student_assignment(teacher)
        source["content_hash"] = _staging_content_hash(source, teacher, student)
        _atomic_write_yaml(teacher_path, teacher)
        _atomic_write_yaml(student_path, student)
        _atomic_write_yaml(source_path, source)

        # 写后失效该 bank（刷 AssetIndex + summary counts），再从新快照回取单题 detail。
        new_snapshot = self._invalidate_bank(bank_id)
        updated = new_snapshot.items_by_bank_item.get((bank_id, item_id))
        if updated is None:
            # 失效后该题仍缺失（理论不应发生，因为 record 仍有效）→ 兜底重建。
            detail, _ = self._staging_detail(record)
            updated = next(item for item in detail["items"] if item["id"] == item_id)
        return updated

    def update_staging_text(
        self, bank_id: str, item_id: str, update: TextUpdate
    ) -> dict[str, Any]:
        """P2-03：编辑题干/答案/小问文本，重算 hash，旧 review 置 stale。

        写路径与图片替换一致（teacher + student + source 三写 + 精准失效）。
        学生版只同步题干与选项（答案/提示/解答步骤绝不进入学生 assignment）。
        修订痕迹追加在 items/<id>/text-edits.yaml（P2-08 门禁 3 的证据）。
        """
        record = self.record(bank_id)
        if (
            record.kind != "staging_exam"
            or item_id not in self._staging_item_ids(record)
        ):
            raise KeyError((bank_id, item_id))
        item_dir = record.directory / "items" / item_id
        teacher_path = item_dir / "teacher.resolved.assignment.yaml"
        student_path = item_dir / "student.resolved.assignment.yaml"
        source_path = item_dir / "source.yaml"
        for path in (teacher_path, student_path, source_path):
            if not path.is_file():
                raise KeyError((bank_id, item_id))

        teacher = _read_yaml(teacher_path)
        source = _read_yaml(source_path)
        block = _first_practice_block(teacher)
        changed: dict[str, Any] = {}
        if update.stem_latex is not None:
            text = update.stem_latex.strip()
            if not text:
                raise ValueError("题干不能为空")
            block["stem_latex"] = text
            changed["stem_latex"] = text
        if update.choices is not None:
            if len(update.choices) != 4 or any(not c.strip() for c in update.choices):
                raise ValueError("选择题必须恰好 4 个非空选项")
            block["choices"] = list(update.choices)
            changed["choices"] = list(update.choices)
        if update.answer is not None:
            text = update.answer.strip()
            if not text:
                raise ValueError("答案不能为空")
            block["answer"] = text
            changed["answer"] = text
        if update.clue is not None:
            block["clue"] = update.clue
            changed["clue"] = update.clue
        if update.solution_steps is not None:
            steps = [str(step).strip() for step in update.solution_steps]
            if block.get("type") in {"problem", "short_answer"} and not steps:
                raise ValueError("解答题至少需要一个解答步骤")
            block["solution_steps"] = steps
            changed["solution_steps"] = steps
        if update.solution_notes is not None:
            block["solution_notes"] = [str(note) for note in update.solution_notes]
            changed["solution_notes"] = block["solution_notes"]
        if not changed:
            raise ValueError("没有可保存的文本修改")

        student = _derive_student_assignment(teacher)
        source["content_hash"] = _staging_content_hash(source, teacher, student)
        # 内容已变：人工复核状态回 pending（与 materialize 的语义一致），
        # 旧 review.yaml 因 hash 不再匹配而在读取侧显示 stale。
        transcription = source.setdefault("transcription", {})
        if isinstance(transcription, dict):
            transcription["human_review"] = "pending"

        edits_path = item_dir / "text-edits.yaml"
        edits = (
            _read_yaml(edits_path)
            if edits_path.is_file()
            else {"schema": "math_item_text_edits/v1", "item_id": item_id, "edits": []}
        )
        edits.setdefault("edits", []).append(
            {
                "edited_at": datetime.now(timezone.utc).isoformat(),
                "editor": update.editor,
                "fields": sorted(changed),
            }
        )
        _atomic_write_yaml(teacher_path, teacher)
        _atomic_write_yaml(student_path, student)
        _atomic_write_yaml(source_path, source)
        _atomic_write_yaml(edits_path, edits)

        new_snapshot = self._invalidate_bank(bank_id)
        updated = new_snapshot.items_by_bank_item.get((bank_id, item_id))
        if updated is None:
            detail, _ = self._staging_detail(record)
            updated = next(item for item in detail["items"] if item["id"] == item_id)
        return updated

    def write_staging_review(
        self, bank_id: str, item_id: str, decision: ReviewDecision
    ) -> dict[str, Any]:
        record = self.record(bank_id)
        if record.kind != "staging_exam" or item_id not in self._staging_item_ids(record):
            raise KeyError((bank_id, item_id))
        review = self._write_staging_review_with_record(record, item_id, decision)
        # 写后精准失效该 bank（§9.1）：刷 summary counts + 该题 detail + AssetIndex。
        self._invalidate_bank(bank_id)
        return review

    def _write_staging_review_with_record(
        self, record: BankRecord, item_id: str, decision: ReviewDecision
    ) -> dict[str, Any]:
        """单题审核核心，复用传入 record，不再 discover（§9.1，A8）。

        批量审核在循环外只调一次 ``record()``，循环内全部走这里；公开入口
        ``write_staging_review`` 仍各自 ``record()`` 以保留完整校验。
        """
        bank_id = record.bank_id
        if record.kind != "staging_exam" or item_id not in self._staging_item_ids(record):
            raise KeyError((bank_id, item_id))
        item_dir = record.directory / "items" / item_id
        source = _read_yaml(_safe_file(item_dir, "source.yaml", record.directory))
        if source.get("schema") != SOURCE_SCHEMA or source.get("item_id") != item_id:
            raise ValueError("source.yaml 与 staging item 不匹配")
        review_path = item_dir / "review.yaml"
        if review_path.is_symlink():
            raise ValueError("review.yaml 不允许为符号链接")
        note = decision.note.strip()
        if decision.decision == "approved" and (record.directory / "review-issues.yaml").is_file():
            raise ValueError(
                "该卷处于转写疑点隔离审核模式；请先裁决疑点、应用 resolution 并重建正常 staging"
            )
        if decision.decision == "rejected" and not note:
            raise ValueError("要求修改时必须填写修改意见")
        notes = [note] if note else []
        payload = {
            "schema": REVIEW_SCHEMA,
            "item_id": item_id,
            "source_key": source.get("source_key"),
            "content_hash": source.get("content_hash"),
            "status": decision.decision,
            "reviewer": "question-bank-review-ui",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
        }
        item_dir_resolved = item_dir.resolve()
        if not _inside(item_dir_resolved, record.directory.resolve()):
            raise ValueError("staging item 超出试卷范围")
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=item_dir_resolved, delete=False
        ) as handle:
            yaml.safe_dump(payload, handle, allow_unicode=True, sort_keys=False)
            temporary = Path(handle.name)
        try:
            os.replace(temporary, review_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return self._review_state(item_dir_resolved, source)

    def write_issue_resolution(
        self,
        bank_id: str,
        item_id: str,
        issue_id: str,
        decision: TranscriptionIssueDecision,
    ) -> dict[str, Any]:
        record = self.record(bank_id)
        if record.kind != "staging_exam" or item_id not in self._staging_item_ids(record):
            raise KeyError((bank_id, item_id))
        issues, resolutions = self._review_issue_sidecars(record)
        if issues is None:
            raise KeyError(issue_id)
        issue = next(
            (
                candidate for candidate in issues.issues
                if candidate.issue_id == issue_id
                and getattr(candidate, "item_id", None) == item_id
            ),
            None,
        )
        if issue is None:
            raise KeyError(issue_id)
        now = datetime.now(timezone.utc)
        note = decision.note.strip() or None
        if isinstance(issue, ReviewIssue):
            if decision.decision not in {"accept_candidate", "accept_baseline", "manual"}:
                raise ValueError("字段疑点必须选择候选、基线或手工值")
            resolution = IssueResolution(
                issue_id=issue_id,
                decision=decision.decision,
                accepted_window_id=decision.accepted_window_id,
                manual_value=decision.manual_value,
                resolved_candidates_hash=issue.candidates_hash,
                reviewer="question-bank-review-ui",
                resolved_at=now,
                note=note,
            )
        else:
            if decision.decision not in {"diagram", "mixed_content"}:
                raise ValueError("图片分类疑点必须选择 diagram 或 mixed_content")
            resolution = AssetClassificationResolution(
                issue_id=issue_id,
                selected_class=decision.decision,
                resolved_issue_hash=issue.issue_hash,
                reviewer="question-bank-review-ui",
                resolved_at=now,
                note=note,
            )
        values = [
            value for value in (resolutions.resolutions if resolutions else [])
            if value.issue_id != issue_id
        ]
        values.append(resolution)
        bundle = ReviewResolutionsBundle(
            schema="math_transcription_review_resolutions/v1",
            paper_id=issues.paper_id,
            resolutions=values,
        )
        _atomic_write_yaml(
            record.directory / "review-resolutions.yaml",
            bundle.model_dump(by_alias=True, exclude_none=True, mode="json"),
        )
        self._invalidate_bank(bank_id)
        return {
            "issue_id": issue_id,
            "resolved": True,
            "resolution": resolution.model_dump(exclude_none=True, mode="json"),
        }

    def approve_all_staging(self, bank_id: str) -> dict[str, Any]:
        """一键通过整张 staging 试卷（A8：只 discover 一次 + 精准失效一次）。

        返回新契约（§9.2 推荐方案）：``{counts, updated_reviews, errors}``，
        前端 ``approveWholePaper`` 据此就地刷新计数与各题 review，不再重拉整卷。
        """
        record = self.record(bank_id)
        if record.kind != "staging_exam":
            raise KeyError(bank_id)
        approve = ReviewDecision(decision="approved", note="")
        errors: list[dict[str, str]] = []
        updated_reviews: dict[str, dict[str, Any]] = {}
        for item_id in self._staging_item_ids(record):
            try:
                updated_reviews[item_id] = self._write_staging_review_with_record(
                    record, item_id, approve
                )
            except (OSError, ValueError) as exc:
                errors.append({"item_id": item_id, "error": str(exc)})
        # 全部写完后只失效一次：刷 summary counts + 整卷 detail + AssetIndex。
        new_snapshot = self._invalidate_bank(bank_id)
        summary = new_snapshot.summaries_by_id.get(bank_id, {})
        return {
            "counts": {
                "approved": summary.get("approved_count", 0),
                "rejected": summary.get("rejected_count", 0),
                "stale": summary.get("stale_count", 0),
            },
            "updated_reviews": updated_reviews,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # 小题讲解 / 解答（items/<item>/explanations.yaml sidecar）
    # ------------------------------------------------------------------

    def _explanations_entry(
        self, bank_id: str, item_id: str
    ) -> tuple[BankRecord, Path, Path, dict[str, Any], dict[str, Any]]:
        """解析 (record, item_dir, teacher_path, teacher_payload, teacher_block)。"""
        record = self.record(bank_id)
        if record.kind == "staging_exam":
            if item_id not in self._staging_item_ids(record):
                raise KeyError((bank_id, item_id))
            item_dir = record.directory / "items" / item_id
            teacher_path = _safe_file(
                item_dir, "teacher.resolved.assignment.yaml", record.directory
            )
            teacher_payload = _read_yaml(teacher_path)
            teacher_block = _first_practice_block(teacher_payload)
        else:
            manifest_item = next(
                (
                    candidate
                    for candidate in record.manifest.get("items", [])
                    if isinstance(candidate, dict) and str(candidate.get("id", "")) == item_id
                ),
                None,
            )
            if manifest_item is None:
                raise KeyError((bank_id, item_id))
            teacher_path = _safe_file(
                record.directory, str(manifest_item.get("teacher_assignment", "")), record.directory
            )
            teacher_payload = _read_yaml(teacher_path)
            teacher_block = _practice_block(teacher_payload, item_id)
        item_dir = teacher_path.parent
        if not _inside(item_dir.resolve(), record.directory.resolve()):
            raise ValueError("item 目录越界")
        return record, item_dir, teacher_path, teacher_payload, teacher_block

    def _persist_explanations(
        self,
        record: BankRecord,
        bank_id: str,
        item_id: str,
        item_dir: Path,
        payload: dict[str, Any],
    ) -> None:
        path = _explanations_path(item_dir)
        if path.is_symlink():
            raise ValueError("explanations.yaml 不允许为符号链接")
        _atomic_write_yaml(
            path,
            {
                "schema": EXPLANATIONS_SCHEMA,
                "item_id": item_id,
                "subquestions": payload["subquestions"],
            },
        )
        self._invalidate_bank(bank_id)

    @staticmethod
    def _find_approach(
        payload: dict[str, Any], approach_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        for subquestion in payload["subquestions"]:
            for approach in subquestion["approaches"]:
                if approach["id"] == approach_id:
                    return subquestion, approach
        raise ValueError(f"讲解-解答对不存在：{approach_id}")

    def _new_approach(
        self, payload: dict[str, Any], subquestion: dict[str, Any], title: str = ""
    ) -> dict[str, Any]:
        numbers = [
            int(approach["id"][1:])
            for _, approach in _iter_approaches(payload)
            if re.fullmatch(r"a\d+", str(approach["id"]))
        ]
        return {
            "id": f"a{(max(numbers) + 1) if numbers else 1}",
            "title": title.strip() or f"思路 {len(subquestion['approaches']) + 1}",
            "explanation": {
                "text": "",
                "status": "draft",
                "source": "manual",
                "transcript": "",
                "audio_path": None,
            },
            "solution": {"text": "", "status": "draft", "source": "manual"},
            "created_at": _utc_now_iso(),
            "approved_at": None,
            "blueprint": None,
        }

    def explanations_view(self, bank_id: str, item_id: str) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        payload["recording_supported"] = (
            bool(explanations_ai.api_key()) and shutil.which("ffmpeg") is not None
        )
        return payload

    def create_approach(
        self, bank_id: str, item_id: str, subquestion_id: str, title: str = ""
    ) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        subquestion = next(
            (entry for entry in payload["subquestions"] if entry["id"] == subquestion_id),
            None,
        )
        if subquestion is None:
            raise ValueError(f"小问不存在：{subquestion_id}")
        subquestion["approaches"].append(self._new_approach(payload, subquestion, title))
        self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        return payload

    def update_approach(
        self,
        bank_id: str,
        item_id: str,
        approach_id: str,
        *,
        title: str | None = None,
        explanation_text: str | None = None,
        solution_text: str | None = None,
    ) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        _, approach = self._find_approach(payload, approach_id)
        title_changed = False
        if title is not None and title.strip() != approach.get("title"):
            approach["title"] = title.strip()
            title_changed = True
        content_changed = False
        if explanation_text is not None and explanation_text.strip() != approach["explanation"]["text"]:
            approach["explanation"].update(
                {"text": explanation_text.strip(), "status": "draft", "source": "manual"}
            )
            content_changed = True
        if solution_text is not None and solution_text.strip() != approach["solution"]["text"]:
            approach["solution"].update(
                {"text": solution_text.strip(), "status": "draft", "source": "manual"}
            )
            content_changed = True
        # P3-01：title-only 更新也必须落盘（此前仅内容变化触发 persist，标题改动重启即丢）。
        if content_changed or title_changed:
            # 批准后继续编辑 → 回到草稿，此前的 blueprint 导出自动过期。
            if content_changed and approach.get("approved_at"):
                approach["approved_at"] = None
                approach["explanation"]["status"] = "draft"
                approach["solution"]["status"] = "draft"
                stale_blueprint = dict(approach.get("blueprint") or {})
                stale_blueprint["stale"] = True
                approach["blueprint"] = stale_blueprint
            self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        return payload

    def delete_approach(self, bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        subquestion, _ = self._find_approach(payload, approach_id)
        subquestion["approaches"] = [
            approach
            for approach in subquestion["approaches"]
            if approach["id"] != approach_id
        ]
        self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        return payload

    def save_recording(
        self, bank_id: str, item_id: str, approach_id: str, audio: bytes, content_type: str
    ) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        _, approach = self._find_approach(payload, approach_id)
        suffix = explanations_ai.audio_suffix_for(content_type)
        if len(audio) > explanations_ai.MAX_AUDIO_BYTES:
            raise AiAssistError("audio_too_large", "录音超过 50MB 上限")
        if not audio:
            raise ValueError("录音内容为空")
        audio_dir = item_dir / EXPLANATIONS_AUDIO_DIR
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_file = audio_dir / f"{approach_id}-{int(time.time())}{suffix}"
        audio_file.write_bytes(audio)
        approach["explanation"]["audio_path"] = f"{EXPLANATIONS_AUDIO_DIR}/{audio_file.name}"
        self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        # 转写失败时录音已登记，稍后可通过"润色"重读录音重试转写。
        transcript = explanations_ai.transcribe_audio(audio, content_type)
        approach["explanation"]["transcript"] = transcript
        self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        return {**payload, "transcript": transcript}

    def polish_approach(self, bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        subquestion, approach = self._find_approach(payload, approach_id)
        explanation = approach["explanation"]
        transcript = str(explanation.get("transcript", "")).strip()
        if not transcript and explanation.get("audio_path"):
            audio_file = item_dir / str(explanation["audio_path"])
            if audio_file.is_file():
                content_type = mimetypes.guess_type(audio_file.name)[0] or "audio/webm"
                transcript = explanations_ai.transcribe_audio(
                    audio_file.read_bytes(), content_type
                )
                explanation["transcript"] = transcript
        if not transcript:
            raise ValueError("没有可润色的录音转写稿：请先录制讲解")
        polished = explanations_ai.polish_explanation_text(
            {
                "stem": str(teacher_block.get("stem_latex", "")),
                "subquestion_label": subquestion.get("label", ""),
                "subquestion_stem": subquestion.get("stem_latex", ""),
                "answer": str(teacher_block.get("answer", "")),
                "solution": str(approach["solution"].get("text", ""))
                or _solution_steps_text(teacher_block, subquestion.get("label", "")),
                "transcript": transcript,
            }
        )
        explanation.update({"text": polished, "source": "polished", "status": "draft"})
        if approach.get("approved_at"):
            approach["approved_at"] = None
            approach["solution"]["status"] = "draft"
            stale_blueprint = dict(approach.get("blueprint") or {})
            stale_blueprint["stale"] = True
            approach["blueprint"] = stale_blueprint
        self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        return payload

    def generate_missing(self, bank_id: str, item_id: str, kind: str) -> dict[str, Any]:
        """一键补齐：explanation=为缺讲解的小问生成讲解；solution=为有讲解缺解答的对生成解答。"""
        if kind not in {"explanation", "solution"}:
            raise ValueError("kind 必须是 explanation 或 solution")
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        stem = str(teacher_block.get("stem_latex", ""))
        answer = str(teacher_block.get("answer", ""))
        errors: list[dict[str, str]] = []
        last_error: AiAssistError | None = None
        generated = 0
        if kind == "explanation":
            for subquestion in payload["subquestions"]:
                if any(
                    approach["explanation"]["text"].strip()
                    for approach in subquestion["approaches"]
                ):
                    continue
                approach = (
                    subquestion["approaches"][0]
                    if subquestion["approaches"]
                    else self._new_approach(payload, subquestion)
                )
                if approach not in subquestion["approaches"]:
                    subquestion["approaches"].append(approach)
                try:
                    approach["explanation"]["text"] = explanations_ai.generate_explanation_text(
                        {
                            "stem": stem,
                            "subquestion_label": subquestion.get("label", ""),
                            "subquestion_stem": subquestion.get("stem_latex", ""),
                            "answer": answer,
                            "solution": _solution_steps_text(
                                teacher_block, subquestion.get("label", "")
                            ),
                        }
                    )
                    approach["explanation"].update({"source": "generated", "status": "draft"})
                    generated += 1
                except AiAssistError as exc:
                    last_error = exc
                    errors.append({"approach_id": approach["id"], "error": str(exc)})
        else:
            for subquestion, approach in _iter_approaches(payload):
                if not approach["explanation"]["text"].strip():
                    continue
                if approach["solution"]["text"].strip():
                    continue
                try:
                    approach["solution"]["text"] = explanations_ai.generate_solution_text(
                        {
                            "stem": stem,
                            "subquestion_label": subquestion.get("label", ""),
                            "subquestion_stem": subquestion.get("stem_latex", ""),
                            "answer": answer,
                            "explanation": approach["explanation"]["text"],
                        }
                    )
                    approach["solution"].update({"source": "generated", "status": "draft"})
                    generated += 1
                except AiAssistError as exc:
                    last_error = exc
                    errors.append({"approach_id": approach["id"], "error": str(exc)})
        if generated:
            self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        if not generated and last_error is not None:
            raise last_error
        return {"explanations": payload, "generated": generated, "errors": errors}

    def approve_approach(self, bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
        _, approach = self._find_approach(payload, approach_id)
        if not approach["explanation"]["text"].strip() or not approach["solution"]["text"].strip():
            raise ValueError("讲解与解答都填写后才能批准并导出 blueprint")
        approach["explanation"]["status"] = "approved"
        approach["solution"]["status"] = "approved"
        approach["approved_at"] = _utc_now_iso()
        self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        export = self._export_bank_blueprints(bank_id, record=record)
        refreshed = _merged_explanations(item_dir, teacher_block, item_id)
        _, refreshed_approach = self._find_approach(refreshed, approach_id)
        return {
            "explanations": refreshed,
            "blueprint": refreshed_approach.get("blueprint"),
            "export": export,
        }

    def _bank_item_ids(self, record: BankRecord) -> list[str]:
        if record.kind == "staging_exam":
            return self._staging_item_ids(record)
        return [
            str(entry.get("id"))
            for entry in record.manifest.get("items", [])
            if isinstance(entry, dict) and entry.get("id")
        ]

    def export_bank_blueprints(self, bank_id: str) -> dict[str, Any]:
        """手动重导出整卷 blueprint candidate batch。"""
        return self._export_bank_blueprints(bank_id)

    def _export_bank_blueprints(
        self, bank_id: str, record: BankRecord | None = None
    ) -> dict[str, Any]:
        """把该题库所有已批准的讲解-解答对重建成 teaching-tools authoring candidate batch。

        每次批准后全量重建（幂等）：输出覆盖写
        ``<teaching-tools>/authoring/tmp/reviewed-bank-import/<slug>.candidates.json``，
        candidate 元数据 source 固定为 reviewed-bank-import，assignments 指向教师版
        resolved assignment 绝对路径，供 ``authoring/scenario_pipeline.py generate`` 消费。
        """
        record = record or self.record(bank_id)
        root = self.teaching_tools_root
        if not root.is_dir():
            raise ValueError(f"teaching-tools 仓库目录不存在：{root}")
        slug = re.sub(r"[^0-9A-Za-z._-]+", "-", bank_id).strip("-") or "bank"
        candidates: list[dict[str, Any]] = []
        assignments: set[str] = set()
        items_with_candidates: set[str] = set()
        for item_id in self._bank_item_ids(record):
            try:
                _, item_dir, teacher_path, teacher_payload, teacher_block = (
                    self._explanations_entry(bank_id, item_id)
                )
            except (KeyError, ValueError, OSError):
                continue
            payload = _merged_explanations(
            item_dir, teacher_block, item_id, canonical_parts=self._question_parts(item_dir)
        )
            manifest_item = next(
                (
                    entry
                    for entry in record.manifest.get("items", [])
                    if isinstance(entry, dict) and str(entry.get("id", "")) == item_id
                ),
                None,
            )
            meta = manifest_item or {}
            item_candidates: list[dict[str, Any]] = []
            changed = False
            for subquestion, approach in _iter_approaches(payload):
                explanation = approach["explanation"]
                solution = approach["solution"]
                if explanation.get("status") != "approved" or solution.get("status") != "approved":
                    continue
                content_hash = "sha256:" + _sha256_bytes(
                    f"{explanation['text']}\n--\n{solution['text']}".encode("utf-8")
                )
                candidate_id = f"{bank_id}:{item_id}:{subquestion['id']}:{approach['id']}"
                teacher_abs = str(teacher_path.resolve())
                assignments.add(teacher_abs)
                item_candidates.append(
                    {
                        "id": candidate_id,
                        "promptData": {
                            "promptLatex": subquestion.get("stem_latex") or str(
                                teacher_block.get("stem_latex", "")
                            ),
                            "fullStemLatex": str(teacher_block.get("stem_latex", "")),
                            "subquestionLabel": subquestion.get("label", ""),
                            "itemId": item_id,
                            "explanationLatex": explanation["text"],
                            "solutionLatex": solution["text"],
                            "approvedAt": approach.get("approved_at"),
                        },
                        "answerKey": {
                            "answerLatex": str(teacher_block.get("answer", "")),
                            "solutionSteps": _normalized_solution_steps(teacher_block),
                        },
                        "metadata": {
                            "source": "reviewed-bank-import",
                            "assignments": [teacher_abs],
                            "tags": [str(tag) for tag in (meta.get("skill_tags") or [])],
                            "difficulty": str(meta.get("difficulty", "")),
                        },
                    }
                )
                blueprint = {
                    "candidate_id": candidate_id,
                    "content_hash": content_hash,
                    "exported_at": _utc_now_iso(),
                }
                if approach.get("blueprint") != blueprint:
                    approach["blueprint"] = blueprint
                    changed = True
            candidates.extend(item_candidates)
            if item_candidates:
                items_with_candidates.add(item_id)
            if changed:
                self._persist_explanations(record, bank_id, item_id, item_dir, payload)
        out_dir = root / "authoring" / "tmp" / "reviewed-bank-import"
        batch_path = out_dir / f"{slug}.candidates.json"
        if candidates:
            out_dir.mkdir(parents=True, exist_ok=True)
            batch = {
                "taskId": slug,
                "engineKind": "topic-practice",
                "contentId": f"topic-practice.{slug}.v1",
                "version": "1",
                "source": "reviewed-bank-import",
                "assignments": sorted(assignments),
                "candidates": candidates,
            }
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=out_dir, delete=False
            ) as handle:
                json.dump(batch, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                temporary = Path(handle.name)
            try:
                os.replace(temporary, batch_path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        elif batch_path.exists():
            batch_path.unlink()
        return {
            "batch_path": str(batch_path),
            "candidate_count": len(candidates),
            "item_count": len(items_with_candidates),
        }

    # ------------------------------------------------------------------
    # 教学策略 TeachingApproach（Phase 3：items/<item>/teaching-approach.yaml）
    # ------------------------------------------------------------------

    def _teaching_view(
        self,
        item_dir: Path,
        item_id: str,
        *,
        stored: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(stored if stored is not None else (ta.load_sidecar(item_dir) or {}))
        payload.setdefault("schema", ta.APPROACH_SCHEMA)
        payload.setdefault("item_id", item_id)
        payload.setdefault("approaches", [])
        if not payload.get("question"):
            payload["question"] = ta.question_binding(item_dir, self.ta_ledger_path)
        payload["recording_supported"] = (
            bool(explanations_ai.api_key()) and shutil.which("ffmpeg") is not None
        )
        payload["topic_skill_ids"] = list(ta.TOPIC_SKILL_IDS)
        # ADR-005：绑定的 QT current 版本若含小问，UI 需要小问清单做 part 选择。
        payload["question_parts"] = self._question_parts(item_dir)
        return payload

    def _question_parts(self, item_dir: Path) -> list[dict[str, Any]]:
        binding = ta.question_binding(item_dir, self.ta_ledger_path)
        if not binding or not binding.get("artifact_id"):
            return []
        try:
            truth = ce.current_truth(str(binding["artifact_id"]), root=self.canonical_root)
        except Exception:
            return []
        return [
            {"part_id": str(part.get("part_id") or ""), "prompt": str(part.get("prompt") or "")}
            for part in truth.get("subquestions") or []
        ]

    def _find_teaching_approach(
        self, payload: dict[str, Any], approach_id: str
    ) -> dict[str, Any]:
        for approach in payload.get("approaches") or []:
            if str(approach.get("id")) == approach_id:
                return approach
        raise KeyError(approach_id)

    def teaching_approach_view(self, bank_id: str, item_id: str) -> dict[str, Any]:
        record, item_dir, _, _, _ = self._explanations_entry(bank_id, item_id)
        return self._teaching_view(item_dir, item_id)

    def create_teaching_approach(
        self,
        bank_id: str,
        item_id: str,
        *,
        title: str,
        author: str,
        part_id: str = "",
    ) -> dict[str, Any]:
        record, item_dir, _, _, _ = self._explanations_entry(bank_id, item_id)
        binding = ta.question_binding(item_dir, self.ta_ledger_path)
        if binding is None:
            raise ValueError(
                "该题没有 canonical QuestionTruth 绑定（不在 id-allocations 账本中），"
                "不能创建教学策略"
            )
        parts = self._question_parts(item_dir)
        if parts and not str(part_id or "").strip():
            raise ValueError("该题含小问，创建教学策略时必须选择小问（ADR-005 part 绑定）")
        payload = ta.load_sidecar(item_dir) or {
            "schema": ta.APPROACH_SCHEMA,
            "item_id": item_id,
            "question": {**binding, "bound_at": _utc_now_iso()},
            "approaches": [],
        }
        if not payload.get("question"):
            payload["question"] = {**binding, "bound_at": _utc_now_iso()}
        approach = ta.new_approach(payload, title=title, author=author)
        approach["part_id"] = str(part_id or "").strip()
        payload["approaches"].append(approach)
        ta.save_sidecar(item_dir, payload)
        self._invalidate_bank(bank_id)
        return self._teaching_view(item_dir, item_id, stored=payload)

    def update_teaching_approach(
        self,
        bank_id: str,
        item_id: str,
        approach_id: str,
        *,
        title: str | None = None,
        goal: str | None = None,
        entry_signal: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        part_id: str | None = None,
        editor: str = "question-bank-review-ui",
    ) -> dict[str, Any]:
        record, item_dir, _, _, _ = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        changed: list[str] = []
        if title is not None and title.strip() != approach.get("title"):
            approach["title"] = title.strip()
            changed.append("title")
        if goal is not None and goal.strip() != approach.get("goal"):
            approach["goal"] = goal.strip()
            changed.append("goal")
        if entry_signal is not None and entry_signal.strip() != approach.get("entry_signal"):
            approach["entry_signal"] = entry_signal.strip()
            changed.append("entry_signal")
        if part_id is not None:
            normalized_part = str(part_id or "").strip()
            if normalized_part != str(approach.get("part_id") or ""):
                valid_parts = {p["part_id"] for p in self._question_parts(item_dir)}
                if valid_parts and normalized_part not in valid_parts:
                    raise ValueError(f"part_id {normalized_part} 不在该题小问列表中")
                approach["part_id"] = normalized_part
                changed.append("part_id")
        if steps is not None:
            normalized = [
                ta.normalize_step(step, index) for index, step in enumerate(steps)
            ]
            if normalized != approach.get("steps"):
                approach["steps"] = normalized
                approach["steps_origin"] = "manual"
                changed.append("steps")
        if changed:
            # Approved 修改回 Draft（FR-4）：旧 canonical 版本仍可从 registry 取回。
            if approach.get("approval"):
                approach["approval"] = None
                approach["status"] = "draft"
            ta.append_manual_edit_note(approach, editor=editor, fields=changed)
            ta.save_sidecar(item_dir, payload)
            self._invalidate_bank(bank_id)
        return self._teaching_view(item_dir, item_id, stored=payload)

    def delete_teaching_approach(
        self, bank_id: str, item_id: str, approach_id: str
    ) -> dict[str, Any]:
        record, item_dir, _, _, _ = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        if approach.get("canonical"):
            raise ValueError(
                "该教学策略已有冻结的 canonical 版本：工作副本不可删除"
                "（历史证据链保留，可编辑后重新批准）"
            )
        payload["approaches"] = [
            entry for entry in payload["approaches"] if entry.get("id") != approach_id
        ]
        ta.save_sidecar(item_dir, payload)
        self._invalidate_bank(bank_id)
        return self._teaching_view(item_dir, item_id, stored=payload)

    def save_teaching_recording(
        self, bank_id: str, item_id: str, approach_id: str, audio: bytes, content_type: str
    ) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        suffix = explanations_ai.audio_suffix_for(content_type)
        if len(audio) > explanations_ai.MAX_AUDIO_BYTES:
            raise AiAssistError("audio_too_large", "录音超过 50MB 上限")
        if not audio:
            raise ValueError("录音内容为空")
        revision_entry = ta.recording_revision(
            approach, item_dir, audio_bytes=audio, suffix=suffix
        )
        # 先落盘：ASR 失败时录音修订已在案，稍后可重试转写（P3-03 append-only）。
        ta.save_sidecar(item_dir, payload)
        transcript = explanations_ai.transcribe_audio(audio, content_type)
        ta.attach_transcript(
            approach,
            item_dir,
            revision_entry,
            transcript=transcript,
            asr={
                "provider": "dashscope",
                "model_id": explanations_ai.asr_model(),
            },
        )
        ta.save_sidecar(item_dir, payload)
        self._invalidate_bank(bank_id)
        return {**self._teaching_view(item_dir, item_id, stored=payload), "transcript": transcript}

    def teaching_recording_file(
        self, bank_id: str, item_id: str, approach_id: str, revision: int
    ) -> Path:
        """P3-02：受限音频回放——只允许读取该 approach 证据链里登记的录音修订。"""
        record, item_dir, _, _, _ = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        entry = next(
            (
                rec
                for rec in (approach.get("evidence") or {}).get("recordings") or []
                if int(rec.get("revision") or 0) == revision
            ),
            None,
        )
        if entry is None:
            raise ValueError(f"录音修订不存在：r{revision}")
        audio_file = item_dir / str(entry.get("audio_path") or "")
        if not _inside(audio_file.resolve(), record.directory.resolve()) or not audio_file.is_file():
            raise ValueError("录音文件缺失或越界")
        if audio_file.is_symlink():
            raise ValueError("录音文件不允许为符号链接")
        return audio_file

    def polish_teaching_approach(
        self, bank_id: str, item_id: str, approach_id: str
    ) -> dict[str, Any]:
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        recordings = (approach.get("evidence") or {}).get("recordings") or []
        revision_entry = next(
            (rec for rec in reversed(recordings) if str(rec.get("transcript") or "").strip()),
            None,
        )
        if revision_entry is None:
            latest = next(
                (
                    rec
                    for rec in reversed(recordings)
                    if rec.get("audio_path") and (item_dir / str(rec["audio_path"])).is_file()
                ),
                None,
            )
            if latest is None:
                raise ValueError("没有可润色的录音转写稿：请先录制讲解")
            content_type = mimetypes.guess_type(str(latest["audio_path"]))[0] or "audio/webm"
            transcript = explanations_ai.transcribe_audio(
                (item_dir / str(latest["audio_path"])).read_bytes(), content_type
            )
            ta.attach_transcript(
                approach,
                item_dir,
                latest,
                transcript=transcript,
                asr={
                    "provider": "dashscope",
                    "model_id": explanations_ai.asr_model(),
                },
            )
            revision_entry = latest
        polished = explanations_ai.polish_explanation_text(
            {
                "stem": str(teacher_block.get("stem_latex", "")),
                "subquestion_label": "",
                "subquestion_stem": "",
                "answer": str(teacher_block.get("answer", "")),
                "solution": _solution_steps_text(teacher_block),
                "transcript": str(revision_entry["transcript"]),
            }
        )
        ta.polish_revision(
            approach,
            item_dir,
            polished_text=polished,
            provenance={
                "provider": "dashscope",
                "model_id": explanations_ai.llm_model(),
                "prompt_version": "POLISH_PROMPT@2026-08-v1",
            },
            based_on_recording=int(revision_entry["revision"]),
        )
        approach["polished_text"] = polished
        if approach.get("approval"):
            approach["approval"] = None
            approach["status"] = "draft"
        ta.save_sidecar(item_dir, payload)
        self._invalidate_bank(bank_id)
        return self._teaching_view(item_dir, item_id, stored=payload)

    def init_teaching_steps(
        self,
        bank_id: str,
        item_id: str,
        approach_id: str,
        *,
        use_ai: bool = True,
        replace: bool = False,
    ) -> dict[str, Any]:
        """P3-05：从 assignment teaching/solution_steps 初始化 TeachingStep 草稿。

        AI（qwen-plus）只产建议草稿；无 key/关闭 AI 时退化为确定性 assignment 脚手架。
        草稿不会直接进入 canonical——批准门禁要求教师补齐空字段。
        """
        record, item_dir, _, _, teacher_block = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        if (approach.get("steps") or []) and not replace:
            raise ValueError("已有教学步骤：确认覆盖请传 replace=true")
        if use_ai and explanations_ai.api_key():
            teaching_fields = {
                key: teacher_block.get("teaching", {}).get(key)
                for key in ("teaching_goal", "expected_blocker", "fallback_move")
                if teacher_block.get("teaching", {}).get(key)
            }
            drafts = explanations_ai.draft_teaching_steps(
                {
                    "stem": str(teacher_block.get("stem_latex", "")),
                    "solution": _solution_steps_text(teacher_block)
                    or str(teacher_block.get("answer", "")),
                    "clue": str(teacher_block.get("clue") or ""),
                    "teaching": yaml.safe_dump(teaching_fields, allow_unicode=True)
                    if teaching_fields
                    else "（无）",
                    "allowed_skill_ids": ta.TOPIC_SKILL_IDS,
                }
            )
            steps_origin = "ai_draft"
        else:
            drafts = ta.assignment_step_drafts(teacher_block)
            steps_origin = "assignment"
        approach["steps"] = [
            ta.normalize_step(draft, index) for index, draft in enumerate(drafts)
        ]
        approach["steps_origin"] = steps_origin
        if approach.get("approval"):
            approach["approval"] = None
            approach["status"] = "draft"
        ta.save_sidecar(item_dir, payload)
        self._invalidate_bank(bank_id)
        return self._teaching_view(item_dir, item_id, stored=payload)

    def approve_teaching_approach(
        self,
        bank_id: str,
        item_id: str,
        approach_id: str,
        *,
        reviewer_id: str,
        review_note: str,
    ) -> dict[str, Any]:
        """P3-07/P3-08 + ADR-005：批准冻结 canonical ApprovedTeachingApproach.v2。

        冻结前先应用 Question change stale 事件（保证绑定的是 QT 当前版本）；
        part 绑定合法性（QT 含小问时必填且命中）在 freeze 内 fail closed；
        任何门禁失败（结构/绑定/静态答案一致性/schema/publication）都不写文件。
        """
        ta.apply_question_change_stale(root=self.canonical_root)
        record, item_dir, _, _, _ = self._explanations_entry(bank_id, item_id)
        payload = ta.load_sidecar(item_dir)
        if payload is None:
            raise KeyError(approach_id)
        approach = self._find_teaching_approach(payload, approach_id)
        binding = payload.get("question") or ta.question_binding(
            item_dir, self.ta_ledger_path
        )
        if not binding or not binding.get("artifact_id"):
            raise ValueError("该题没有 canonical QuestionTruth 绑定，不能批准")
        frozen = ta.freeze_approved_approach(
            approach,
            item_dir,
            reviewer_id=reviewer_id,
            review_note=review_note,
            qt_id=str(binding["artifact_id"]),
            ledger_path=self.ta_ledger_path,
            root=self.canonical_root,
            part_id=str(approach.get("part_id") or "") or None,
        )
        approach["status"] = "approved"
        approach["approval"] = {
            "reviewer_id": reviewer_id,
            "approved_at": frozen["approval"]["approved_at"],
            "review_note": review_note.strip() or None,
        }
        approach["canonical"] = {
            "artifact_id": frozen["artifact_id"],
            "version": frozen["version"],
            "content_hash": frozen["content_hash"],
            "approved_at": frozen["approval"]["approved_at"],
        }
        ta.save_sidecar(item_dir, payload)
        self._invalidate_bank(bank_id)
        return {
            "teaching_approach": self._teaching_view(item_dir, item_id, stored=payload),
            "canonical": {
                "artifact_id": frozen["artifact_id"],
                "version": frozen["version"],
                "artifact_uri": frozen["artifact_uri"],
                "content_hash": frozen["content_hash"],
            },
        }

    def detail(self, bank_id: str) -> tuple[dict[str, Any], dict[tuple[str, str], Path]]:
        return self._detail_for_record(self.record(bank_id))

    def item_detail(self, bank_id: str, item_id: str) -> dict[str, Any]:
        """单题完整详情（§8.3，阶段 5）：供 GET /api/banks/{id}/items/{item_id}。

        优先级：snapshot.items_by_bank_item（O(1) 命中，整卷 detail 已在快照构建时算好）
        → item cache（按 generation 失效）→ 仅解析当前题（兜底，不重建整卷）。
        snapshot 已持有整卷 detail，单题接口在热态是纯字典查找；item cache 只在
        snapshot miss 的极端情况（如外部写后 _item_cache 清空但 snapshot 还在重建）下有用。
        """
        snapshot = self.snapshot()
        cached = snapshot.items_by_bank_item.get((bank_id, item_id))
        if cached is not None:
            return cached
        # snapshot 里没有（题库/题目不存在或刚被外部删改）：先查 item cache，再解析当前题。
        with self._lock:
            entry = self._item_cache.get((bank_id, item_id))
            if entry is not None and entry[0] == snapshot.generation:
                return entry[1]
        # 兜底：解析当前题（不重建整卷）。staging 走 _staging_detail 取整卷再挑一题，
        # 因为单题解析依赖 source.yaml + 两份 resolved，_staging_detail 已封装这一套。
        record = snapshot.records_by_id.get(bank_id)
        if record is None:
            raise KeyError(bank_id)
        detail, _ = self._detail_for_record(record)
        for item in detail.get("items", []):
            if str(item.get("id", "")) == item_id:
                with self._lock:
                    self._item_cache[(bank_id, item_id)] = (snapshot.generation, item)
                return item
        raise KeyError((bank_id, item_id))

    def paper_directory(self, bank_id: str) -> dict[str, Any]:
        """卷级轻量目录（§8.3，阶段 5）：counts + items 的 id/title/review_status/stale。

        供前端首屏拿到导航所需的最小目录，再逐题懒加载完整详情（§10.3）。
        ensure_bank_fresh 兜底外部写；命中 snapshot 是 O(items) 内存投影，无 YAML 解析。
        """
        snapshot = self.ensure_bank_fresh(bank_id)
        detail = snapshot.details_by_bank.get(bank_id)
        if detail is None:
            raise KeyError(bank_id)
        items = detail.get("items", [])
        directory_items = [
            {
                "id": str(item.get("id", "")),
                "title": item.get("title") or item.get("id") or "",
                "review_status": (item.get("review") or {}).get("status", "pending"),
                "stale": bool((item.get("review") or {}).get("stale")),
                "review_issue_count": len(item.get("review_issues") or []),
                "unresolved_review_issue_count": sum(
                    1 for issue in item.get("review_issues") or []
                    if not issue.get("resolved")
                ),
            }
            for item in items
        ]
        if detail.get("kind") == "staging_exam":
            counts = {
                "approved": detail.get("approved_count", 0),
                "rejected": detail.get("rejected_count", 0),
                "stale": detail.get("stale_count", 0),
            }
        else:
            counts = {
                "approved": detail.get("enabled_count", 0),
                "rejected": 0,
                "stale": 0,
            }
        return {
            "id": bank_id,
            "kind": detail.get("kind", "formal_bank"),
            "topic": detail.get("topic", bank_id),
            "grade": detail.get("grade", ""),
            "paper_id": detail.get("paper_id", ""),
            "year": detail.get("year", ""),
            "exam_type": detail.get("exam_type", ""),
            "district": detail.get("district", ""),
            "item_count": detail.get("item_count", len(items)),
            "counts": counts,
            "review_mode_active": bool(detail.get("review_mode_active")),
            "review_issue_count": int(detail.get("review_issue_count", 0)),
            "unresolved_review_issue_count": int(
                detail.get("unresolved_review_issue_count", 0)
            ),
            "items": directory_items,
        }

    def _detail_for_record(
        self, record: BankRecord
    ) -> tuple[dict[str, Any], dict[tuple[str, str], Path]]:
        """detail 的无 discover 版本：直接用传入 record（消除 A2，snapshot 构建走这里）。"""
        bank_id = record.bank_id
        if record.kind == "staging_exam":
            started = time.perf_counter()
            try:
                return self._staging_detail(record)
            finally:
                self.staging_detail_seconds += time.perf_counter() - started
        preview_files: dict[tuple[str, str], Path] = {}
        rendered_items: list[dict[str, Any]] = []
        for manifest_item in record.manifest.get("items", []):
            if not isinstance(manifest_item, dict):
                continue
            item_id = str(manifest_item.get("id", ""))
            rendered = {
                key: manifest_item.get(key)
                for key in (
                    "id", "title", "question_type", "difficulty", "skill_tags",
                    "variation_dimension", "diagram_requirement", "weight", "enabled",
                )
            }
            rendered.update(
                {
                    "stem_latex": "",
                    "answer": "",
                    "clue": "",
                    "solution_steps": [],
                    "prompt_preview_url": None,
                    "solution_preview_url": None,
                    "solution_previews": [],
                    "explanations_summary": _default_explanations_summary(),
                }
            )
            try:
                student_path = _safe_file(
                    record.directory,
                    manifest_item.get("student_assignment", ""),
                    record.directory,
                )
                teacher_path = _safe_file(
                    record.directory,
                    manifest_item.get("teacher_assignment", ""),
                    record.directory,
                )
                student_payload = _read_yaml(student_path)
                teacher_payload = _read_yaml(teacher_path)
                rendered["explanations_summary"] = _explanations_summary(teacher_path.parent)
                student_block = _practice_block(student_payload, item_id)
                teacher_block = _practice_block(teacher_payload, item_id)
                rendered["stem_latex"] = str(student_block.get("stem_latex", ""))
                rendered["answer"] = str(teacher_block.get("answer", ""))
                rendered["clue"] = str(teacher_block.get("clue", ""))
                # ADR-005：审题面板的小问切分预览（formal bank 路径与 staging 同源）。
                rendered["subquestion_split_preview"] = _subquestion_split_preview(
                    stem=str(student_block.get("stem_latex") or ""),
                    answer=str(teacher_block.get("answer", "")),
                    solution_steps=[
                        str(step) if isinstance(step, str) else str(step.get("content", ""))
                        for step in teacher_block.get("solution_steps", [])
                        if isinstance(step, (str, dict))
                    ],
                )
                steps = teacher_block.get("solution_steps", [])
                rendered_steps: list[dict[str, Any]] = []
                solution_previews: list[dict[str, str]] = []
                seen_solution_paths: set[Path] = set()
                for step_index, step in enumerate(steps):
                    # 与 staging 路径一致：字符串格式 solution_steps 归一成 {content}。
                    if isinstance(step, str):
                        step = {"content": step}
                    elif not isinstance(step, dict):
                        continue
                    rendered_step = {
                        "title": str(step.get("title", "")),
                        "content": str(step.get("content", "")),
                        "preview_url": None,
                    }
                    step_preview = _diagram_preview(
                        step.get("diagram_col"), teacher_path, record.directory
                    )
                    if step_preview:
                        role = f"solution-step-{step_index}"
                        url = _asset_url(bank_id, item_id, role, step_preview)
                        preview_files[(item_id, role)] = step_preview
                        seen_solution_paths.add(step_preview)
                        rendered_step["preview_url"] = url
                        solution_previews.append(
                            {"title": rendered_step["title"] or f"第 {step_index + 1} 步", "url": url}
                        )
                    rendered_steps.append(rendered_step)
                rendered["solution_steps"] = rendered_steps
                prompt = _diagram_preview(student_block.get("diagram_col"), student_path, record.directory)
                answer_space = teacher_block.get("answer_space", {})
                solution_diagram = answer_space.get("diagram_col") if isinstance(answer_space, dict) else None
                solution = _diagram_preview(solution_diagram, teacher_path, record.directory)
                if prompt:
                    preview_files[(item_id, "prompt")] = prompt
                    rendered["prompt_preview_url"] = _asset_url(
                        bank_id, item_id, "prompt", prompt
                    )
                if solution:
                    preview_files[(item_id, "solution")] = solution
                    rendered["solution_preview_url"] = _asset_url(
                        bank_id, item_id, "solution", solution
                    )
                    seen_solution_paths.add(solution)
                    solution_previews.append(
                        {"title": "综合解答图", "url": rendered["solution_preview_url"]}
                    )
                extra_index = 0
                for section in teacher_payload.get("sections", []):
                    if not isinstance(section, dict) or section.get("type") != "answer_key":
                        continue
                    for diagram_block in section.get("blocks", []):
                        if not isinstance(diagram_block, dict):
                            continue
                        diagram = diagram_block.get("diagram_col")
                        if diagram is None and diagram_block.get("type") == "diagram":
                            diagram = diagram_block
                        extra = _diagram_preview(diagram, teacher_path, record.directory)
                        if not extra or extra in seen_solution_paths:
                            continue
                        role = f"solution-extra-{extra_index}"
                        extra_index += 1
                        url = _asset_url(bank_id, item_id, role, extra)
                        preview_files[(item_id, role)] = extra
                        seen_solution_paths.add(extra)
                        solution_previews.append(
                            {"title": str(diagram_block.get("label") or "解答图"), "url": url}
                        )
                rendered["solution_previews"] = solution_previews
                if solution_previews and not rendered["solution_preview_url"]:
                    rendered["solution_preview_url"] = solution_previews[0]["url"]
            except (OSError, ValueError) as exc:
                rendered["load_error"] = str(exc)
            rendered_items.append(rendered)
        bank = self.summary(record)
        bank["items"] = rendered_items
        return bank, preview_files


def _filter_bank_summaries(
    summaries: list[dict[str, Any]],
    *,
    kind: str | None,
    grade: str | None,
    year: str | None,
    exam_type: str | None,
    q: str | None,
) -> list[dict[str, Any]]:
    """按 kind/grade/year/exam_type/q 对题库 summary 做 AND 过滤。

    空参数视为不过滤；``q`` 对 topic/grade/year/exam_type/district/paper_id 做
    子串匹配（大小写不敏感）。formal_bank 没有 year/exam_type/district，这些
    过滤会自然排除 formal_bank。
    """
    query = (q or "").strip().lower()
    kind = (kind or "").strip()
    grade_f = (grade or "").strip()
    year_f = (year or "").strip()
    exam_type_f = (exam_type or "").strip()
    kept: list[dict[str, Any]] = []
    for item in summaries:
        if kind and item.get("kind", "formal_bank") != kind:
            continue
        if grade_f and item.get("grade", "") != grade_f:
            continue
        if year_f and item.get("year", "") != year_f:
            continue
        if exam_type_f and item.get("exam_type", "") != exam_type_f:
            continue
        if query:
            haystack = " ".join(
                str(item.get(field, ""))
                for field in ("topic", "grade", "year", "exam_type", "district", "paper_id", "id")
            ).lower()
            if query not in haystack:
                continue
        kept.append(item)
    return kept


def create_question_bank_app(
    bank_root: str | Path = DEFAULT_BANK_ROOT,
    number_review_url: str = DEFAULT_NUMBER_REVIEW_URL,
    external_write_ttl: float | None = None,
    triangle_candidates_path: str | Path | None = None,
    triangle_question_review_path: str | Path = DEFAULT_TRIANGLE_QUESTION_REVIEW,
    teaching_tools_root: str | Path | None = None,
    canonical_root: str | Path | None = None,
) -> FastAPI:
    catalog = QuestionBankCatalog(bank_root, canonical_root=canonical_root)
    if teaching_tools_root is not None:
        catalog.teaching_tools_root = _resolve_teaching_tools_root(teaching_tools_root)
    triangle_review = (
        TriangleCandidateReviewStore(Path(triangle_candidates_path), Path(triangle_question_review_path))
        if triangle_candidates_path is not None
        else None
    )
    app = FastAPI(title="Question Bank Review", version="0.1.0")
    app.state.catalog = catalog
    app.state.number_review_url = number_review_url
    # §5.2 兜底：external_write_ttl>0 启动后台 TTL watcher，覆盖不 bump 的外部写。
    # 默认 None=不启动（测试与单进程常态靠 ensure_bank_fresh 指纹层即可）。
    if external_write_ttl and external_write_ttl > 0:
        catalog.start_ttl_watcher(external_write_ttl)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def review_page() -> HTMLResponse:
        template_path = TEMPLATE_DIR / "question-bank-review.html"
        html = template_path.read_text(encoding="utf-8")
        static_version = max(
            template_path.stat().st_mtime_ns,
            (STATIC_DIR / "question-bank-review.css").stat().st_mtime_ns,
            (STATIC_DIR / "question-bank-review.js").stat().st_mtime_ns,
        )
        html = html.replace("__NUMBER_REVIEW_URL__", number_review_url).replace(
            "__STATIC_VERSION__", str(static_version)
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        # 读 snapshot（A9）：健康检查不再触发全量 discover。ready 反映预热状态，
        # 本阶段同步构建，恒为 True（后台预热 + ready 是阶段 10.3 的后续工作）。
        snapshot = catalog.snapshot()
        return {
            "ok": True,
            "ready": True,
            "banks": len(snapshot.summaries) + int(triangle_review is not None),
            "errors": snapshot.errors,
            # §11 阶段 0 可观测：stats 非破坏性追加，现有 ok/ready/banks/errors 契约不变。
            "stats": catalog.stats(),
        }

    @app.get("/api/bootstrap")
    def bootstrap() -> dict[str, Any]:
        """首屏单请求（§8.1）：一次返回 summaries + facets + errors + number_review_url。

        消灭原首屏 ``loadFacets()`` → ``applyFilters()`` 串行瀑布（F1），两者在旧实现里
        各自算一遍全量 catalog。改读 snapshot 后这里全部 O(1)：summaries 自带归一化字段、
        facets 已聚合、errors 已收集。前端据此本地填列表 + facets 再触发首次 selectBank。
        """
        snapshot = catalog.snapshot()
        facets = snapshot.facets
        generated_summary = triangle_review.summary() if triangle_review else None
        return {
            "banks": ([generated_summary] if generated_summary else []) + snapshot.summaries,
            "facets": {
                "kinds": sorted(set(facets["kinds"]) | ({"staging_exam"} if generated_summary else set())),
                "grades": sorted(set(facets["grades"]) | ({generated_summary["grade"]} if generated_summary else set())),
                "years": facets["years"],
                "exam_types": facets["exam_types"],
            },
            "errors": snapshot.errors,
            "number_review_url": number_review_url,
        }

    @app.get("/api/banks")
    def list_banks(
        kind: str | None = None,
        grade: str | None = None,
        year: str | None = None,
        exam_type: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        # 读 snapshot（A1/A4）：summaries 自带归一化 year/exam_type/district 字段，
        # 内存过滤零成本（§4.2）。_filter_bank_summaries 原样复用。
        snapshot = catalog.snapshot()
        banks = _filter_bank_summaries(
            ([triangle_review.summary()] if triangle_review else []) + snapshot.summaries,
            kind=kind,
            grade=grade,
            year=year,
            exam_type=exam_type,
            q=q,
        )
        return {
            "banks": banks,
            "errors": snapshot.errors,
            "number_review_url": number_review_url,
        }

    @app.get("/api/banks/facets")
    def bank_facets() -> dict[str, Any]:
        # 读 snapshot（A4）：facets 已在快照构建时聚合好。
        snapshot = catalog.snapshot()
        facets = snapshot.facets
        return {
            "kinds": sorted(set(facets["kinds"]) | ({"staging_exam"} if triangle_review else set())),
            "grades": sorted(set(facets["grades"]) | ({"九年级"} if triangle_review else set())),
            "years": facets["years"],
            "exam_types": facets["exam_types"],
            "errors": snapshot.errors,
        }

    @app.get("/api/banks/{bank_id}")
    def bank_detail(bank_id: str, directory: bool = False) -> dict[str, Any]:
        # 读 snapshot：整卷 detail 在快照构建时一次性算好。
        # ensure_bank_fresh 兜底外部写（直接改 source.yaml 等），保证 stale 检测等正确性。
        #
        # ?directory=1（§8.3 阶段 5）：返回轻量卷级目录（counts + items 的 id/title/
        # review_status/stale），供前端首屏拿导航再逐题懒加载。默认仍返回整卷完整 detail，
        # 兼容已提交测试与未升级前端（§14 反向兼容开关）。
        if bank_id == TRIANGLE_CANDIDATE_BANK_ID and triangle_review:
            return triangle_review.directory() if directory else {
                **triangle_review.directory(),
                "items": [triangle_review.item(item["id"]) for item in triangle_review.directory()["items"]],
            }
        if directory:
            try:
                return catalog.paper_directory(bank_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="题库不存在") from exc
        snapshot = catalog.ensure_bank_fresh(bank_id)
        detail = snapshot.details_by_bank.get(bank_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="题库不存在")
        return detail

    @app.get("/api/banks/{bank_id}/items/{item_id}")
    def item_detail(bank_id: str, item_id: str) -> dict[str, Any]:
        """单题完整详情（§8.3 阶段 5）：命中 snapshot O(1)，否则仅解析当前题。

        前端懒加载（§10.3）：加载卷级目录后逐题请求此接口，避免一次拉整卷 3×N 份 YAML。
        """
        if bank_id == TRIANGLE_CANDIDATE_BANK_ID and triangle_review:
            try:
                return triangle_review.item(item_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="题目不存在") from exc
        snapshot = catalog.ensure_bank_fresh(bank_id)
        try:
            return catalog.item_detail(bank_id, item_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="题目不存在") from exc

    @app.get("/api/assets/{bank_id}/{item_id}/{role}")
    def preview_asset(bank_id: str, item_id: str, role: str) -> FileResponse:
        # 读 AssetIndex（A6）：命中直接 FileResponse，不再为一张图重建整卷。
        # 索引未命中（新写尚未失效、或 bank 不存在）回退 detail()（§14 阶段 2 双写过渡）。
        snapshot = catalog.ensure_bank_fresh(bank_id)
        entry = snapshot.asset_paths.get((bank_id, item_id, role))
        path: Path | None = entry[0] if entry else None
        if path is None:
            catalog.asset_index_misses += 1
            try:
                _, files = catalog.detail(bank_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="题库不存在") from exc
            path = files.get((item_id, role))
        else:
            catalog.asset_index_hits += 1
        if path is None:
            raise HTTPException(status_code=404, detail="预览不存在")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.get("/api/source-pages/{bank_id}/{item_id}/{role}/{index}")
    def source_page_asset(
        bank_id: str, item_id: str, role: str, index: int
    ) -> FileResponse:
        """服务 documents/ 下的整页来源 PNG（_safe_file 限 bank_dir，无法服务仓库根文件）。

        读 AssetIndex（A7）：命中直接 FileResponse，不再 record()→discover()。
        索引未命中回退到内联 source.yaml 解析（§14 阶段 2 双写过渡），保留原 404 语义。
        """
        snapshot = catalog.ensure_bank_fresh(bank_id)
        entry = snapshot.source_page_paths.get((bank_id, item_id, role, index))
        page_image: Path | None = entry[0] if entry else None
        if page_image is None:
            catalog.asset_index_misses += 1
        else:
            catalog.asset_index_hits += 1
        if page_image is None:
            # 兼容性回退：role 必须是合法枚举，否则按原逻辑返回"来源证据不存在"。
            if role not in ("question", "official_solution"):
                raise HTTPException(status_code=404, detail="来源证据不存在")
            try:
                record = catalog.record(bank_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="题库不存在") from exc
            source_path = record.directory / "items" / item_id / "source.yaml"
            if not source_path.is_file():
                raise HTTPException(status_code=404, detail="source.yaml 不存在")
            try:
                source = _read_yaml(source_path)
            except (OSError, ValueError) as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            word_evidence = source.get("word_evidence") or {}
            if not isinstance(word_evidence, dict):
                raise HTTPException(status_code=404, detail="无来源证据")
            spans = word_evidence.get(role)
            if not isinstance(spans, list) or not 0 <= index < len(spans):
                raise HTTPException(status_code=404, detail="来源证据不存在")
            span_entry = spans[index]
            if not isinstance(span_entry, dict):
                raise HTTPException(status_code=404, detail="来源证据不存在")
            resolved = Path(str(span_entry.get("page_image") or ""))
            if not resolved.is_absolute():
                resolved = REPO_ROOT / resolved
            try:
                resolved = resolved.resolve()
            except OSError as exc:
                raise HTTPException(status_code=404, detail="页图不存在") from exc
            if not _inside(resolved, REPO_ROOT) or not resolved.is_file():
                raise HTTPException(status_code=404, detail="页图不存在")
            page_image = resolved
        media_type = mimetypes.guess_type(page_image.name)[0] or "application/octet-stream"
        return FileResponse(page_image, media_type=media_type)

    @app.post("/api/admin/reindex")
    def admin_reindex(
        bank: str | None = None,
        bump: bool = False,
    ) -> dict[str, Any]:
        """外部受控写触发失效（§8.5）：受控 writer（ingestion/geometry/resolved）调用。

        - ``bank=<bank_id>``：精准重建该 bank（实际走全量 COW，见 reindex_bank 文档）。
        - 无 ``bank``：全量重建 snapshot。
        - ``bump=true``：先 bump ``<bank>/.catalog-version``，让 ensure_bank_fresh 的快速路径
          在本进程之外的 reader 上也生效（多 reader 共享文件系统时）；同进程 reader 立即重建。
        """
        if bank is not None:
            snapshot = catalog.snapshot()
            if bank not in snapshot.records_by_id:
                raise HTTPException(status_code=404, detail="题库不存在")
            if bump and not catalog.bump_catalog_version(bank):
                raise HTTPException(status_code=400, detail="无法写入 .catalog-version")
            new_snapshot = catalog.reindex_bank(bank)
        else:
            new_snapshot = catalog.reindex_all()
        return {
            "ok": True,
            "generation": new_snapshot.generation,
            "banks": len(new_snapshot.summaries),
        }

    @app.post("/api/banks/{bank_id}/items/{item_id}/review")
    def review_staging_item(
        bank_id: str, item_id: str, decision: ReviewDecision
    ) -> dict[str, Any]:
        if bank_id == TRIANGLE_CANDIDATE_BANK_ID and triangle_review:
            try:
                return triangle_review.write_review(item_id, decision.decision, decision.note)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="候选题不存在") from exc
        try:
            return catalog.write_staging_review(bank_id, item_id, decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="staging 题目不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/issues/{issue_id}/resolution")
    def resolve_transcription_issue(
        bank_id: str,
        item_id: str,
        issue_id: str,
        decision: TranscriptionIssueDecision,
    ) -> dict[str, Any]:
        try:
            return catalog.write_issue_resolution(
                bank_id, item_id, issue_id, decision
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="转写疑点不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/banks/{bank_id}/review-all")
    def review_all_staging(bank_id: str) -> dict[str, Any]:
        """一键通过整张 staging 试卷，返回刷新后的 detail（含 items + errors）。"""
        if bank_id == TRIANGLE_CANDIDATE_BANK_ID and triangle_review:
            return triangle_review.approve_all()
        try:
            return catalog.approve_all_staging(bank_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="staging 试卷不存在") from exc

    @app.put("/api/banks/{bank_id}/items/{item_id}/text")
    def update_staging_text(
        bank_id: str,
        item_id: str,
        update: TextUpdate,
    ) -> dict[str, Any]:
        """P2-03：保存文本修订（重算 content_hash，旧 review 自动 stale）。"""
        try:
            return catalog.update_staging_text(bank_id, item_id, update)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="staging 题目不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/images/{target}/{index}")
    async def replace_staging_image(
        bank_id: str,
        item_id: str,
        target: str,
        index: int,
        request: Request,
    ) -> dict[str, Any]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=415, detail="请粘贴图片内容")
        raw = await request.body()
        try:
            return catalog.replace_staging_image(
                bank_id, item_id, target, index, raw
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="staging 图片位置不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/banks/{bank_id}/items/{item_id}/images/{target}/{index}")
    def delete_staging_image(
        bank_id: str,
        item_id: str,
        target: str,
        index: int,
    ) -> dict[str, Any]:
        try:
            return catalog.delete_staging_image(bank_id, item_id, target, index)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="staging 图片位置不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ------------------------------------------------------------------
    # 小题讲解 / 解答：查看、录音、润色、补齐、批准、blueprint 导出
    # ------------------------------------------------------------------

    def _explanations_http_error(
        exc: KeyError | ValueError | AiAssistError | OSError | TeachingApproachError,
    ) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(status_code=404, detail="题目或题库不存在")
        if isinstance(exc, AiAssistError):
            status_by_code = {
                "no_api_key": 503,
                "unsupported_media_type": 415,
                "audio_too_large": 413,
            }
            status = status_by_code.get(exc.code, 502)
            return HTTPException(status_code=status, detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/banks/{bank_id}/items/{item_id}/explanations")
    def get_explanations(bank_id: str, item_id: str) -> dict[str, Any]:
        try:
            return catalog.explanations_view(bank_id, item_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/explanations/approaches")
    def create_approach(
        bank_id: str, item_id: str, payload: ApproachCreate
    ) -> dict[str, Any]:
        try:
            return catalog.create_approach(
                bank_id, item_id, payload.subquestion_id, payload.title
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.put("/api/banks/{bank_id}/items/{item_id}/explanations/approaches/{approach_id}")
    def update_approach(
        bank_id: str, item_id: str, approach_id: str, payload: ApproachUpdate
    ) -> dict[str, Any]:
        try:
            return catalog.update_approach(
                bank_id,
                item_id,
                approach_id,
                title=payload.title,
                explanation_text=payload.explanation_text,
                solution_text=payload.solution_text,
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.delete("/api/banks/{bank_id}/items/{item_id}/explanations/approaches/{approach_id}")
    def delete_approach(bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        try:
            return catalog.delete_approach(bank_id, item_id, approach_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/explanations/approaches/{approach_id}/audio")
    async def upload_recording(
        bank_id: str,
        item_id: str,
        approach_id: str,
        request: Request,
    ) -> dict[str, Any]:
        content_type = request.headers.get("content-type", "")
        raw = await request.body()
        try:
            return catalog.save_recording(
                bank_id, item_id, approach_id, raw, content_type
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/explanations/approaches/{approach_id}/polish")
    def polish_approach(bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        try:
            return catalog.polish_approach(bank_id, item_id, approach_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/explanations/generate")
    def generate_explanations(
        bank_id: str, item_id: str, payload: ExplanationGenerateRequest
    ) -> dict[str, Any]:
        try:
            return catalog.generate_missing(bank_id, item_id, payload.kind)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/explanations/approaches/{approach_id}/approve")
    def approve_approach(bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        try:
            return catalog.approve_approach(bank_id, item_id, approach_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.post("/api/banks/{bank_id}/explanations/blueprint")
    def export_blueprints(bank_id: str) -> dict[str, Any]:
        try:
            return catalog.export_bank_blueprints(bank_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    @app.get("/api/banks/{bank_id}/items/{item_id}/explanations/approaches/{approach_id}/audio")
    def get_explanation_audio(bank_id: str, item_id: str, approach_id: str) -> FileResponse:
        """P3-02 兼容面：legacy 讲解录音的受限回放（只读 sidecar 登记的 audio_path）。"""
        try:
            record, item_dir, _, _, _ = catalog._explanations_entry(bank_id, item_id)
            payload = _merged_explanations(item_dir, {}, item_id)
            _, approach = catalog._find_approach(payload, approach_id)
            audio_path = str((approach.get("explanation") or {}).get("audio_path") or "")
            if not audio_path:
                raise ValueError("该讲解还没有录音")
            audio_file = item_dir / audio_path
            if (
                not _inside(audio_file.resolve(), record.directory.resolve())
                or not audio_file.is_file()
                or audio_file.is_symlink()
            ):
                raise ValueError("录音文件缺失或越界")
            media_type = mimetypes.guess_type(audio_file.name)[0] or "application/octet-stream"
            return FileResponse(audio_file, media_type=media_type, filename=audio_file.name)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _explanations_http_error(exc) from exc

    # ------------------------------------------------------------------
    # 教学策略 TeachingApproach（Phase 3）
    # ------------------------------------------------------------------

    def _ta_error(
        exc: KeyError | ValueError | AiAssistError | OSError | TeachingApproachError,
    ) -> HTTPException:
        if isinstance(exc, KeyError):
            return HTTPException(status_code=404, detail="题目、题库或教学策略不存在")
        if isinstance(exc, AiAssistError):
            status_by_code = {
                "no_api_key": 503,
                "unsupported_media_type": 415,
                "audio_too_large": 413,
            }
            return HTTPException(status_code=status_by_code.get(exc.code, 502), detail=str(exc))
        return HTTPException(status_code=400, detail=str(exc))

    @app.get("/api/banks/{bank_id}/items/{item_id}/teaching-approach")
    def get_teaching_approach(bank_id: str, item_id: str) -> dict[str, Any]:
        try:
            return catalog.teaching_approach_view(bank_id, item_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/teaching-approach/approaches")
    def create_teaching_approach(
        bank_id: str, item_id: str, payload: TeachingApproachCreate
    ) -> dict[str, Any]:
        try:
            return catalog.create_teaching_approach(
                bank_id,
                item_id,
                title=payload.title,
                author=payload.author,
                part_id=payload.part_id,
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.put("/api/banks/{bank_id}/items/{item_id}/teaching-approach/approaches/{approach_id}")
    def update_teaching_approach(
        bank_id: str, item_id: str, approach_id: str, payload: TeachingApproachUpdate
    ) -> dict[str, Any]:
        try:
            return catalog.update_teaching_approach(
                bank_id,
                item_id,
                approach_id,
                title=payload.title,
                goal=payload.goal,
                entry_signal=payload.entry_signal,
                steps=payload.steps,
                part_id=payload.part_id,
                editor=payload.editor,
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.delete("/api/banks/{bank_id}/items/{item_id}/teaching-approach/approaches/{approach_id}")
    def delete_teaching_approach(bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        try:
            return catalog.delete_teaching_approach(bank_id, item_id, approach_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.post("/api/banks/{bank_id}/items/{item_id}/teaching-approach/approaches/{approach_id}/audio")
    async def upload_teaching_recording(
        bank_id: str,
        item_id: str,
        approach_id: str,
        request: Request,
    ) -> dict[str, Any]:
        content_type = request.headers.get("content-type", "")
        raw = await request.body()
        try:
            return catalog.save_teaching_recording(
                bank_id, item_id, approach_id, raw, content_type
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.get(
        "/api/banks/{bank_id}/items/{item_id}/teaching-approach/"
        "approaches/{approach_id}/audio/{revision}"
    )
    def get_teaching_recording(bank_id: str, item_id: str, approach_id: str, revision: int):
        """P3-02：按修订号受限回放（文件必须在该 approach 证据链中登记）。"""
        try:
            audio_file = catalog.teaching_recording_file(
                bank_id, item_id, approach_id, revision
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc
        media_type = mimetypes.guess_type(audio_file.name)[0] or "application/octet-stream"
        return FileResponse(audio_file, media_type=media_type, filename=audio_file.name)

    @app.post("/api/banks/{bank_id}/items/{item_id}/teaching-approach/approaches/{approach_id}/polish")
    def polish_teaching_approach(bank_id: str, item_id: str, approach_id: str) -> dict[str, Any]:
        try:
            return catalog.polish_teaching_approach(bank_id, item_id, approach_id)
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.post(
        "/api/banks/{bank_id}/items/{item_id}/teaching-approach/"
        "approaches/{approach_id}/steps/init"
    )
    def init_teaching_steps(
        bank_id: str, item_id: str, approach_id: str, payload: TeachingStepsInitRequest
    ) -> dict[str, Any]:
        try:
            return catalog.init_teaching_steps(
                bank_id,
                item_id,
                approach_id,
                use_ai=payload.use_ai,
                replace=payload.replace,
            )
        except (KeyError, ValueError, AiAssistError, OSError) as exc:
            raise _ta_error(exc) from exc

    @app.post(
        "/api/banks/{bank_id}/items/{item_id}/teaching-approach/"
        "approaches/{approach_id}/approve"
    )
    def approve_teaching_approach(
        bank_id: str, item_id: str, approach_id: str, payload: TeachingApproachApproveRequest
    ) -> dict[str, Any]:
        try:
            return catalog.approve_teaching_approach(
                bank_id,
                item_id,
                approach_id,
                reviewer_id=payload.reviewer_id,
                review_note=payload.review_note,
            )
        except (
            KeyError,
            ValueError,
            AiAssistError,
            OSError,
            TeachingApproachError,
        ) as exc:
            raise _ta_error(exc) from exc

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-root", type=Path, default=DEFAULT_BANK_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--number-review-url", default=DEFAULT_NUMBER_REVIEW_URL)
    parser.add_argument("--triangle-candidates", type=Path, default=DEFAULT_TRIANGLE_CANDIDATES)
    parser.add_argument("--triangle-question-review", type=Path, default=DEFAULT_TRIANGLE_QUESTION_REVIEW)
    # §5.2 不受约束外部写兜底：>0 启动后台 TTL watcher（秒）。默认 0=不启动。
    parser.add_argument(
        "--external-write-ttl",
        type=float,
        default=0.0,
        help="后台指纹扫描间隔（秒）；0 关闭。覆盖手工编辑 YAML 这类不 bump 的外部写。",
    )
    parser.add_argument(
        "--canonical-root",
        type=Path,
        default=None,
        help="canonical 注册表根（question-truth/teaching-approach/id-allocations）。"
        "默认 teaching_approach.canonical_export.CANONICAL_ROOT。",
    )
    args = parser.parse_args(argv)
    uvicorn.run(
        create_question_bank_app(
            args.bank_root,
            args.number_review_url,
            external_write_ttl=args.external_write_ttl or None,
            triangle_candidates_path=args.triangle_candidates,
            triangle_question_review_path=args.triangle_question_review,
            canonical_root=args.canonical_root,
        ),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
