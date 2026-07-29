#!/usr/bin/env python3
"""Observe PDF page batches with one joint MiMo transcription+bbox request.

Two entry points coexist during the index-rollout:

* :func:`observe` (new) — driven by a ``math_question_span_index/v1``. The span
  index fixes each first-round batch's pages and expected question refs, so MiMo
  no longer自由发现题目. Missing / unexpected / duplicate refs trigger a定点补读
  of just the affected question while already-good questions stay frozen. MiMo
  remains the formal provider (joint text + bbox); BaiLian is only used upstream
  for the prescan. This is the path ``question-span-index-redesign.md`` §7.3
  prescribes.
* :func:`observe_windows` (legacy) — the old overlapping-window flow. Retained
  for one migration cycle and prints a deprecation notice; ``--overlap`` is no
  longer honoured (a non-zero value hard-errors).
"""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import PaperMeta, Provider
from scripts.question_transcription.mimo_client import MimoClient
from scripts.question_transcription.pdf_observation_contracts import (
    PdfPage,
    PdfPageObservation,
    PdfSourceManifest,
)
from scripts.question_transcription.question_span_index import (
    ObservationBatch,
    QuestionSpanIndex,
    build_observation_batches,
    load_index,
)

PROMPT_VERSION = "pdf-joint-observation-v3"
SPAN_INDEX_PROMPT_VERSION = "pdf-joint-observation-v4"
SYSTEM_PROMPT = r"""
你是数学试卷视觉转录器。对给定的连续页面一次完成文字/公式忠实转录和独立题图 bbox 识别。
只返回 JSON 对象 {"questions": [...]}。每题字段必须符合：
question_ref(数字字符串), question_number, section_ref, section_title,
question_type(choice|fillin|problem|short_answer), points,
content 或 null；content 含 stem_latex, choices, answer, clue, solution_steps, solution_notes；
question_evidence/solution_evidence 数组元素为 {page_number, box_norm:[left,top,right,bottom]}；
solution_start_anchor/solution_end_anchor；figures 数组元素为
{local_id,page_number,role:prompt|solution,order,box_norm,whiteout_norm,confidence,state,
note,needs_human_crop}；confidence 字典；continues_from_previous/continues_to_next；notes。
所有 *_norm 坐标必须是相对页面宽高的 0–1000 整数坐标，不要使用模型内部缩放图的像素。
question_evidence 是整题审计框，figure 是独立视觉对象，两者可重叠。
medium confidence 默认 state=needs_review；只有题号、角色、主体和标签都明确才 accepted。
看不到答案时允许 content=null 或 solution_evidence 为空，不得编造。公式用 LaTeX，保留原解答步骤数量与顺序。
不得返回 null：未知分值用 0，未知数组用 []，未知 clue 用“依据题目条件推导”，末题
solution_end_anchor 用 <END_OF_SOURCE>。figure confidence 必须是 high/medium/low 字符串。
每道已识别题必须显式返回 question_evidence 和 solution_evidence；如果当前页同时有题目与
“参考答案/解”文字，两类框都不能遗漏。figure bbox 必须完整包含全部线条、顶点字母、角度
或坐标标注，并在四边各留约页面宽高 1% 的安全边距，禁止裁掉标签。
""".strip()


def make_windows(
    pages: list[PdfPage], *, window_size: int = 3, overlap: int = 1
) -> list[list[PdfPage]]:
    """Legacy overlapping windows (deprecated; see :func:`observe`)."""
    if window_size < 1:
        raise ValueError("window_size must be positive")
    if not 0 <= overlap < window_size:
        raise ValueError("overlap must satisfy 0 <= overlap < window_size")
    step = window_size - overlap
    return [pages[start : start + window_size] for start in range(0, len(pages), step)]


def _page_path(manifest: PdfSourceManifest, page: PdfPage) -> Path:
    path = Path(page.source)
    if path.is_absolute():
        return path
    return Path(manifest.source_archive) / path


