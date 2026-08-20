#!/usr/bin/env python3
"""TeachingApproach authoring store & canonical freeze (Phase 3, P3-03..P3-08).

Working sidecar (per bank item, mutable working copy):

    <bank item dir>/teaching-approach.yaml      # math_item_teaching_approach/v1
    <bank item dir>/assets/teaching-approach/   # audio/transcript/polished files

Canonical immutable artifacts (mirror the question-truth registry semantics of
``canonical_export`` / ADR-002 + ADR-004):

    artifacts/canonical-authoring/
      teaching-approach/TA-SMV-00N/{v1.json, …, registry.yaml}
      audio/TA-SMV-00N/v1/<file>        # evidence copies made at freeze time
      transcript/TA-SMV-00N/v1/<file>
    id-allocations.yaml                  # + ta_next_seq / ta_allocations

Rules implemented here:

- evidence is append-only (P3-03): every recording/polish appends a new
  revision; old audio/transcript/polish files and refs are never overwritten
  or removed, so a re-record cannot destroy the previous evidence chain;
- the working sidecar carries question binding, author, reviewer and review
  note (P3-04); approval freezes an immutable ``ApprovedTeachingApproach.v1``
  (P3-07) whose ``question_ref`` must equal the QuestionTruth registry's
  current Approved version at freeze time (fail closed, P3-08);
- QuestionTruth changes propagate Stale into teaching-approach registries via
  the Phase 2 ``stale-events.yaml`` ledger; Stale versions stay readable but
  can never be frozen/published again (P3-08);
- a static answer-consistency check refuses to freeze an approach whose steps
  never state the QuestionTruth's answer / proof targets (fail closed);
- content_hash excludes identity/lifecycle fields exactly like question-truth
  (``canonical_export._HASH_EXCLUDED``), so re-approval and supersede never
  re-hash content.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

_PACKAGE_PARENT = Path(__file__).resolve().parents[4]
if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

from integrations.ai_teaching_contracts import (  # noqa: E402
    validate_for_publication,
    validate_payload,
)

import canonical_export as ce  # noqa: E402

__all__ = [
    "APPROACH_SCHEMA",
    "APPROACH_SIDECAR_FILE",
    "APPROACH_AUDIO_DIR",
    "TA_NAMESPACE",
    "TOPIC_SKILL_IDS",
    "TeachingApproachError",
    "sidecar_path",
    "load_sidecar",
    "save_sidecar",
    "question_binding",
    "next_local_id",
    "new_approach",
    "normalize_step",
    "append_manual_edit_note",
    "recording_revision",
    "polish_revision",
    "assignment_step_drafts",
    "static_answer_consistency",
    "allocate_ta_id",
    "freeze_approved_approach",
    "apply_question_change_stale",
    "read_approach_version",
    "approach_history",
    "current_approach",
    "approaches_for_question",
    "freeze_approach_set",
]

APPROACH_SCHEMA = "math_item_teaching_approach/v1"
APPROACH_SIDECAR_FILE = "teaching-approach.yaml"
APPROACH_AUDIO_DIR = "assets/teaching-approach"
TA_NAMESPACE = "teaching-approach"
TP_NAMESPACE = "tutor-plan"
AUDIO_NAMESPACE = "audio"
TRANSCRIPT_NAMESPACE = "transcript"
TA_ID_PATTERN = re.compile(r"^TA-[A-Z0-9]+-[0-9]{3,}$")
SKILL_ID_PATTERN = re.compile(r"^SKILL-[A-Z0-9]+-[0-9]{3,}$")

# MVP 相似三角形专题冻结的 canonical skill（源：PRDS migration/manifests/skill-scope.yaml）。
# 仅作为 UI 建议与 AI 草稿白名单；canonical 校验仍只认 SKILL- 模式。
TOPIC_SKILL_IDS = [
    "SKILL-SMV-001",
    "SKILL-SMV-002",
    "SKILL-SMV-003",
    "SKILL-SMV-005",
    "SKILL-SMV-006",
    "SKILL-SMV-007",
    "SKILL-SMV-008",
    "SKILL-SMV-009",
]



def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class TeachingApproachError(Exception):
    """Approach authoring/freeze failure (always fail closed)."""


# --------------------------------------------------------------------------- #
# Working sidecar
# --------------------------------------------------------------------------- #


def sidecar_path(item_dir: Path) -> Path:
    return item_dir / APPROACH_SIDECAR_FILE


def load_sidecar(item_dir: Path) -> dict[str, Any] | None:
    path = sidecar_path(item_dir)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        payload = ce._load_yaml(path)
    except Exception:
        return None
    if payload.get("schema") != APPROACH_SCHEMA or not isinstance(
        payload.get("approaches"), list
    ):
        return None
    return payload


def save_sidecar(item_dir: Path, payload: dict[str, Any]) -> None:
    path = sidecar_path(item_dir)
    if path.is_symlink():
        raise TeachingApproachError("teaching-approach.yaml 不允许为符号链接")
    ce._write_yaml_atomic(path, payload)


def question_binding(item_dir: Path, ledger_path: Path) -> dict[str, Any] | None:
    """item → canonical QuestionTruth 绑定（source.yaml source_key → ledger qt_id）。"""
    source_path = item_dir / "source.yaml"
    if source_path.is_symlink() or not source_path.is_file():
        return None
    try:
        source = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    source_key = str(source.get("source_key") or "").strip()
    if not source_key:
        return None
    if not ledger_path.is_file():
        return None
    try:
        ledger = ce._load_yaml(ledger_path)
    except Exception:
        return None
    allocation = (ledger.get("allocations") or {}).get(source_key)
    if not isinstance(allocation, dict):
        return None
    qt_id = str(allocation.get("qt_id") or "")
    if not qt_id:
        return None
    return {"source_key": source_key, "artifact_id": qt_id}


def next_local_id(payload: dict[str, Any]) -> str:
    numbers = [
        int(m.group(1))
        for approach in payload.get("approaches") or []
        if (m := re.fullmatch(r"t(\d+)", str(approach.get("id") or "")))
    ]
    return f"t{(max(numbers) + 1) if numbers else 1}"


def new_approach(payload: dict[str, Any], *, title: str, author: str) -> dict[str, Any]:
    return {
        "id": next_local_id(payload),
        "title": title.strip(),
        "author": author.strip() or "unknown-author",
        "status": "draft",
        "part_id": "",  # ADR-005：小问绑定（空 = 整题/无小问题）
        "goal": "",
        "entry_signal": "",
        "steps": [],
        "steps_origin": "none",
        "polished_text": "",
        "evidence": {"recordings": [], "polishes": [], "manual_edit_notes": []},
        "approval": None,
        "canonical": None,
        "created_at": ce._now(),
    }


_STEP_FIELDS = (
    "intent",
    "narration",
    "expected_student_reasoning",
    "accepted_alternatives",
    "common_errors",
    "skill_ids",
)


def normalize_step(step: Any, index: int, *, keep_origin: bool = True) -> dict[str, Any]:
    """Working step 归一化：字段固定、step_id 重排、skill_ids 过滤合法模式。"""
    if not isinstance(step, dict):
        raise TeachingApproachError(f"第 {index + 1} 个教学步骤不是对象")
    skill_ids = [
        str(item).strip()
        for item in (step.get("skill_ids") or [])
        if SKILL_ID_PATTERN.match(str(item).strip() or "")
    ]
    normalized: dict[str, Any] = {
        "step_id": f"S{index + 1}",
        "intent": str(step.get("intent") or "").strip(),
        "narration": str(step.get("narration") or "").strip(),
        "expected_student_reasoning": str(
            step.get("expected_student_reasoning") or ""
        ).strip(),
        "accepted_alternatives": [
            str(item).strip()
            for item in (step.get("accepted_alternatives") or [])
            if str(item).strip()
        ],
        "common_errors": [
            str(item).strip()
            for item in (step.get("common_errors") or [])
            if str(item).strip()
        ],
        "skill_ids": skill_ids,
    }
    if keep_origin:
        normalized["origin"] = str(step.get("origin") or "manual")
    return normalized


def append_manual_edit_note(
    approach: dict[str, Any], *, editor: str, fields: list[str]
) -> None:
    if not fields:
        return
    note = f"{ce._now()} editor={editor or 'unknown'} edited={','.join(sorted(set(fields)))}"
    approach.setdefault("evidence", {}).setdefault("manual_edit_notes", []).append(note)


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def recording_revision(
    approach: dict[str, Any],
    item_dir: Path,
    *,
    audio_bytes: bytes,
    suffix: str,
) -> dict[str, Any]:
    """Append-only 新录音修订（P3-03）：文件名含修订号，旧修订永不覆盖。"""
    recordings = approach.setdefault("evidence", {}).setdefault("recordings", [])
    revision = len(recordings) + 1
    audio_dir = item_dir / APPROACH_AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    stamp = ce._now().replace(":", "").replace("-", "").replace("+", "_")
    audio_name = f"{approach['id']}-r{revision:02d}-{stamp}{suffix}"
    audio_file = audio_dir / audio_name
    audio_file.write_bytes(audio_bytes)
    revision_entry = {
        "revision": revision,
        "audio_path": f"{APPROACH_AUDIO_DIR}/{audio_name}",
        "audio_sha256": _file_sha256(audio_file),
        "audio_bytes": len(audio_bytes),
        "recorded_at": ce._now(),
        "duration_seconds": None,
        "transcript": "",
        "transcript_path": None,
        "transcript_sha256": None,
        "asr": None,
        "transcribed_at": None,
    }
    recordings.append(revision_entry)
    return revision_entry


def attach_transcript(
    approach: dict[str, Any],
    item_dir: Path,
    revision_entry: dict[str, Any],
    *,
    transcript: str,
    asr: dict[str, str],
) -> None:
    """把 ASR 结果写进既有录音修订（转写稿另存文件，不覆盖音频）。"""
    audio_dir = item_dir / APPROACH_AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_name = Path(str(revision_entry["audio_path"])).name
    stem = audio_name.rsplit(".", 1)[0]
    transcript_name = f"{stem}.transcript.txt"
    transcript_file = audio_dir / transcript_name
    transcript_file.write_text(transcript, encoding="utf-8")
    revision_entry["transcript"] = transcript
    revision_entry["transcript_path"] = f"{APPROACH_AUDIO_DIR}/{transcript_name}"
    revision_entry["transcript_sha256"] = _file_sha256(transcript_file)
    revision_entry["asr"] = asr
    revision_entry["transcribed_at"] = ce._now()


def polish_revision(
    approach: dict[str, Any],
    item_dir: Path,
    *,
    polished_text: str,
    provenance: dict[str, str],
    based_on_recording: int,
) -> dict[str, Any]:
    """Append-only 新润色修订（P3-03）：润色稿另存文件，转写稿与旧润色不动。"""
    polishes = approach.setdefault("evidence", {}).setdefault("polishes", [])
    revision = len(polishes) + 1
    audio_dir = item_dir / APPROACH_AUDIO_DIR
    audio_dir.mkdir(parents=True, exist_ok=True)
    stamp = ce._now().replace(":", "").replace("-", "").replace("+", "_")
    polished_name = f"{approach['id']}-p{revision:02d}-{stamp}.polished.txt"
    polished_file = audio_dir / polished_name
    polished_file.write_text(polished_text, encoding="utf-8")
    entry = {
        "revision": revision,
        "based_on_recording": based_on_recording,
        "polished_path": f"{APPROACH_AUDIO_DIR}/{polished_name}",
        "polished_sha256": _file_sha256(polished_file),
        "polished_at": ce._now(),
        "provenance": provenance,
    }
    polishes.append(entry)
    return entry


def assignment_step_drafts(teacher_block: dict[str, Any]) -> list[dict[str, Any]]:
    """P3-05 确定性脚手架：从 assignment solution_steps/clue 初始化 TeachingStep 草稿。

    无 solution_steps 的题（填空/选择）退化为 读题标注→关系转化→求解作答 三步骨架。
    草稿刻意把 skill_ids 留空——批准门禁要求教师逐步补齐（AI 只建议，教师编辑）。
    """
    steps_text: list[str] = []
    raw_steps = teacher_block.get("solution_steps")
    if isinstance(raw_steps, list):
        steps_text = [str(step).strip() for step in raw_steps if str(step).strip()]
    if not steps_text:
        clue = str(teacher_block.get("clue") or "").strip()
        answer = str(teacher_block.get("answer") or "").strip()
        steps_text = [
            clue or "通读题目，标注已知条件与求解目标。",
            "把已知条件转化为图形或比例关系，确定使用的模型。",
            f"完成计算/推理并核对结论。参考答案：{answer or '（见题库）'}",
        ]
    drafts: list[dict[str, Any]] = []
    for index, text in enumerate(steps_text):
        drafts.append(
            {
                "step_id": f"S{index + 1}",
                "intent": f"推进第 {index + 1} 步",
                "narration": text,
                "expected_student_reasoning": "",
                "accepted_alternatives": [],
                "common_errors": [],
                "skill_ids": [],
                "origin": "assignment",
            }
        )
    return drafts


# --------------------------------------------------------------------------- #
# Static answer consistency (fail closed)
# --------------------------------------------------------------------------- #

_PROVE_TARGET = re.compile(r"求证[：:]\s*([^；;。.]+)")
_MATH_SEGMENT = re.compile(r"\$([^$]+)\$")


def _normalize_math_text(value: str) -> str:
    lowered = str(value or "")
    for token in ("$", "\\,", "\\;", "\\!", "\\ ", "\\left", "\\right"):
        lowered = lowered.replace(token, "")
    lowered = lowered.replace("\\cdot", "·").replace("\\times", "×")
    lowered = lowered.replace("\\perp", "⊥").replace("\\parallel", "∥")
    lowered = lowered.replace("\\sim", "∽").replace("\\triangle", "△")
    lowered = lowered.replace("{", "").replace("}", "")
    return re.sub(r"\s+", "", lowered)


def _answer_targets(
    truth_payload: dict[str, Any], part_id: str | None = None
) -> list[tuple[str, str]]:
    """提取静态可核验的答案目标：求证目标 + canonical_answer 的 $…$ 数学片段。

    ADR-005：part_id 给定时目标取自该小问（prompt 的求证目标 + 小问级
    canonical_answer）；v2 有小问的 Truth 顶层不再有答案，part_id 为空时对
    多小问题退回整题混合目标（兼容 v1 存量）。提取不到任何目标返回空列表
    （调用方 fail closed）。
    """
    targets: list[tuple[str, str]] = []
    if part_id:
        parts = truth_payload.get("subquestions") or []
        part = next(
            (p for p in parts if str(p.get("part_id") or "") == part_id), None
        )
        if part is None:
            return []
        stem = str(part.get("prompt") or "")
        answer = part.get("canonical_answer") or {}
    else:
        stem = str(truth_payload.get("stem") or "")
        subq_prompts = "；".join(
            str(p.get("prompt") or "") for p in truth_payload.get("subquestions") or []
        )
        stem = f"{stem}；{subq_prompts}" if subq_prompts else stem
        answer = truth_payload.get("canonical_answer") or {}
    for match in _PROVE_TARGET.finditer(stem):
        # 求证：(1) $…$；(2) $…$ —— 捕获里会带小问序号前缀，剥掉再比对。
        captured = re.sub(r"^[（(]\s*[0-9]\s*[）)]\s*", "", match.group(1)).strip()
        target = _normalize_math_text(captured)
        if len(target) >= 2:
            targets.append((f"求证目标 {captured}", target))
    if answer.get("kind") == "choice_option":
        for option in answer.get("options") or []:
            value = _normalize_math_text(str(option.get("value") or ""))
            if value:
                targets.append((f"选项 {option.get('id')}", value))
    else:
        raw_value = str(answer.get("value") or "")
        for segment in _MATH_SEGMENT.findall(raw_value):
            target = _normalize_math_text(segment)
            # 答案片段保留单字符目标（如 "$1$"/"$6$"）：规范化后做子串匹配，
            # 单字符偶有误放行风险，由人工审核 + 求证目标兜底（MVP 取舍）。
            if target:
                targets.append((f"答案片段 {segment.strip()}", target))
    return targets


def static_answer_consistency(
    truth_payload: dict[str, Any],
    steps: list[dict[str, Any]],
    part_id: str | None = None,
) -> list[str]:
    """静态答案一致性（fail closed）：教学步骤必须陈述 Truth 的答案/求证目标。

    目标 = 求证目标 + 答案数学片段，全部必须出现在步骤文本（narration ∪
    expected_student_reasoning）中；提取不到任何目标也视为失败（宁可拒绝）。
    ADR-005：part_id 给定时只对照该小问的目标。
    """
    steps_text = _normalize_math_text(
        " ".join(
            str(step.get("narration") or "")
            + " "
            + str(step.get("expected_student_reasoning") or "")
            for step in steps
        )
    )
    targets = _answer_targets(truth_payload, part_id)
    if not targets:
        return ["无法从 QuestionTruth 提取可验证的答案/求证目标（fail closed）"]
    problems: list[str] = []
    for label, target in targets:
        if target not in steps_text:
            problems.append(f"{label} 未出现在教学步骤中（期望含「{target}」）")
    return problems


# --------------------------------------------------------------------------- #
# TA id allocation ledger
# --------------------------------------------------------------------------- #


def _ledger_all_ta_ids(ledger: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for entries in (ledger.get("ta_allocations") or {}).values():
        if isinstance(entries, list):
            for entry in entries:
                if isinstance(entry, dict) and entry.get("ta_id"):
                    used.add(str(entry["ta_id"]))
    return used


def allocate_ta_id(
    ledger_path: Path, *, qt_id: str, local_id: str, title: str
) -> str:
    """(qt_id, local_id) → 稳定 TA id；新分配从 ta_next_seq 递增，冲突 fail closed。"""
    ledger = ce._load_yaml(ledger_path)
    if not isinstance(ledger.get("allocations"), dict):
        raise TeachingApproachError(f"{ledger_path}: 缺少 allocations 段")
    by_question = ledger.setdefault("ta_allocations", {})
    existing = by_question.get(qt_id) or []
    if not isinstance(existing, list):
        raise TeachingApproachError(f"{ledger_path}: ta_allocations.{qt_id} 结构非法")
    for entry in existing:
        if isinstance(entry, dict) and str(entry.get("local_id") or "") == local_id:
            return str(entry["ta_id"])
    used = _ledger_all_ta_ids(ledger)
    seq = int(ledger.get("ta_next_seq") or 1)
    while True:
        candidate = f"TA-SMV-{seq:03d}"
        if candidate not in used:
            break
        seq += 1
    existing.append(
        {
            "local_id": local_id,
            "ta_id": candidate,
            "title": title.strip(),
            "allocated_at": ce._now(),
        }
    )
    by_question[qt_id] = existing
    ledger["ta_next_seq"] = seq + 1
    ce._write_yaml_atomic(ledger_path, ledger)
    return candidate


def _ta_registry_path(ta_id: str, root: Path) -> Path:
    return root / TA_NAMESPACE / ta_id / "registry.yaml"


def _ta_version_path(ta_id: str, version: str, root: Path) -> Path:
    return root / TA_NAMESPACE / ta_id / f"{version}.json"


# --------------------------------------------------------------------------- #
# Canonical freeze (P3-07)
# --------------------------------------------------------------------------- #


def _validate_working_approach(approach: dict[str, Any]) -> None:
    if not str(approach.get("title") or "").strip():
        raise TeachingApproachError("教学策略缺少标题（title）")
    if not str(approach.get("goal") or "").strip():
        raise TeachingApproachError("教学策略缺少教学目标（goal）")
    steps = approach.get("steps") or []
    if len(steps) < 3:
        raise TeachingApproachError(f"TeachingStep 至少 3 个（当前 {len(steps)}）")
    for index, step in enumerate(steps):
        step_id = str(step.get("step_id") or f"S{index + 1}")
        for field in ("intent", "narration", "expected_student_reasoning"):
            if not str(step.get(field) or "").strip():
                raise TeachingApproachError(f"{step_id}.{field} 为空：请教师补齐后再批准")
        if not (step.get("skill_ids") or []):
            raise TeachingApproachError(f"{step_id}.skill_ids 为空：请教师补齐后再批准")


def _canonical_evidence(
    approach: dict[str, Any], item_dir: Path, *, ta_id: str, version: str, root: Path
) -> dict[str, Any]:
    """构造 canonical evidence；音频/转写/润色文件按 hash 复制成不可变工件。"""
    evidence = approach.get("evidence") or {}
    audio_items: list[dict[str, Any]] = []
    transcript_items: list[dict[str, Any]] = []
    for entry in evidence.get("recordings") or []:
        audio_file = item_dir / str(entry.get("audio_path") or "")
        if not audio_file.is_file():
            raise TeachingApproachError(
                f"录音修订 {entry.get('revision')} 的音频文件缺失：{entry.get('audio_path')}"
            )
        if _file_sha256(audio_file) != entry.get("audio_sha256"):
            raise TeachingApproachError(
                f"录音修订 {entry.get('revision')} 的音频 hash 漂移（fail closed）"
            )
        audio_name = audio_file.name
        _copy_evidence_file(
            audio_file, root / AUDIO_NAMESPACE / ta_id / version / audio_name
        )
        audio_items.append(
            {
                "artifact_uri": f"artifact://{AUDIO_NAMESPACE}/{ta_id}@{version}/{audio_name}",
                "content_hash": entry["audio_sha256"],
                "recorded_at": entry.get("recorded_at") or ce._now(),
                **(
                    {"duration_seconds": entry["duration_seconds"]}
                    if entry.get("duration_seconds")
                    else {}
                ),
            }
        )
        if entry.get("transcript"):
            transcript_file = item_dir / str(entry.get("transcript_path") or "")
            if not transcript_file.is_file():
                raise TeachingApproachError(
                    f"录音修订 {entry.get('revision')} 的转写稿文件缺失"
                )
            transcript_name = transcript_file.name
            _copy_evidence_file(
                transcript_file,
                root / TRANSCRIPT_NAMESPACE / ta_id / version / transcript_name,
            )
            transcript_items.append(
                {
                    "artifact_uri": (
                        f"artifact://{TRANSCRIPT_NAMESPACE}/{ta_id}@{version}/"
                        f"{transcript_name}"
                    ),
                    "asr_provenance": {
                        "provider": str((entry.get("asr") or {}).get("provider", "")),
                        "model_id": str((entry.get("asr") or {}).get("model_id", "")),
                    },
                    "revision": int(entry.get("revision") or 0),
                }
            )
    polished_items: list[dict[str, Any]] = []
    for entry in evidence.get("polishes") or []:
        polished_file = item_dir / str(entry.get("polished_path") or "")
        if not polished_file.is_file():
            raise TeachingApproachError(f"润色修订 {entry.get('revision')} 的文件缺失")
        polished_name = polished_file.name
        _copy_evidence_file(
            polished_file, root / TRANSCRIPT_NAMESPACE / ta_id / version / polished_name
        )
        provenance = entry.get("provenance") or {}
        polished_items.append(
            {
                "artifact_uri": (
                    f"artifact://{TRANSCRIPT_NAMESPACE}/{ta_id}@{version}/"
                    f"{polished_name}"
                ),
                "polish_provenance": {
                    "provider": str(provenance.get("provider", "")),
                    "model_id": str(provenance.get("model_id", "")),
                    "prompt_version": str(provenance.get("prompt_version", "")),
                },
            }
        )
    return {
        "audio": audio_items,
        "transcripts": transcript_items,
        "polished": polished_items,
        "manual_edit_notes": [
            str(note) for note in evidence.get("manual_edit_notes") or []
        ],
    }


def _copy_evidence_file(source: Path, target: Path) -> None:
    if target.is_file():
        # 已有不可变副本：hash 一致即幂等，不一致 fail closed。
        if _file_sha256(target) == _file_sha256(source):
            return
        raise TeachingApproachError(f"证据文件冲突（不可变副本已存在且内容不同）：{target.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())


def freeze_approved_approach(
    approach: dict[str, Any],
    item_dir: Path,
    *,
    reviewer_id: str,
    review_note: str,
    qt_id: str,
    ledger_path: Path,
    root: Path | None = None,
    part_id: str | None = None,
) -> dict[str, Any]:
    """批准并冻结 canonical ApprovedTeachingApproach.v2（不可变，P3-07/ADR-005）。

    门禁（全部 fail closed，任何一步失败都不写文件）：
    工作区结构完整（≥3 步、字段齐、skill_refs）→ 绑定 QuestionTruth 当前
    Approved 版本（含 part 绑定合法性：QT 含 subquestions 时 part_id 必填且
    必须命中，无小问时必须省略）→ 静态答案一致性（对照绑定 part 的目标）→
    contracts schema + publication 校验 → 写 version 文件 + registry
    （同 id 重批 → v<N+1>，旧版 Superseded）。
    """
    root = root or ce.CANONICAL_ROOT
    _validate_working_approach(approach)
    if not str(reviewer_id or "").strip():
        raise TeachingApproachError("批准需要 reviewer_id")

    truth = ce.current_truth(qt_id, root=root)
    if truth.get("status") != "Approved":
        raise TeachingApproachError(
            f"{qt_id}: QuestionTruth current 版本不是 Approved，拒绝冻结"
        )
    subquestion_ids = [
        str(part.get("part_id") or "") for part in truth.get("subquestions") or []
    ]
    bound_part_id = str(part_id or "").strip() or None
    if subquestion_ids:
        if bound_part_id is None:
            raise TeachingApproachError(
                f"{qt_id}: QuestionTruth 含小问 {subquestion_ids}，TeachingApproach "
                "必须绑定具体小问（ADR-005 part_id）"
            )
        if bound_part_id not in subquestion_ids:
            raise TeachingApproachError(
                f"{qt_id}: part_id {bound_part_id} 不在小问列表 {subquestion_ids}"
            )
    elif bound_part_id is not None:
        raise TeachingApproachError(
            f"{qt_id}: QuestionTruth 无小问，TeachingApproach 不得携带 part_id"
        )
    question_ref: dict[str, Any] = {
        "artifact_id": qt_id,
        "version": truth["version"],
        "content_hash": truth["content_hash"],
    }
    if bound_part_id is not None:
        question_ref["part_id"] = bound_part_id
    consistency = static_answer_consistency(truth, approach["steps"], bound_part_id)
    if consistency:
        raise TeachingApproachError(
            "静态答案一致性检查失败（fail closed）：" + "；".join(consistency)
        )

    ta_id = allocate_ta_id(
        ledger_path,
        qt_id=qt_id,
        local_id=str(approach["id"]),
        title=str(approach.get("title") or ""),
    )
    registry_path = _ta_registry_path(ta_id, root)
    registry = (
        ce._load_yaml(registry_path)
        if registry_path.is_file()
        else {"artifact_id": ta_id, "current_version": None, "versions": []}
    )
    if registry.get("artifact_id") != ta_id:
        raise TeachingApproachError(f"{registry_path}: artifact_id mismatch")
    current_version = registry.get("current_version")
    versions: list[dict[str, Any]] = list(registry.get("versions") or [])
    next_version = (
        f"v{int(current_version[1:]) + 1}" if current_version is not None else "v1"
    )

    evidence = _canonical_evidence(
        approach, item_dir, ta_id=ta_id, version=next_version, root=root
    )
    payload: dict[str, Any] = {
        "schema": "ai_teaching_teaching_approach/v2",
        "artifact_id": ta_id,
        "version": next_version,
        "status": "Approved",
        "question_ref": question_ref,
        "title": str(approach["title"]).strip(),
        "goal": str(approach["goal"]).strip(),
        "entry_signal": str(approach.get("entry_signal") or "").strip(),
        "steps": [
            {
                "step_id": step["step_id"],
                "intent": step["intent"],
                "narration": step["narration"],
                "expected_student_reasoning": step["expected_student_reasoning"],
                **(
                    {"accepted_alternatives": step["accepted_alternatives"]}
                    if step.get("accepted_alternatives")
                    else {}
                ),
                **(
                    {"common_errors": step["common_errors"]}
                    if step.get("common_errors")
                    else {}
                ),
                "skill_ids": step["skill_ids"],
            }
            for step in approach["steps"]
        ],
        "evidence": evidence,
        "approval": {
            "reviewer_id": reviewer_id.strip(),
            "approved_at": ce._now(),
            "review_note": review_note.strip() or None,
        },
        "content_hash": "",
        "artifact_uri": f"artifact://{TA_NAMESPACE}/{ta_id}@{next_version}",
    }
    payload["content_hash"] = ce._content_hash(payload)

    ok, errors = validate_payload(payload)
    if not ok:
        raise TeachingApproachError(f"{ta_id}: canonical schema invalid: {errors}")
    publication_errors = validate_for_publication(payload)
    if publication_errors:
        raise TeachingApproachError(
            f"{ta_id}: publication validation failed (fail closed): "
            f"{[str(e) for e in publication_errors]}"
        )

    ce._write_json_atomic(_ta_version_path(ta_id, next_version, root), payload)
    if current_version is not None:
        current_file = _ta_version_path(ta_id, current_version, root)
        old_payload = _read_json(current_file)
        old_payload["status"] = "Superseded"
        old_payload["superseded_by"] = {"artifact_id": ta_id, "version": next_version}
        ce._write_json_atomic(current_file, old_payload)
        versions = [
            dict(
                entry,
                status="Superseded",
                superseded_by={"artifact_id": ta_id, "version": next_version},
            )
            if entry.get("version") == current_version
            else entry
            for entry in versions
        ]
    versions.append(
        {
            "version": next_version,
            "status": "Approved",
            "content_hash": payload["content_hash"],
            "approved_at": payload["approval"]["approved_at"],
            "question_ref": question_ref,
        }
    )
    registry["current_version"] = next_version
    registry["versions"] = versions
    ce._write_yaml_atomic(registry_path, registry)
    return payload


# --------------------------------------------------------------------------- #
# Stale propagation (P3-08)
# --------------------------------------------------------------------------- #


def apply_question_change_stale(root: Path | None = None) -> dict[str, Any]:
    """读 Phase 2 stale-events.yaml，把绑定旧 QuestionTruth 版本的 TA/TP registry 标 Stale。

    幂等：已 Stale 的条目跳过。Stale 版本文件与 registry 都保留（可读），
    但不再是 current Approved，后续编译/发布只认 current + Approved。
    Phase 4 起同轮传播 tutor-plan（stale-events.yaml 的 downstream 声明本就
    包含 {type: tutor-plan, action: stale}；TP registry 条目与 TA 同样携带
    question_ref，复用同一判定）。
    """
    root = root or ce.CANONICAL_ROOT
    events_path = root / "stale-events.yaml"
    if not events_path.is_file():
        return {"events_applied": 0, "stale_versions": []}
    data = ce._load_yaml(events_path)
    changed: list[str] = []
    for event in data.get("events") or []:
        if not isinstance(event, dict) or event.get("kind") != "question_change":
            continue
        question = event.get("question") or {}
        qt_id = str(question.get("artifact_id") or "")
        to_version = str(question.get("to_version") or "")
        if not qt_id or not to_version:
            continue
        try:
            truth_registry = ce._load_yaml(
                root / ce.QT_NAMESPACE / qt_id / "registry.yaml"
            )
        except Exception:
            continue
        for namespace, prefix in ((TA_NAMESPACE, "TA"), (TP_NAMESPACE, "TP")):
            namespace_root = root / namespace
            if not namespace_root.is_dir():
                continue
            for registry_file in sorted(
                namespace_root.glob(f"{prefix}-*/registry.yaml")
            ):
                registry = ce._load_yaml(registry_file)
                mutated = False
                for entry in registry.get("versions") or []:
                    ref = entry.get("question_ref") or {}
                    if (
                        str(ref.get("artifact_id") or "") == qt_id
                        and str(ref.get("version") or "") != to_version
                        and entry.get("status") == "Approved"
                    ):
                        entry["status"] = "Stale"
                        version_file = (
                            registry_file.parent / f"{entry.get('version')}.json"
                        )
                        if version_file.is_file():
                            payload = _read_json(version_file)
                            payload["status"] = "Stale"
                            ce._write_json_atomic(version_file, payload)
                        mutated = True
                        changed.append(
                            f"{registry.get('artifact_id')}@{entry.get('version')}"
                        )
                if mutated:
                    ce._write_yaml_atomic(registry_file, registry)
    return {"events_applied": len(changed), "stale_versions": changed}


# --------------------------------------------------------------------------- #
# Registry reads (Phase 4 compiler 入口)
# --------------------------------------------------------------------------- #


def read_approach_version(
    ta_id: str, version: str, *, root: Path | None = None
) -> dict[str, Any]:
    root = root or ce.CANONICAL_ROOT
    path = _ta_version_path(ta_id, version, root)
    if not path.is_file():
        raise TeachingApproachError(f"unknown teaching approach version: {path}")
    payload = _read_json(path)
    expected = payload.get("content_hash")
    actual = ce._content_hash(payload)
    if expected != actual:
        raise TeachingApproachError(
            f"{ta_id}@{version}: content_hash drift — refusing to serve"
        )
    return payload


def approach_history(ta_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or ce.CANONICAL_ROOT
    path = _ta_registry_path(ta_id, root)
    if not path.is_file():
        raise TeachingApproachError(f"unknown teaching approach: {ta_id}")
    registry = ce._load_yaml(path)
    for entry in registry.get("versions") or []:
        read_approach_version(ta_id, str(entry.get("version")), root=root)
    return registry


def current_approach(ta_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or ce.CANONICAL_ROOT
    registry = approach_history(ta_id, root=root)
    current = str(registry.get("current_version") or "")
    return read_approach_version(ta_id, current, root=root)


def approaches_for_question(
    qt_id: str,
    *,
    ledger_path: Path,
    root: Path | None = None,
    part_id: str | None = None,
) -> list[dict[str, Any]]:
    """该 QuestionTruth 当前 Approved 的全部 TeachingApproach（Compiler 读取入口）。

    ADR-005：part_id 给定时只返回绑定该小问的 TA（v1 存量整题 TA 不带
    part_id，不命中任何 part 查询）；省略时返回该题全部当前 Approved TA。
    """
    root = root or ce.CANONICAL_ROOT
    ledger = ce._load_yaml(ledger_path)
    entries = (ledger.get("ta_allocations") or {}).get(qt_id) or []
    wanted_part = str(part_id or "").strip() or None
    current_list: list[dict[str, Any]] = []
    for entry in entries:
        ta_id = str(entry.get("ta_id") or "")
        if not ta_id:
            continue
        registry = ce._load_yaml(_ta_registry_path(ta_id, root))
        current = str(registry.get("current_version") or "")
        payload = read_approach_version(ta_id, current, root=root)
        if payload.get("status") != "Approved":
            continue
        bound = str((payload.get("question_ref") or {}).get("part_id") or "") or None
        if wanted_part is not None and bound != wanted_part:
            continue
        current_list.append(payload)
    return current_list


# --------------------------------------------------------------------------- #
# ApproachSet freeze（ADR-005 §5：跨小问组合层，每题一份）
# --------------------------------------------------------------------------- #

AS_NAMESPACE = "approach-set"
AS_ID_PATTERN = re.compile(r"^AS-[A-Z0-9]+-[0-9]{3,}$")


def _as_registry_path(as_id: str, root: Path) -> Path:
    return root / AS_NAMESPACE / as_id / "registry.yaml"


def _as_version_path(as_id: str, version: str, root: Path) -> Path:
    return root / AS_NAMESPACE / as_id / f"{version}.json"


def freeze_approach_set(
    qt_id: str,
    parts: list[dict[str, Any]],
    *,
    reviewer_id: str,
    review_note: str,
    ledger_path: Path,
    root: Path | None = None,
    cross_part_rhythm: str | None = None,
) -> dict[str, Any]:
    """批准并冻结 canonical ApprovedApproachSet.v1（不可变，ADR-005 §5）。

    门禁（全部 fail closed）：
    - QT current 版本必须 Approved；parts 与 QT subquestions 一一对应
      （无小问题时只允许一个省略 part_id 的整题 part）；
    - 每个引用的 TA 必须 current Approved，且 question_ref 三元组与本 QT
      current 完全一致、part_id 与所在 part 匹配（alternates 同样校验）；
    - contracts schema + publication 校验后写 version 文件 + registry
      （同 id 重冻 → v<N+1>，旧版 Superseded）；AS id 从账本 as_next_seq 分配。
    """
    root = root or ce.CANONICAL_ROOT
    if not str(reviewer_id or "").strip():
        raise TeachingApproachError("批准需要 reviewer_id")
    truth = ce.current_truth(qt_id, root=root)
    if truth.get("status") != "Approved":
        raise TeachingApproachError(f"{qt_id}: QuestionTruth current 不是 Approved，拒绝冻结")
    question_ids = [str(p.get("part_id") or "") for p in truth.get("subquestions") or []]
    part_ids = [str(part.get("part_id") or "") for part in parts]
    if question_ids:
        if part_ids != question_ids:
            raise TeachingApproachError(
                f"{qt_id}: parts {part_ids} 与小问 {question_ids} 不一一对应"
            )
    else:
        if len(parts) != 1 or part_ids != [""]:
            raise TeachingApproachError(f"{qt_id}: 无小问，只允许一个整题 part")

    def _check_approach_ref(ref: dict[str, Any], expected_part: str) -> dict[str, Any]:
        ta_id = str(ref.get("artifact_id") or "")
        if not TA_ID_PATTERN.match(ta_id):
            raise TeachingApproachError(f"非法 TA id：{ta_id!r}")
        current = read_approach_version(ta_id, str(ref.get("version") or ""), root=root)
        if current.get("status") != "Approved":
            raise TeachingApproachError(f"{ta_id}@{ref.get('version')}: 不是 Approved，拒绝引用")
        bound = current.get("question_ref") or {}
        if (
            bound.get("artifact_id") != qt_id
            or bound.get("version") != truth["version"]
            or bound.get("content_hash") != truth["content_hash"]
            or str(bound.get("part_id") or "") != expected_part
        ):
            raise TeachingApproachError(
                f"{ta_id}: question_ref 与 QT current 或 part 不匹配，拒绝引用"
            )
        if current.get("content_hash") != str(ref.get("content_hash") or ""):
            raise TeachingApproachError(f"{ta_id}: 引用 content_hash 与版本文件不一致")
        return current

    canonical_parts: list[dict[str, Any]] = []
    for part in parts:
        expected = str(part.get("part_id") or "")
        primary = _check_approach_ref(part["approach"], expected)
        canonical_parts.append(
            {
                **({"part_id": expected} if expected else {}),
                "approach": {
                    "artifact_id": primary["artifact_id"],
                    "version": primary["version"],
                    "content_hash": primary["content_hash"],
                },
                **(
                    {
                        "alternates": [
                            {
                                "artifact_id": alt_c["artifact_id"],
                                "version": alt_c["version"],
                                "content_hash": alt_c["content_hash"],
                            }
                            for alt_c in (
                                _check_approach_ref(ref, expected)
                                for ref in part.get("alternates") or []
                            )
                        ]
                    }
                    if part.get("alternates")
                    else {}
                ),
                **({"note": str(part["note"])} if part.get("note") else {}),
            }
        )

    ledger = ce._load_yaml(ledger_path)
    by_question = ledger.setdefault("as_allocations", {})
    as_id = str(by_question.get(qt_id) or "")
    if not as_id:
        seq = int(ledger.get("as_next_seq") or 1)
        while True:
            as_id = f"AS-SMV-{seq:03d}"
            used = {
                entry
                for entries in by_question.values()
                if isinstance(entries, str)
                for entry in [entries]
            }
            if as_id not in used:
                break
            seq += 1
        ledger["as_next_seq"] = seq + 1
        by_question[qt_id] = as_id
        ce._write_yaml_atomic(ledger_path, ledger)

    registry_path = _as_registry_path(as_id, root)
    registry = (
        ce._load_yaml(registry_path)
        if registry_path.is_file()
        else {"artifact_id": as_id, "current_version": None, "versions": []}
    )
    current_version = registry.get("current_version")
    versions: list[dict[str, Any]] = list(registry.get("versions") or [])
    next_version = (
        f"v{int(current_version[1:]) + 1}" if current_version is not None else "v1"
    )
    payload: dict[str, Any] = {
        "schema": "ai_teaching_approach_set/v1",
        "artifact_id": as_id,
        "version": next_version,
        "status": "Approved",
        "question_ref": {
            "artifact_id": qt_id,
            "version": truth["version"],
            "content_hash": truth["content_hash"],
        },
        "parts": canonical_parts,
        **({"cross_part_rhythm": cross_part_rhythm} if cross_part_rhythm else {}),
        "approval": {
            "reviewer_id": reviewer_id.strip(),
            "approved_at": ce._now(),
            "review_note": review_note.strip() or None,
        },
        "content_hash": "",
        "artifact_uri": f"artifact://{AS_NAMESPACE}/{as_id}@{next_version}",
    }
    payload["content_hash"] = ce._content_hash(payload)

    ok, errors = validate_payload(payload)
    if not ok:
        raise TeachingApproachError(f"{as_id}: canonical schema invalid: {errors}")
    publication_errors = validate_for_publication(payload)
    if publication_errors:
        raise TeachingApproachError(
            f"{as_id}: publication validation failed (fail closed): "
            f"{[str(e) for e in publication_errors]}"
        )

    ce._write_json_atomic(_as_version_path(as_id, next_version, root), payload)
    if current_version is not None:
        current_file = _as_version_path(as_id, current_version, root)
        old_payload = _read_json(current_file)
        old_payload["status"] = "Superseded"
        old_payload["superseded_by"] = {"artifact_id": as_id, "version": next_version}
        ce._write_json_atomic(current_file, old_payload)
        versions = [
            dict(
                entry,
                status="Superseded",
                superseded_by={"artifact_id": as_id, "version": next_version},
            )
            if entry.get("version") == current_version
            else entry
            for entry in versions
        ]
    versions.append(
        {
            "version": next_version,
            "status": "Approved",
            "content_hash": payload["content_hash"],
            "approved_at": payload["approval"]["approved_at"],
            "question_ref": payload["question_ref"],
        }
    )
    registry["current_version"] = next_version
    registry["versions"] = versions
    ce._write_yaml_atomic(registry_path, registry)
    return payload
