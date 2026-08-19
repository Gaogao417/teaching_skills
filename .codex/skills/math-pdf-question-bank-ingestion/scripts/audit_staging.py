#!/usr/bin/env python3
"""Audit a staged exam and build compact visual contact sheets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageOps
import yaml


ROLES = ("question_evidence", "prompt", "solution", "official_solution")
FORBIDDEN_STUDENT_KEYS = {
    "answer",
    "clue",
    "solution_steps",
    "solution_notes",
    "source_solution_images",
    "teaching",
}
# An embedded option label is a leading A–D / 0–3 followed by a separator.
# Numeric separators split: ``、`` / ``．`` (CJK) can never start a decimal, but a
# half-width ``.`` may — ``3.14`` / ``0.3`` / ``3.0 \times 10^8`` are option *bodies*,
# not labels. The ``.`` branch therefore requires the next char to be non-digit.
EMBEDDED_CHOICE_LABEL = re.compile(
    r"^\s*(?:"
    r"(?:[A-Da-d]|[0-3])\s*[、．]\s*"  # CJK 顿号/全角句号:不可能是小数
    r"|(?:[A-Da-d])\s*\.\s*"  # 半角点 + 字母:A./B. 等标签
    r"|(?:[0-3])\s*\.(?!\d)\s*"  # 半角点 + 数字:后不接数字才算标签(排除 3.14)
    r"|[（(]\s*(?:[A-Da-d]|[0-3])\s*[）)]\s*"  # 括号包裹:（A）(0)
    r")"
)
# Strips a leading label to recover the option body. Mirrors EMBEDDED_CHOICE_LABEL
# but used only when all four choices form a complete ordered A–D / 0–3 sequence, so
# the renderer can re-add labels deterministically.
_CHOICE_LABEL_PREFIX = re.compile(
    r"^\s*(?:"
    r"(?:[A-Da-d]|[0-3])\s*[、．]\s*"
    r"|(?:[A-Da-d])\s*\.\s*"
    r"|(?:[0-3])\s*\.(?!\d)\s*"
    r"|[（(]\s*(?:[A-Da-d]|[0-3])\s*[）)]\s*"
    r")"
)
# Complete ordered label sequences whose prefix the renderer can re-emit itself.
_COMPLETE_LETTER_SEQUENCE = ("A", "B", "C", "D")
_COMPLETE_DIGIT_SEQUENCE = ("0", "1", "2", "3")
# 题干里指向配图的强信号短语。只匹配这些明确「指代一张图」的表达，不匹配裸
# 「图」字——「中心对称图形」「轴对称图形」「函数图象」「统计图」「柱状图」等
# 纯文字描述会误报。命中即要求题目配了 prompt crop。
FIGURE_REFERENCE = re.compile(r"如图|图所示|下图|上图|图中|示意图")

# 源缺题声明（missing-questions.yaml，放在原始源文件旁，与 non-question-pages.yaml
# 同一约定）。题号连续性不变式 fail-closed：题号必须从 1 连续递增到末题；断档只有
# 在显式声明该题「原始源材料中不存在」时才放行（例如公众号扫描件丢版面：答案页有
# 「6. C」但试卷页从第 5 题直接跳到第 7 题）。
MISSING_QUESTIONS_SCHEMA = "math_missing_questions/v1"
MISSING_QUESTION_REASONS = ("source_scan_missing", "source_omitted", "other")
MISSING_QUESTIONS_FILENAME = "missing-questions.yaml"

# 转写占位符标记：整卷转写模型在逐页文本中找不到对应内容时，会把这些说明性
# 文字写进题干/选项/解答。措辞有变体（「未出现在所给逐页文本中」「未出现在
# 给定页文本中」「未出现在识别文本中」…），统一按「未出现在…文本」正则匹配。
# 审计不拦截（占位符是模型的诚实报告），但必须以 WARNING 显式暴露，人工在
# Review UI 补全或确认源缺后才能批准。
TRANSCRIPTION_PLACEHOLDER_RE = re.compile(r"未出现在.{0,6}文本")


def find_transcription_placeholder(value: Any) -> str | None:
    """返回 teacher 内容里命中的占位符片段（无则 None）。"""
    try:
        blob = json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return None
    match = TRANSCRIPTION_PLACEHOLDER_RE.search(blob)
    return match.group(0) if match else None


def normalize_choice_labels(choices: list[str]) -> tuple[bool, list[str] | None]:
    """Strip leading A–D / 0–3 labels iff all four choices form a complete sequence.

    Returns ``(normalized, stripped)``:

    * ``normalized`` is True iff all four choices carry a leading label and those
      labels are exactly ``A,B,C,D`` or ``0,1,2,3`` in order (case-insensitive for
      letters). Only then is it safe for the renderer to re-emit labels itself.
    * ``stripped`` is the label-free bodies when ``normalized`` is True, else None.
      A body that becomes empty after stripping means the choice is a placeholder
      with no real content; callers must keep treating that as a structural error
      rather than silently turning it into an empty option.
    """
    if len(choices) != 4:
        return False, None
    extracted: list[str] = []
    bodies: list[str] = []
    for choice in choices:
        match = _CHOICE_LABEL_PREFIX.match(choice)
        if match is None:
            return False, None
        extracted.append(match.group(0).strip())
        bodies.append(choice[match.end():])
    labels = []
    for token in extracted:
        # Pull the single A–D / 0–3 char out of the matched prefix.
        glyph = next(ch for ch in token if ch.isalnum())
        labels.append(glyph.upper())
    if tuple(labels) in (_COMPLETE_LETTER_SEQUENCE, _COMPLETE_DIGIT_SEQUENCE):
        return True, bodies
    return False, None


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def walk(value: Any) -> Iterable[tuple[str | None, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from walk(child)


def question_blocks(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for section in assignment.get("sections") or []
        if isinstance(section, dict) and section.get("type") == "practice"
        for block in section.get("blocks") or []
        if isinstance(block, dict)
        and block.get("type") in {"choice", "fillin", "problem", "short_answer"}
    ]


def image_references(value: Any) -> list[tuple[str, dict[str, Any]]]:
    references: list[tuple[str, dict[str, Any]]] = []
    for _, child in walk(value):
        if isinstance(child, dict) and isinstance(child.get("image_path"), str):
            references.append((child["image_path"], child))
    return references


def crop_outputs(source: dict[str, Any], role: str) -> list[str]:
    crops = (source.get("crops") or {}).get(role) or []
    return [str(crop.get("output")) for crop in crops if isinstance(crop, dict)]


def relative_image_refs(value: Any) -> list[str]:
    return [path for path, _ in image_references(value)]


def count_path(references: list[str], path: str) -> int:
    return sum(reference == path for reference in references)


def choice_values(choices: Any) -> list[str]:
    if isinstance(choices, dict):
        return [str(value) for value in choices.values()]
    if isinstance(choices, list):
        return [str(value) for value in choices]
    return []


def mentions_figure(text: Any) -> bool:
    """文本是否明确指代一张配图（如图/图所示/下图…）。

    只命中强信号短语，避免「中心对称图形」「函数图象」这类纯文字描述触发。
    """
    return bool(FIGURE_REFERENCE.search(str(text or "")))


def box_area(box: Any) -> int:
    if not isinstance(box, list) or len(box) != 4:
        return 0
    try:
        left, top, right, bottom = (int(value) for value in box)
    except (TypeError, ValueError):
        return 0
    return max(0, right - left) * max(0, bottom - top)


def box_intersection_area(first: Any, second: Any) -> int:
    if (
        not isinstance(first, list)
        or len(first) != 4
        or not isinstance(second, list)
        or len(second) != 4
    ):
        return 0
    try:
        a_left, a_top, a_right, a_bottom = (int(value) for value in first)
        b_left, b_top, b_right, b_bottom = (int(value) for value in second)
    except (TypeError, ValueError):
        return 0
    width = max(0, min(a_right, b_right) - max(a_left, b_left))
    height = max(0, min(a_bottom, b_bottom) - max(a_top, b_top))
    return width * height


def parse_missing_questions(payload: Any, *, label: str) -> dict[int, dict]:
    """Parse and validate a missing-questions.yaml payload.

    Returns ``{question_number: claim}``. Every field is mandatory — a
    declaration exists to make a source-material gap explicit and reviewable,
    so a vague or partial claim must fail rather than silently pass.
    """
    if not isinstance(payload, dict):
        raise ValueError(f"{label}: YAML root must be a mapping")
    if payload.get("schema") != MISSING_QUESTIONS_SCHEMA:
        raise ValueError(f"{label}: schema must be {MISSING_QUESTIONS_SCHEMA}")
    if not isinstance(payload.get("paper_id"), str) or not payload["paper_id"].strip():
        raise ValueError(f"{label}: paper_id must be a non-empty string")
    missing_raw = payload.get("missing")
    if not isinstance(missing_raw, list) or not missing_raw:
        raise ValueError(f"{label}: missing must be a non-empty list")
    claims: dict[int, dict] = {}
    for index, claim in enumerate(missing_raw):
        where = f"{label}.missing[{index}]"
        if not isinstance(claim, dict):
            raise ValueError(f"{where} must be a mapping")
        number = claim.get("question_number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            raise ValueError(f"{where}.question_number must be a positive integer")
        if number in claims:
            raise ValueError(f"{where}: duplicate declaration for question {number}")
        reason = claim.get("reason")
        if reason not in MISSING_QUESTION_REASONS:
            raise ValueError(
                f"{where}.reason must be one of {', '.join(MISSING_QUESTION_REASONS)}"
            )
        if not isinstance(claim.get("note"), str) or not claim["note"].strip():
            raise ValueError(f"{where}.note must be a non-empty string")
        if not isinstance(claim.get("verified_at"), str) or not claim["verified_at"].strip():
            raise ValueError(f"{where}.verified_at must be a non-empty string")
        claims[number] = claim
    return claims


def collect_question_numbers(
    staging_dir: Path, ordered: list[str]
) -> tuple[list[int], list[str]]:
    """Read each item's authoritative question_number from source.yaml."""
    numbers: list[int] = []
    errors: list[str] = []
    for item_id in ordered:
        source_path = staging_dir / "items" / item_id / "source.yaml"
        try:
            source = load_yaml(source_path)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"{item_id}: cannot read source.yaml ({exc})")
            continue
        number = source.get("question_number")
        if not isinstance(number, int) or isinstance(number, bool) or number < 1:
            errors.append(f"{item_id}: question_number must be a positive integer")
            continue
        numbers.append(number)
    return numbers, errors