def _data_url(path: Path) -> str:
    media_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def observe_windows(
    manifest: PdfSourceManifest,
    *,
    paper: PaperMeta,
    client: MimoClient,
    window_size: int = 3,
    overlap: int = 1,
    document_role: str = "mixed",
) -> list[PdfPageObservation]:
    """Legacy overlapping-window observation flow (deprecated)."""
    provider = Provider(
        kind="vision_api", name="xiaomi-mimo", version=f"{client.model}/{PROMPT_VERSION}"
    )
    observations = []
    for window in make_windows(
        manifest.pages, window_size=window_size, overlap=overlap
    ):
        window_id = f"p{window[0].page_number:03d}-p{window[-1].page_number:03d}"
        metadata = [
            {
                "page_number": page.page_number,
                "width_px": page.width_px,
                "height_px": page.height_px,
                "sha256": page.sha256,
            }
            for page in window
        ]
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    f"文档角色：{document_role}。页面元数据："
                    + json.dumps(metadata, ensure_ascii=False)
                ),
            }
        ]
        for page in window:
            content.extend(
                [
                    {"type": "text", "text": f"PAGE_NUMBER={page.page_number}"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": _data_url(_page_path(manifest, page)),
                            "detail": "high",
                        },
                    },
                ]
            )
        result, _cache_hit = client.complete_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            cache_material={
                "page_sha256": [page.sha256 for page in window],
                "prompt_version": PROMPT_VERSION,
                "observation_schema": "math_pdf_page_observation/v1",
                "document_role": document_role,
            },
        )
        payload = {
            "schema": "math_pdf_page_observation/v1",
            "paper": paper.model_dump(by_alias=True, exclude_none=True),
            "provider": provider.model_dump(),
            "prompt_version": PROMPT_VERSION,
            "window_id": window_id,
            "pages": [page.model_dump() for page in window],
            "questions": _normalize_provider_questions(
                result.get("questions", []), window
            ),
        }
        observations.append(PdfPageObservation.model_validate(payload))
    return observations


def _normalize_provider_questions(
    questions: Any, pages: list[PdfPage]
) -> list[dict[str, Any]]:
    """Normalize provider quirks and convert normalized boxes to source pixels."""
    if not isinstance(questions, list):
        raise ValueError("provider questions must be a list")
    page_by_number = {page.page_number: page for page in pages}
    normalized = deepcopy(questions)
    for question in normalized:
        if not isinstance(question, dict):
            raise ValueError("each provider question must be an object")
        question["points"] = question.get("points") or 0
        question["notes"] = question.get("notes") or []
        question["confidence"] = question.get("confidence") or {}
        content = question.get("content")
        if isinstance(content, dict):
            content["choices"] = content.get("choices") or []
            content["clue"] = content.get("clue") or "依据题目条件推导。"
            content["solution_steps"] = content.get("solution_steps") or []
            content["solution_notes"] = content.get("solution_notes") or []
        question["question_evidence"] = question.get("question_evidence") or []
        question["solution_evidence"] = question.get("solution_evidence") or []
        question["figures"] = question.get("figures") or []
        if not question.get("solution_end_anchor"):
            question["solution_end_anchor"] = "<END_OF_SOURCE>"
        for evidence_name in ("question_evidence", "solution_evidence"):
            for evidence in question[evidence_name]:
                _convert_box(evidence, page_by_number, "box_norm", "box_px")
        for figure in question["figures"]:
            _convert_box(figure, page_by_number, "box_norm", "box_px")
            if "whiteout_norm" in figure:
                figure["whiteout_px"] = [
                    _norm_box_to_px(
                        box, page_by_number[int(figure["page_number"])]
                    )
                    for box in (figure.pop("whiteout_norm") or [])
                ]
            else:
                figure["whiteout_px"] = figure.get("whiteout_px") or []
            confidence = figure.get("confidence") or "low"
            if isinstance(confidence, dict):
                rank = {"low": 0, "medium": 1, "high": 2}
                values = [value for value in confidence.values() if value in rank]
                confidence = min(values, key=rank.get) if values else "low"
            figure["confidence"] = confidence
            if confidence == "medium" and figure.get("state") == "accepted":
                figure["state"] = "needs_review"
            figure["state"] = figure.get("state") or "needs_review"
            figure["needs_human_crop"] = bool(
                figure.get("needs_human_crop", False)
            )
    return normalized


def _convert_box(
    item: dict[str, Any],
    pages: dict[int, PdfPage],
    normalized_name: str,
    pixel_name: str,
) -> None:
    page_number = int(item["page_number"])
    if normalized_name in item:
        item[pixel_name] = _norm_box_to_px(
            item.pop(normalized_name), pages[page_number]
        )
    if pixel_name not in item:
        raise ValueError(f"provider region missing {normalized_name}")


def _norm_box_to_px(box: Any, page: PdfPage) -> list[int]:
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(type(value) is not int for value in box)
        or any(value < 0 or value > 1000 for value in box)
    ):
        raise ValueError("normalized bbox must be four integers in [0, 1000]")
    left, top, right, bottom = box
    return [
        round(left * page.width_px / 1000),
        round(top * page.height_px / 1000),
        round(right * page.width_px / 1000),
        round(bottom * page.height_px / 1000),
    ]


