#!/usr/bin/env python3
"""FastAPI service for reviewing formal question banks and staging exam papers."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import mimetypes
import os
import tempfile
from dataclasses import dataclass
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
TEMPLATE_DIR = PACKAGE_DIR / "templates"
STATIC_DIR = PACKAGE_DIR / "static"
DEFAULT_BANK_ROOT = REPO_ROOT / "artifacts" / "题库"
DEFAULT_STAGING_ROOT = REPO_ROOT / "artifacts" / "试卷整理"
DEFAULT_NUMBER_REVIEW_URL = "http://127.0.0.1:8876/"
REVIEW_SCHEMA = "math_exam_item_review/v1"
SOURCE_SCHEMA = "math_exam_item_source/v1"
PAPER_SCHEMA = "math_exam_paper/v1"
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


@dataclass(frozen=True)
class BankRecord:
    bank_id: str
    directory: Path
    manifest: dict[str, Any]
    kind: Literal["formal_bank", "staging_exam"] = "formal_bank"
    assignment_path: Path | None = None
    crop_manifest_path: Path | None = None


class ReviewNote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(default="", max_length=4000)


class ReviewDecision(ReviewNote):
    decision: Literal["approved", "rejected"]


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"无法读取 {path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} 不是 YAML 对象")
    return payload


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


def _derive_student_assignment(teacher: dict[str, Any]) -> dict[str, Any]:
    """Keep the review server self-contained while matching the normal derivation."""

    import copy

    teacher_only = {
        "answer",
        "explanation",
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
    def __init__(self, bank_root: str | Path):
        self.bank_root = Path(bank_root).expanduser().resolve()

    def discover(self) -> tuple[list[BankRecord], list[str]]:
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
        records, _ = self.discover()
        for record in records:
            if record.bank_id == bank_id:
                return record
        raise KeyError(bank_id)

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
                **review_counts,
            }
        bank = record.manifest.get("bank", {})
        items = record.manifest.get("items", [])
        return {
            "id": record.bank_id,
            "topic": bank.get("topic", record.bank_id),
            "grade": bank.get("grade", ""),
            "subject": bank.get("subject", ""),
            "status": bank.get("status", ""),
            "target_count": bank.get("target_count", len(items)),
            "item_count": len(items),
            "enabled_count": sum(bool(item.get("enabled", True)) for item in items if isinstance(item, dict)),
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
    ) -> list[dict[str, str]]:
        previews: list[dict[str, str]] = []
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
            previews.append(
                {
                    "title": f"{title_prefix} {index + 1}",
                    "url": _asset_url(record.bank_id, item_id, role, image),
                    "edit_index": index,
                    "edit_target": edit_target,
                }
            )
        return previews

    @staticmethod
    def _word_evidence_texts(entries: Any, *, title_prefix: str) -> list[dict[str, str]]:
        rendered: list[dict[str, str]] = []
        if not isinstance(entries, list):
            return rendered
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            manifest = Path(str(entry.get("manifest", "")))
            if not manifest.is_absolute():
                manifest = REPO_ROOT / manifest
            manifest = manifest.resolve()
            if not _inside(manifest, REPO_ROOT) or not manifest.is_file():
                continue
            try:
                payload = _read_yaml(manifest)
                start = int(entry.get("paragraph_start"))
                end = int(entry.get("paragraph_end"))
            except (TypeError, ValueError):
                continue
            lines: list[str] = []
            for record in payload.get("paragraphs") or []:
                if not isinstance(record, dict):
                    continue
                paragraph_index = record.get("index")
                if not isinstance(paragraph_index, int) or not start <= paragraph_index <= end:
                    continue
                text = str(record.get("text") or "").strip()
                media = [str(value) for value in record.get("images") or [] if value]
                detail = text
                if media:
                    detail += ("\n" if detail else "") + "媒体：" + "、".join(media)
                if detail:
                    lines.append(f"[{paragraph_index}] {detail}")
            if lines:
                rendered.append(
                    {
                        "title": f"{title_prefix} {index + 1}（段落 {start}–{end}）",
                        "text": "\n".join(lines),
                    }
                )
        return rendered

    def _staging_detail(
        self, record: BankRecord
    ) -> tuple[dict[str, Any], dict[tuple[str, str], Path]]:
        preview_files: dict[tuple[str, str], Path] = {}
        rendered_items: list[dict[str, Any]] = []
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
                "explanation": "",
                "solution_steps": [],
                "solution_notes": [],
                "source_question_previews": [],
                "source_question_texts": [],
                "prompt_previews": [],
                "official_solution_previews": [],
                "official_solution_texts": [],
                "prompt_preview_url": None,
                "solution_preview_url": None,
                "solution_previews": [],
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
                        "explanation": str(teacher_block.get("explanation", "")),
                        "solution_notes": teacher_block.get("solution_notes", []),
                        "prompt_status": transcription.get(
                            "prompt_status", "author_pass"
                        ),
                        "prompt_review_notes": transcription.get(
                            "prompt_review_notes", []
                        ),
                        "content_hash": source.get("content_hash", ""),
                    }
                )
                rendered["solution_steps"] = []
                for step_index, step in enumerate(
                    teacher_block.get("solution_steps", []), start=1
                ):
                    if not isinstance(step, dict):
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
                word_evidence = source.get("word_evidence", {})
                if not isinstance(word_evidence, dict):
                    word_evidence = {}
                rendered["source_question_texts"] = self._word_evidence_texts(
                    word_evidence.get("question"), title_prefix="Word 原题来源"
                )
                rendered["official_solution_texts"] = self._word_evidence_texts(
                    word_evidence.get("official_solution"),
                    title_prefix="Word 官方解答来源",
                )
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
        summary["items"] = rendered_items
        return summary, preview_files

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
        source["content_hash"] = _canonical_hash(
            {
                "teacher": teacher,
                "student": student,
                "crop_hashes": {
                    crop_role: [
                        crop.get("output_sha256")
                        for crop in crop_entries
                        if isinstance(crop, dict)
                    ]
                    for crop_role, crop_entries in crops.items()
                    if isinstance(crop_entries, list)
                },
            }
        )

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

        detail, _ = self._staging_detail(record)
        return next(item for item in detail["items"] if item["id"] == item_id)

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
        source["content_hash"] = _canonical_hash(
            {
                "teacher": teacher,
                "student": student,
                "crop_hashes": {
                    crop_role: [
                        crop.get("output_sha256")
                        for crop in crop_entries
                        if isinstance(crop, dict)
                    ]
                    for crop_role, crop_entries in crops.items()
                    if isinstance(crop_entries, list)
                },
            }
        )
        _atomic_write_yaml(teacher_path, teacher)
        _atomic_write_yaml(student_path, student)
        _atomic_write_yaml(source_path, source)

        detail, _ = self._staging_detail(record)
        return next(item for item in detail["items"] if item["id"] == item_id)

    def write_staging_review(
        self, bank_id: str, item_id: str, decision: ReviewDecision
    ) -> dict[str, Any]:
        record = self.record(bank_id)
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

    def detail(self, bank_id: str) -> tuple[dict[str, Any], dict[tuple[str, str], Path]]:
        record = self.record(bank_id)
        if record.kind == "staging_exam":
            return self._staging_detail(record)
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
                    "explanation": "",
                    "solution_steps": [],
                    "prompt_preview_url": None,
                    "solution_preview_url": None,
                    "solution_previews": [],
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
                student_block = _practice_block(student_payload, item_id)
                teacher_block = _practice_block(teacher_payload, item_id)
                rendered["stem_latex"] = str(student_block.get("stem_latex", ""))
                rendered["answer"] = str(teacher_block.get("answer", ""))
                rendered["explanation"] = str(teacher_block.get("explanation", ""))
                steps = teacher_block.get("solution_steps", [])
                rendered_steps: list[dict[str, Any]] = []
                solution_previews: list[dict[str, str]] = []
                seen_solution_paths: set[Path] = set()
                for step_index, step in enumerate(steps):
                    if not isinstance(step, dict):
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


def create_question_bank_app(
    bank_root: str | Path = DEFAULT_BANK_ROOT,
    number_review_url: str = DEFAULT_NUMBER_REVIEW_URL,
) -> FastAPI:
    catalog = QuestionBankCatalog(bank_root)
    app = FastAPI(title="Question Bank Review", version="0.1.0")
    app.state.catalog = catalog
    app.state.number_review_url = number_review_url
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
        records, errors = catalog.discover()
        return {"ok": True, "banks": len(records), "errors": errors}

    @app.get("/api/banks")
    def list_banks() -> dict[str, Any]:
        records, errors = catalog.discover()
        return {
            "banks": [catalog.summary(record) for record in records],
            "errors": errors,
            "number_review_url": number_review_url,
        }

    @app.get("/api/banks/{bank_id}")
    def bank_detail(bank_id: str) -> dict[str, Any]:
        try:
            detail, _ = catalog.detail(bank_id)
            return detail
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="题库不存在") from exc

    @app.get("/api/assets/{bank_id}/{item_id}/{role}")
    def preview_asset(bank_id: str, item_id: str, role: str) -> FileResponse:
        try:
            _, files = catalog.detail(bank_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="题库不存在") from exc
        path = files.get((item_id, role))
        if path is None:
            raise HTTPException(status_code=404, detail="预览不存在")
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    @app.post("/api/banks/{bank_id}/items/{item_id}/review")
    def review_staging_item(
        bank_id: str, item_id: str, decision: ReviewDecision
    ) -> dict[str, Any]:
        try:
            return catalog.write_staging_review(bank_id, item_id, decision)
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

    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-root", type=Path, default=DEFAULT_BANK_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--number-review-url", default=DEFAULT_NUMBER_REVIEW_URL)
    args = parser.parse_args(argv)
    uvicorn.run(
        create_question_bank_app(args.bank_root, args.number_review_url),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