def _declared_missing_questions(
    staging_dir: Path, ordered: list[str], paper_id: str
) -> tuple[dict[int, dict], list[str]]:
    """Load missing-questions.yaml declarations for this paper.

    The declaration file lives beside the original source files (same convention
    as non-question-pages.yaml); candidate directories are the distinct
    ``source_directory`` values recorded in item source.yaml.
    """
    directories: list[str] = []
    for item_id in ordered:
        source_path = staging_dir / "items" / item_id / "source.yaml"
        try:
            source = load_yaml(source_path)
        except (OSError, ValueError, yaml.YAMLError):
            continue
        directory = str(source.get("source_directory") or "")
        if directory and directory not in directories:
            directories.append(directory)
    claims: dict[int, dict] = {}
    errors: list[str] = []
    for directory in directories:
        path = Path(directory) / MISSING_QUESTIONS_FILENAME
        if not path.is_file():
            continue
        try:
            payload = load_yaml(path)
            paper_claims = parse_missing_questions(payload, label=str(path))
        except (OSError, ValueError, yaml.YAMLError) as exc:
            errors.append(f"question numbering: invalid {MISSING_QUESTIONS_FILENAME}: {exc}")
            continue
        if payload.get("paper_id") != paper_id:
            errors.append(
                f"question numbering: {path} declares paper_id "
                f"{payload.get('paper_id')!r} but staging is {paper_id!r}"
            )
            continue
        for number, claim in paper_claims.items():
            if number in claims:
                errors.append(
                    f"question numbering: duplicate declaration for question "
                    f"{number} across {MISSING_QUESTIONS_FILENAME} files"
                )
            claims[number] = claim
    return claims, errors