# --------------------------------------------------------------------------- #
# Span-index-driven observation (§7.1 / §7.3)
# --------------------------------------------------------------------------- #


def _validate_span_index(
    index: QuestionSpanIndex,
    *,
    page_sha_by_number: dict[int, str],
    page_number_offset: int,
) -> None:
    """Reject an index that does not match the current manifest (§7.1)."""
    if index.source_kind != "pdf":
        raise ValueError(
            f"span index source_kind {index.source_kind!r} != expected 'pdf'"
        )
    if index.status != "ready":
        raise ValueError(
            f"span index status must be 'ready' for observation, got {index.status!r}"
        )
    if index.fingerprint.page_number_offset != page_number_offset:
        raise ValueError(
            f"span index page_number_offset {index.fingerprint.page_number_offset} "
            f"!= manifest offset {page_number_offset}"
        )
    index_page_sha = {
        number: sha
        for number, sha in zip(index.page_numbers, index.fingerprint.page_sha256)
    }
    for number, sha in page_sha_by_number.items():
        if number not in index_page_sha:
            raise ValueError(f"page {number} is missing from the span index")
        if index_page_sha[number] != sha:
            raise ValueError(
                f"span index page {number} SHA does not match the rendered page"
            )


def _batch_user_prompt(
    batch: ObservationBatch,
    window: Sequence[PdfPage],
    *,
    manifest: PdfSourceManifest,
) -> list[dict[str, Any]]:
    """Build the per-batch user content (§7.1): page metadata, expected refs, role."""
    metadata = [
        {
            "page_number": page.page_number,
            "width_px": page.width_px,
            "height_px": page.height_px,
            "sha256": page.sha256,
        }
        for page in window
    ]
    expected = ", ".join(batch.expected_question_refs)
    role_label = "题干" if batch.role == "question" else "官方解答"
    role_rule = (
        "本批只要求转录题干与题图;不可见的解答字段写 null/[]。"
        if batch.role == "question"
        else "本批只要求转录官方解答;不可见的题干字段写 null/[]。"
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"文档角色：{role_label}。页面元数据："
                + json.dumps(metadata, ensure_ascii=False)
                + f"\n{role_rule}\n"
                f"本批必须且只能返回以下预期题号：{expected}。"
                "只返回预期题号;不得创建、合并、借用、拆分或省略任何题号。"
                "若某预期题号在本批页面确实不可见,仍必须为它返回一个 question_ref 正确的"
                "占位条目(content 可为 null),以便定点补读,绝不能遗漏题号或臆造内容。"
            ),
        }
    ]
    for page in window:
        content.extend(
            [
                {"type": "text", "text": f"PAGE_NUMBER={page.page_number}"},
                {
                    "type": "image_url",
                    "image_url": {"url": _data_url(_page_path(manifest, page)), "detail": "high"},
                },
            ]
        )
    return content


def _page_path_for(window: Sequence[PdfPage], page: PdfPage) -> Path:
    """Resolve a page's image path from its source (legacy helper, unused)."""
    path = Path(page.source)
    return path if path.is_absolute() else path


def _question_refs(questions: Any) -> list[str]:
    if not isinstance(questions, list):
        return []
    return [
        str(q.get("question_ref"))
        for q in questions
        if isinstance(q, dict) and q.get("question_ref") is not None
    ]


def _select_question(questions: list[dict[str, Any]], ref: str) -> dict[str, Any] | None:
    matches = [q for q in questions if str(q.get("question_ref")) == ref]
    return dict(matches[0]) if len(matches) == 1 else None


def _call_mimo(
    client: MimoClient,
    *,
    batch: ObservationBatch,
    window: list[PdfPage],
    manifest: PdfSourceManifest,
    cache_material: dict[str, Any],
) -> list[dict[str, Any]]:
    """One MiMo call for a batch; returns normalized question dicts (with bbox)."""
    result, _cache_hit = client.complete_json(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _batch_user_prompt(batch, window, manifest=manifest)},
        ],
        cache_material=cache_material,
    )
    return _normalize_provider_questions(result.get("questions", []), window)


def _observe_batch(
    batch: ObservationBatch,
    *,
    window: list[PdfPage],
    manifest: PdfSourceManifest,
    paper: PaperMeta,
    client: MimoClient,
    prompt_version: str,
    max_repairs: int = 1,
    repair_dir: Path | None = None,
    repair_log: list[dict[str, Any]] | None = None,
) -> PdfPageObservation:
    """Observe one PDF batch with freeze + targeted repair (§7.1).

    MiMo still owns the joint text + bbox transcription; the freeze/repair logic
    only governs which question refs a batch must return. A normal observation
    file is produced only after the batch fully resolves.
    """
    expected_refs = list(batch.expected_question_refs)
    cache_material = {
        "page_sha256": [page.sha256 for page in window],
        "prompt_version": prompt_version,
        "observation_schema": "math_pdf_page_observation/v1",
        "batch_id": batch.batch_id,
        "expected_refs": expected_refs,
        "role": batch.role,
    }

    questions = _call_mimo(client, batch=batch, window=window, manifest=manifest, cache_material=cache_material)
    frozen: dict[str, dict[str, Any]] = {}
    history: list[dict[str, Any]] = []

    def _classify(qs: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str], set[str]]:
        refs = _question_refs(qs)
        counts: dict[str, int] = {}
        for ref in refs:
            counts[ref] = counts.get(ref, 0) + 1
        returned = set(refs)
        missing = set(expected_refs) - returned
        unexpected = returned - set(expected_refs)
        duplicate = {ref for ref, count in counts.items() if count > 1}
        good = {ref for ref in expected_refs if counts.get(ref, 0) == 1}
        return missing, unexpected, duplicate, good

    def _record(stage: str, qs: list[dict[str, Any]], diffs: dict[str, set[str]]) -> None:
        history.append(
            {"stage": stage, "returned_refs": _question_refs(qs), **{k: sorted(v) for k, v in diffs.items()}}
        )

    missing, unexpected, duplicate, good = _classify(questions)
    _record("first_round", questions, {"missing": missing, "unexpected": unexpected, "duplicate": duplicate})
    for ref in sorted(good):
        question = _select_question(questions, ref)
        if question is not None:
            frozen[ref] = question

    repairs_done = 0
    while True:
        outstanding = [ref for ref in expected_refs if ref not in frozen]
        if not outstanding:
            break
        if repairs_done >= max_repairs:
            detail = (
                f"batch {batch.batch_id} could not be repaired within "
                f"{max_repairs} attempt(s); still missing/duplicated: {sorted(outstanding)}"
            )
            if repair_log is not None:
                repair_log.append({"batch_id": batch.batch_id, "status": "blocking", "detail": detail})
            raise ValueError(detail)
        repairs_done += 1
        repair_batch = ObservationBatch(
            batch_id=f"{batch.batch_id}-repair-{repairs_done}",
            role=batch.role,
            page_numbers=list(batch.page_numbers),
            expected_question_refs=outstanding,
        )
        repair_cache = dict(cache_material)
        repair_cache["batch_id"] = repair_batch.batch_id
        repair_cache["expected_refs"] = outstanding
        repair_questions = _call_mimo(
            client, batch=repair_batch, window=window, manifest=manifest, cache_material=repair_cache
        )
        r_missing, r_unexpected, r_duplicate, r_good = _classify(repair_questions)
        _record(
            f"repair_{repairs_done}",
            repair_questions,
            {"missing": r_missing, "unexpected": r_unexpected, "duplicate": r_duplicate},
        )
        for ref in sorted(r_good):
            question = _select_question(repair_questions, ref)
            if question is not None:
                frozen[ref] = question

    provider = Provider(
        kind="vision_api", name="xiaomi-mimo", version=f"{client.model}/{prompt_version}"
    )
    payload = {
        "schema": "math_pdf_page_observation/v1",
        "paper": paper.model_dump(by_alias=True, exclude_none=True),
        "provider": provider.model_dump(),
        "prompt_version": prompt_version,
        "window_id": batch.batch_id,
        "pages": [page.model_dump() for page in window],
        "questions": [dict(frozen[ref]) for ref in expected_refs],
    }
    if repair_log is not None and repairs_done:
        repair_log.append({"batch_id": batch.batch_id, "status": "repaired", "repairs": repairs_done})
    return PdfPageObservation.model_validate(payload)