def validate_question_numbering(
    staging_dir: Path, ordered: list[str], *, paper_id: str
) -> list[str]:
    """题号连续性不变式：题号必须从 1 连续递增到末题，不得重复。

    断档必须由源缺题声明（missing-questions.yaml）显式豁免——声明了但题目
    实际存在同样是错误（过期声明）。fail-closed：未声明的断档/重复直接失败。
    """
    if not ordered:
        return ["question numbering: staging has no items"]
    numbers, errors = collect_question_numbers(staging_dir, ordered)
    if errors:
        return errors
    claims, claim_errors = _declared_missing_questions(staging_dir, ordered, paper_id)
    errors.extend(claim_errors)
    max_number = max(numbers)
    gaps = sorted(set(range(1, max_number + 1)) - set(numbers))
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    for number in duplicates:
        errors.append(
            f"question numbering: duplicate question_number {number} across items"
        )
    for number in gaps:
        claim = claims.get(number)
        if claim is None:
            errors.append(
                f"question numbering: question {number} is missing between 1 and "
                f"{max_number}; if the original source material genuinely lacks it, "
                f"declare it in {MISSING_QUESTIONS_FILENAME} beside the source files"
            )
        else:
            print(
                f"NOTE: question {number} declared missing "
                f"({claim.get('reason')}): {str(claim.get('note'))[:120]}"
            )
    stale_claims = sorted(set(claims) - set(gaps))
    for number in stale_claims:
        errors.append(
            f"question numbering: {MISSING_QUESTIONS_FILENAME} declares question "
            f"{number} missing but it is present in staging; remove the stale claim"
        )
    if numbers and min(numbers) != 1:
        errors.append(
            f"question numbering: numbering must start at 1, got {min(numbers)}"
        )
    return errors