def observe(
    manifest: PdfSourceManifest,
    *,
    paper: PaperMeta,
    span_index: QuestionSpanIndex,
    client: MimoClient,
    target_batch_pages: int = 6,
    max_batch_pages: int = 8,
    target_batch_questions: int = 12,
    max_repairs: int = 1,
    output_dir: Path | None = None,
) -> list[PdfPageObservation]:
    """Observe PDF pages driven by a span index (§7.3).

    Replaces the legacy overlapping-window flow. The span index fixes the batch
    plan; each first-round batch has a disjoint page set and an exact expected-ref
    set. MiMo remains the formal joint text+bbox provider. ``content=null`` is
    tolerated for question-only / solution-only page segments (§7.3).
    """
    page_sha_by_number = {page.page_number: page.sha256 for page in manifest.pages}
    pages_by_number = {page.page_number: page for page in manifest.pages}
    _validate_span_index(span_index, page_sha_by_number=page_sha_by_number, page_number_offset=0)

    batches = build_observation_batches(
        span_index,
        target_page_count=target_batch_pages,
        hard_page_limit=max_batch_pages,
        target_question_count=target_batch_questions,
    )
    if not batches:
        raise ValueError("span index produced no observation batches")

    repair_dir = output_dir / "_repair" if output_dir is not None else None
    observations: list[PdfPageObservation] = []
    repair_log: list[dict[str, Any]] = []
    for batch in batches:
        window = [pages_by_number[n] for n in batch.page_numbers]
        observation = _observe_batch(
            batch,
            window=window,
            manifest=manifest,
            paper=paper,
            client=client,
            prompt_version=SPAN_INDEX_PROMPT_VERSION,
            max_repairs=max_repairs,
            repair_dir=repair_dir,
            repair_log=repair_log,
        )
        observations.append(observation)
        if output_dir is not None:
            output_dir.mkdir(parents=True, exist_ok=True)
            output = output_dir / f"{observation.window_id}.observation.yaml"
            tmp = output.with_suffix(output.suffix + ".tmp")
            tmp.write_text(
                yaml.safe_dump(
                    observation.model_dump(by_alias=True, exclude_none=True),
                    allow_unicode=True,
                    sort_keys=False,
                    width=1000,
                ),
                encoding="utf-8",
            )
            tmp.replace(output)
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--paper-meta", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument(
        "--span-index",
        type=Path,
        default=None,
        help="math_question_span_index/v1 path. When given, the new span-index "
        "batch flow is used (recommended). Without it the legacy overlapping-"
        "window flow runs (deprecated).",
    )
    # New span-index flow knobs.
    parser.add_argument("--target-batch-pages", type=int, default=6)
    parser.add_argument("--max-batch-pages", type=int, default=8)
    parser.add_argument("--target-batch-questions", type=int, default=12)
    parser.add_argument("--max-repairs", type=int, default=1)
    # Legacy overlapping-window knobs (deprecation).
    parser.add_argument("--window-size", type=int, default=3)
    parser.add_argument("--overlap", type=int, default=1)
    parser.add_argument(
        "--document-role", choices=["question", "solution", "mixed"], default="mixed"
    )
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    manifest = PdfSourceManifest.model_validate(
        yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    )
    paper = PaperMeta.model_validate(
        yaml.safe_load(args.paper_meta.read_text(encoding="utf-8"))
    )
    client = MimoClient(timeout_s=args.timeout, cache_dir=args.cache_dir)

    if args.span_index is not None:
        try:
            index = load_index(args.span_index)
            observations = observe(
                manifest,
                paper=paper,
                span_index=index,
                client=client,
                target_batch_pages=args.target_batch_pages,
                max_batch_pages=args.max_batch_pages,
                target_batch_questions=args.target_batch_questions,
                max_repairs=args.max_repairs,
                output_dir=args.output_dir,
            )
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
        print(f"PDF BATCHES OBSERVED: batches={len(observations)} output={args.output_dir}")
        return 0

    # Legacy overlapping-window flow (deprecated).
    if args.overlap != 0:
        print(
            "ERROR: --overlap is no longer honoured; the span-index flow uses "
            "non-overlapping first-round batches. Pass --overlap 0 or migrate.",
            file=sys.stderr,
        )
        return 2
    observations = observe_windows(
        manifest,
        paper=paper,
        client=client,
        window_size=args.window_size,
        overlap=0,
        document_role=args.document_role,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for observation in observations:
        output = args.output_dir / f"{observation.window_id}.observation.yaml"
        output.write_text(
            yaml.safe_dump(
                observation.model_dump(by_alias=True, exclude_none=True),
                allow_unicode=True,
                sort_keys=False,
                width=1000,
            ),
            encoding="utf-8",
        )
    print(f"PDF OBSERVED: windows={len(observations)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