def audit_item(
    item_id: str,
    item_dir: Path,
    repo_root: Path,
    require_approved_review: bool,
    validate_source,
) -> tuple[list[str], list[str], dict[str, list[Path]]]:
    errors: list[str] = []
    warnings: list[str] = []
    assets: dict[str, list[Path]] = {role: [] for role in ROLES}
    source_path = item_dir / "source.yaml"
    teacher_path = item_dir / "teacher.resolved.assignment.yaml"
    student_path = item_dir / "student.resolved.assignment.yaml"
    review_path = item_dir / "review.yaml"
    missing = [
        path.name
        for path in (source_path, teacher_path, student_path)
        if not path.is_file()
    ]
    if missing:
        return [f"{item_id}: missing {', '.join(missing)}"], warnings, assets

    source, source_errors = validate_source(
        source_path,
        review_path=review_path if review_path.is_file() else None,
        repo_root=repo_root,
    )
    errors.extend(f"{item_id}: {message}" for message in source_errors)
    try:
        raw_source = load_yaml(source_path)
        teacher = load_yaml(teacher_path)
        student = load_yaml(student_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return errors + [f"{item_id}: {exc}"], warnings, assets

    placeholder = find_transcription_placeholder(teacher)
    if placeholder is not None:
        warnings.append(
            f"{item_id}: transcription placeholder present (「{placeholder}」) — "
            "该内容声称未出现在逐页文本中；在 Review UI 人工补全,或确认源材料缺失"
        )

    if raw_source.get("item_id") != item_id:
        errors.append(f"{item_id}: source item_id differs")
    hash_payload = {
        "teacher": teacher,
        "student": student,
        "crop_hashes": {
            role: [
                crop.get("output_sha256")
                for crop in (raw_source.get("crops") or {}).get(role, [])
                if isinstance(crop, dict)
            ]
            for role in ROLES
        },
        # Pending-attribution reviews are part of the content identity. Must
        # mirror materialize_staging's hash_payload so the audit recomputes the
        # same hash the materializer wrote.
        "attribution_reviews": {
            role: [
                crop.get("attribution_review") if isinstance(crop, dict) else None
                for crop in (raw_source.get("crops") or {}).get(role, [])
            ]
            for role in ROLES
        },
    }
    calculated_content_hash = canonical_hash(hash_payload)
    if raw_source.get("content_hash") != calculated_content_hash:
        errors.append(f"{item_id}: content_hash does not match assignments and crops")
    teacher_blocks = question_blocks(teacher)
    student_blocks = question_blocks(student)
    if len(teacher_blocks) != 1:
        errors.append(f"{item_id}: teacher must contain exactly one question block")
    if len(student_blocks) != 1:
        errors.append(f"{item_id}: student must contain exactly one question block")
    if len(teacher_blocks) != 1 or len(student_blocks) != 1:
        return errors, warnings, assets
    teacher_block = teacher_blocks[0]
    student_block = student_blocks[0]

    for label, block in (("teacher", teacher_block), ("student", student_block)):
        if block.get("id") != item_id:
            errors.append(f"{item_id}: {label} block id differs")
        if block.get("type") != raw_source.get("question_type"):
            errors.append(f"{item_id}: {label} question type differs from source")
    teacher_stem = str(teacher_block.get("stem_latex") or teacher_block.get("stem") or "").strip()
    student_stem = str(student_block.get("stem_latex") or student_block.get("stem") or "").strip()
    if teacher_stem != student_stem:
        errors.append(f"{item_id}: student and teacher stems differ")
    if not teacher_block.get("answer"):
        errors.append(f"{item_id}: teacher answer is required")
    if raw_source.get("question_type") == "choice":
        teacher_choices = choice_values(teacher_block.get("choices"))
        student_choices = choice_values(student_block.get("choices"))
        if len(teacher_choices) != 4:
            errors.append(
                f"{item_id}: choice question must contain exactly four option bodies"
            )
        if teacher_choices != student_choices:
            errors.append(f"{item_id}: student and teacher choices differ")
        for choice_index, choice in enumerate(teacher_choices):
            if not choice.strip():
                errors.append(f"{item_id}: choice {choice_index + 1} is empty")
        # When all four choices carry a complete ordered A–D / 0–3 prefix, the
        # renderer can re-emit labels itself, so we downgrade the embedded-label
        # report to a *warning* — unless stripping leaves an empty body, which is a
        # structural placeholder and stays an error (we never auto-clear it).
        normalized, stripped = normalize_choice_labels(teacher_choices)
        if normalized and stripped is not None:
            if any(not body.strip() for body in stripped):
                for choice_index, body in enumerate(stripped):
                    if not body.strip():
                        errors.append(
                            f"{item_id}: choice {choice_index + 1} is only a label "
                            "with no body; cannot auto-normalize into an empty option"
                        )
            else:
                warnings.append(
                    f"{item_id}: all four choices carry a complete A–D / 0–3 label "
                    "sequence; strip the labels and let the renderer re-emit them"
                )
        else:
            for choice_index, choice in enumerate(teacher_choices):
                if EMBEDDED_CHOICE_LABEL.match(choice):
                    errors.append(
                        f"{item_id}: choice {choice_index + 1} contains an embedded label; "
                        "store only the option body and let the renderer add A/B/C/D"
                    )
        answer = str(teacher_block.get("answer") or "").strip().upper()
        if answer not in {"A", "B", "C", "D"}:
            errors.append(f"{item_id}: choice answer must be one of A/B/C/D")
    if raw_source.get("question_type") in {"problem", "short_answer"} and not teacher_block.get(
        "solution_steps"
    ):
        errors.append(f"{item_id}: teacher solution_steps are required")

    for key, child in walk(student.get("sections") or []):
        if key in FORBIDDEN_STUDENT_KEYS:
            errors.append(f"{item_id}: student contains forbidden key {key}")
        if key == "diagram_slot":
            errors.append(f"{item_id}: student contains diagram_slot")
        if isinstance(child, dict) and (
            child.get("variant") in {"solution", "source_solution", "annotated"}
            or child.get("disclosure_policy") == "teacher_only"
        ):
            errors.append(f"{item_id}: student contains teacher-only image")
    if any(key == "diagram_slot" for key, _ in walk(teacher)):
        errors.append(f"{item_id}: teacher contains diagram_slot")

    teacher_refs = relative_image_refs(teacher_block)
    student_refs = relative_image_refs(student_block)
    solution_step_refs = relative_image_refs(teacher_block.get("solution_steps") or [])
    official_refs = [
        str(image.get("image_path"))
        for image in teacher_block.get("source_solution_images") or []
        if isinstance(image, dict)
    ]

    for role in ROLES:
        for output in crop_outputs(raw_source, role):
            path = (item_dir / output).resolve()
            assets[role].append(path)
            if not path.is_file():
                errors.append(f"{item_id}: missing {role} output {output}")

    for output in crop_outputs(raw_source, "question_evidence"):
        if count_path(student_refs, output):
            errors.append(f"{item_id}: question evidence leaks into student assignment: {output}")
    for output in crop_outputs(raw_source, "prompt"):
        if count_path(teacher_refs, output) != 1:
            errors.append(f"{item_id}: prompt must appear once in teacher assignment: {output}")
        if count_path(student_refs, output) != 1:
            errors.append(f"{item_id}: prompt must appear once in student assignment: {output}")
    evidence_crops = [
        crop
        for crop in (raw_source.get("crops") or {}).get("question_evidence", [])
        if isinstance(crop, dict)
    ]
    prompt_crops = [
        crop
        for crop in (raw_source.get("crops") or {}).get("prompt", [])
        if isinstance(crop, dict)
    ]
    # 题干明确指代一张配图（如图/图所示/下图…）时，必须配 prompt crop；缺图属于
    # 结构性缺陷，不应让无图版本进入题库。
    if mentions_figure(teacher_stem) and not prompt_crops:
        errors.append(
            f"{item_id}: stem references a figure (如图/图所示/下图…) "
            "but no prompt crop is attached"
        )
    for prompt_crop in prompt_crops:
        same_page_evidence = [
            crop
            for crop in evidence_crops
            if prompt_crop.get("source") == crop.get("source")
        ]
        full_question_candidates = [
            crop
            for crop in same_page_evidence
            if not any(
                marker in str(crop.get("output") or "").lower()
                for marker in ("diagram", "figure")
            )
        ]
        largest_evidence = max(
            full_question_candidates or same_page_evidence,
            key=lambda crop: box_area(crop.get("box_px")),
            default=None,
        )
        prompt_area = box_area(prompt_crop.get("box_px"))
        evidence_area = (
            box_area(largest_evidence.get("box_px")) if largest_evidence else 0
        )
        duplicates_full_evidence = bool(
            largest_evidence
            and prompt_crop.get("box_px") == largest_evidence.get("box_px")
            and (prompt_crop.get("whiteout_px") or [])
            == (largest_evidence.get("whiteout_px") or [])
        )
        near_full_evidence = bool(
            largest_evidence
            and prompt_area
            and evidence_area
            and prompt_area / evidence_area >= 0.8
            and box_intersection_area(
                prompt_crop.get("box_px"), largest_evidence.get("box_px")
            )
            / prompt_area
            >= 0.9
        )
        if duplicates_full_evidence or near_full_evidence:
            errors.append(
                f"{item_id}: prompt duplicates or nearly duplicates full question evidence; "
                "crop only the independent illustration or remove prompt"
            )
    for output in crop_outputs(raw_source, "solution"):
        if count_path(solution_step_refs, output) != 1:
            errors.append(f"{item_id}: solution image must appear once in solution_steps: {output}")
        if count_path(student_refs, output):
            errors.append(f"{item_id}: solution image leaks into student assignment: {output}")
        matching = [
            meta
            for path, meta in image_references(teacher_block.get("solution_steps") or [])
            if path == output
        ]
        if matching and (
            matching[0].get("variant") != "solution"
            or matching[0].get("disclosure_policy") != "teacher_only"
        ):
            errors.append(f"{item_id}: solution image metadata is not teacher-only: {output}")
    expected_official = crop_outputs(raw_source, "official_solution")
    if official_refs != expected_official:
        errors.append(f"{item_id}: source_solution_images order differs from official_solution crops")
    for output in expected_official:
        if count_path(student_refs, output):
            errors.append(f"{item_id}: official solution leaks into student assignment: {output}")

    transcription = raw_source.get("transcription") or {}
    prompt_status = transcription.get("prompt_status", "author_pass")
    prompt_notes = transcription.get("prompt_review_notes") or []
    if prompt_status == "needs_human_crop":
        warnings.append(
            f"{item_id}: prompt needs human crop review — {'; '.join(map(str, prompt_notes))}"
        )
    solution_status = transcription.get("solution_status", "author_pass")
    solution_notes = transcription.get("solution_review_notes") or []
    if solution_status == "needs_human_crop":
        warnings.append(
            f"{item_id}: solution needs human crop review — "
            f"{'; '.join(map(str, solution_notes))}"
        )
    if review_path.is_file():
        review = load_yaml(review_path)
        if review.get("content_hash") != raw_source.get("content_hash"):
            errors.append(f"{item_id}: review is stale")
        if require_approved_review and review.get("status") != "approved":
            errors.append(f"{item_id}: review status is not approved")
    elif require_approved_review:
        errors.append(f"{item_id}: review.yaml is required")
    return errors, warnings, assets


def fit_cell(paths: list[Path], width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height), "white")
    valid = [path for path in paths if path.is_file()]
    if not valid:
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 12), "(none)", fill="gray")
        return canvas
    slot_height = max(1, height // len(valid))
    for index, path in enumerate(valid):
        with Image.open(path) as image:
            thumb = ImageOps.contain(
                image.convert("RGB"), (width - 12, slot_height - 12)
            )
        x = (width - thumb.width) // 2
        y = index * slot_height + (slot_height - thumb.height) // 2
        canvas.paste(thumb, (x, y))
    return canvas


def contact_sheets(
    staging_dir: Path,
    ordered: list[str],
    assets_by_item: dict[str, dict[str, list[Path]]],
    rows_per_sheet: int,
) -> list[Path]:
    qa_dir = staging_dir / "qa"
    qa_dir.mkdir(exist_ok=True)
    cell_width, cell_height, label_width, header_height = 330, 230, 72, 32
    outputs: list[Path] = []
    for sheet_index, start in enumerate(range(0, len(ordered), rows_per_sheet), start=1):
        item_ids = ordered[start : start + rows_per_sheet]
        canvas = Image.new(
            "RGB",
            (
                label_width + cell_width * len(ROLES),
                header_height + cell_height * len(item_ids),
            ),
            "white",
        )
        draw = ImageDraw.Draw(canvas)
        for column, role in enumerate(ROLES):
            draw.text(
                (label_width + column * cell_width + 8, 9),
                role,
                fill="black",
            )
        for row, item_id in enumerate(item_ids):
            top = header_height + row * cell_height
            draw.text((8, top + 10), item_id, fill="black")
            for column, role in enumerate(ROLES):
                cell = fit_cell(
                    assets_by_item[item_id][role], cell_width, cell_height
                )
                canvas.paste(cell, (label_width + column * cell_width, top))
            draw.line(
                (0, top + cell_height - 1, canvas.width, top + cell_height - 1),
                fill="#cccccc",
            )
        output = qa_dir / f"contact-sheet-{sheet_index:03d}.png"
        canvas.save(output)
        outputs.append(output)
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("staging_dir", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--rows-per-sheet", type=int, default=8)
    parser.add_argument("--require-approved-review", action="store_true")
    args = parser.parse_args()

    staging_dir = args.staging_dir.resolve()
    repo_root = args.repo_root.resolve()
    sys.path.insert(0, str(repo_root))
    topic_scripts = (
        repo_root / ".codex/skills/math-topic-question-bank/scripts"
    ).resolve()
    docx_scripts = (
        repo_root / ".codex/skills/math-docx-question-bank-ingestion/scripts"
    ).resolve()
    sys.path.insert(0, str(topic_scripts))
    sys.path.insert(0, str(docx_scripts))
    try:
        review_issues_path = staging_dir / "review-issues.yaml"
        if args.require_approved_review and review_issues_path.is_file():
            raise ValueError(
                "review-issues.yaml marks a quarantined transcription review staging; "
                "apply resolutions and rebuild before approved audit"
            )
        if review_issues_path.is_file():
            from scripts.question_transcription.review_issue_contracts import (
                ReviewIssuesBundle,
                ReviewResolutionsBundle,
                unresolved_issues,
            )

            issue_bundle = ReviewIssuesBundle.model_validate(
                load_yaml(review_issues_path)
            )
            resolution_path = staging_dir / "review-resolutions.yaml"
            resolution_bundle = (
                ReviewResolutionsBundle.model_validate(load_yaml(resolution_path))
                if resolution_path.is_file()
                else None
            )
            pending = unresolved_issues(issue_bundle, resolution_bundle)
            print(
                "TRANSCRIPTION REVIEW QUARANTINE: "
                f"{len(issue_bundle.issues)} issue(s), {len(pending)} unresolved"
            )
        from exam_source_contracts import ExamPaperManifest, ExamPaperMap
        from paper_map_contracts import validate_against_staging
        from validate_exam_source import validate_source
        from word_evidence_pages import validate_staging_coverage

        paper = ExamPaperManifest.model_validate(load_yaml(staging_dir / "paper.yaml"))
        ordered = [
            item_id for section in paper.sections for item_id in section.item_ids
        ]
        paper_map_path = staging_dir / "paper-map.yaml"
        if not paper_map_path.is_file():
            raise ValueError("paper-map.yaml is required")
        paper_map = ExamPaperMap.model_validate(load_yaml(paper_map_path))
        map_errors = validate_against_staging(
            paper_map,
            paper_id=paper.paper.id,
            ordered_item_ids=ordered,
            staging_dir=staging_dir,
        )
        coverage_errors = validate_staging_coverage(
            staging_dir,
            ordered,
            repo_root=repo_root,
        )
        numbering_errors = validate_question_numbering(
            staging_dir, ordered, paper_id=paper.paper.id
        )
        if args.only:
            wanted = set(args.only)
            unknown = sorted(wanted.difference(ordered))
            if unknown:
                raise ValueError("--only item not in paper.yaml: " + ", ".join(unknown))
            ordered = [item_id for item_id in ordered if item_id in wanted]
        if args.rows_per_sheet < 1:
            raise ValueError("--rows-per-sheet must be positive")

        all_errors: list[str] = [*map_errors, *coverage_errors, *numbering_errors]
        all_warnings: list[str] = []
        assets_by_item: dict[str, dict[str, list[Path]]] = {}
        for item_id in ordered:
            errors, warnings, assets = audit_item(
                item_id,
                staging_dir / "items" / item_id,
                repo_root,
                args.require_approved_review,
                validate_source,
            )
            all_errors.extend(errors)
            all_warnings.extend(warnings)
            assets_by_item[item_id] = assets
        sheets = contact_sheets(
            staging_dir, ordered, assets_by_item, args.rows_per_sheet
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"STAGING AUDIT FAILED: {exc}", file=sys.stderr)
        return 1

    for warning in all_warnings:
        print(f"WARNING: {warning}")
    for sheet in sheets:
        print(f"CONTACT SHEET: {sheet}")
    if all_errors:
        print("STAGING INVALID", file=sys.stderr)
        for error in all_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    review_label = "approved" if args.require_approved_review else "structural"
    print(
        f"STAGING VALID: {paper.paper.id} | items={len(ordered)} "
        f"| gate={review_label}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
