#!/usr/bin/env python3
"""Resolve and validate complete Word page evidence ranges.

DOCX teacher-edition sources usually use one of two layouts:

* interleaved: question -> answer/analysis -> next question;
* separated: all questions -> all answers.

The compact draft records the first page of each question and solution. This
module expands those seeds into complete, contiguous page evidence lists. It
does not inspect formulas or images and therefore needs no multimodal model.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml


Layout = Literal["interleaved", "separated"]
ROLES = ("question", "official_solution")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return value


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def draft_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        item
        for section in payload.get("sections") or []
        if isinstance(section, dict)
        for item in section.get("items") or []
        if isinstance(item, dict)
    ]
    if not items:
        raise ValueError("draft contains no items")
    return items


def source_items(staging_dir: Path, ordered_item_ids: list[str]) -> list[dict[str, Any]]:
    return [
        load_yaml(staging_dir / "items" / item_id / "source.yaml")
        for item_id in ordered_item_ids
    ]


def _evidence_lists(
    item: dict[str, Any], *, draft: bool
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if draft:
        question = item.get("question_word_evidence") or []
        official = item.get("official_solution") or {}
        solution = (
            official.get("word_evidence") or []
            if isinstance(official, dict)
            else []
        )
    else:
        groups = item.get("word_evidence") or {}
        if not isinstance(groups, dict):
            groups = {}
        question = groups.get("question") or []
        solution = groups.get("official_solution") or []
    if not isinstance(question, list) or not isinstance(solution, list):
        raise ValueError("Word evidence roles must be lists")
    return question, solution


def _page_number(entry: Any, *, label: str) -> int:
    if not isinstance(entry, dict):
        raise ValueError(f"{label}: evidence entry must be a mapping")
    page = entry.get("page_number")
    if not isinstance(page, int) or page < 1:
        raise ValueError(f"{label}: page_number must be a positive integer")
    return page


def evidence_page_numbers(
    item: dict[str, Any], *, draft: bool, label: str
) -> dict[str, list[int]]:
    question, solution = _evidence_lists(item, draft=draft)
    result = {
        "question": [
            _page_number(entry, label=f"{label}.question[{index}]")
            for index, entry in enumerate(question)
        ],
        "official_solution": [
            _page_number(entry, label=f"{label}.official_solution[{index}]")
            for index, entry in enumerate(solution)
        ],
    }
    for role in ROLES:
        pages = result[role]
        if not pages:
            raise ValueError(f"{label}: word_evidence.{role} must not be empty")
        if pages != sorted(set(pages)):
            raise ValueError(
                f"{label}: word_evidence.{role} pages must be unique and ascending"
            )
    return result


def infer_layout(question_starts: list[int], solution_starts: list[int]) -> Layout:
    if len(question_starts) != len(solution_starts) or not question_starts:
        raise ValueError("question and solution page seeds must have equal non-zero length")
    if question_starts != sorted(question_starts):
        raise ValueError("question page seeds must be ascending")
    if solution_starts != sorted(solution_starts):
        raise ValueError("solution page seeds must be ascending")

    interleaved = all(
        question_starts[index] <= solution_starts[index]
        and (
            index == len(question_starts) - 1
            or solution_starts[index] <= question_starts[index + 1]
        )
        for index in range(len(question_starts))
    )
    if interleaved:
        return "interleaved"
    if min(solution_starts) >= max(question_starts):
        return "separated"
    raise ValueError(
        "cannot infer Word source layout from page seeds; "
        "pass --layout interleaved or --layout separated after manual confirmation"
    )


def _until_before(start: int, next_start: int) -> list[int]:
    """Cover through the page before the next item, sharing a same-page boundary."""
    end = start if next_start <= start else next_start - 1
    return list(range(start, end + 1))


def expected_page_ranges(
    question_starts: list[int],
    solution_starts: list[int],
    *,
    last_page: int,
    layout: Layout,
) -> list[dict[str, list[int]]]:
    if last_page < max(question_starts + solution_starts):
        raise ValueError("last_page precedes an evidence seed")
    expected: list[dict[str, list[int]]] = []
    count = len(question_starts)
    for index in range(count):
        question_start = question_starts[index]
        solution_start = solution_starts[index]
        if layout == "interleaved":
            question_pages = list(range(question_start, solution_start + 1))
            solution_pages = (
                _until_before(solution_start, question_starts[index + 1])
                if index + 1 < count
                else list(range(solution_start, last_page + 1))
            )
        else:
            question_end_seed = (
                question_starts[index + 1]
                if index + 1 < count
                else solution_starts[0]
            )
            question_pages = _until_before(question_start, question_end_seed)
            solution_pages = (
                _until_before(solution_start, solution_starts[index + 1])
                if index + 1 < count
                else list(range(solution_start, last_page + 1))
            )
        expected.append(
            {
                "question": question_pages,
                "official_solution": solution_pages,
            }
        )
    return expected


def allowed_shared_boundaries(
    question_starts: list[int],
    solution_starts: list[int],
    *,
    layout: Layout,
) -> list[dict[str, set[int]]]:
    """Return boundary pages that adjacent items may legitimately share.

    The resolver computes the smallest complete ranges. A rendered page can,
    however, contain the tail of one item followed by the next item's start.
    Such a page is valid evidence for both items and must not be rejected as an
    unexpected extra page.
    """
    count = len(question_starts)
    allowed: list[dict[str, set[int]]] = []
    for index in range(count):
        if layout == "interleaved":
            question_boundary: set[int] = set()
            solution_boundary = (
                {question_starts[index + 1]} if index + 1 < count else set()
            )
        else:
            question_boundary = (
                {question_starts[index + 1]}
                if index + 1 < count
                else {solution_starts[0]}
            )
            solution_boundary = (
                {solution_starts[index + 1]} if index + 1 < count else set()
            )
        allowed.append(
            {
                "question": question_boundary,
                "official_solution": solution_boundary,
            }
        )
    return allowed


def _complete_or_preserved_pages(
    current: list[int], expected: list[int], allowed_boundary: set[int]
) -> list[int]:
    """Preserve an explicit shared boundary while repairing missing core pages."""
    missing = set(expected).difference(current)
    extras = set(current).difference(expected)
    if not missing and extras.issubset(allowed_boundary):
        return current
    return expected


def _page_template(entries: list[dict[str, Any]], *, label: str) -> tuple[str, int, str]:
    if not entries or not isinstance(entries[0], dict):
        raise ValueError(f"{label}: first evidence page is required")
    raw = str(entries[0].get("page_image") or "")
    path = Path(raw)
    if not raw or not path.name:
        raise ValueError(f"{label}: page_image is required")
    stem = path.stem
    width = len(stem) if stem.isdigit() else 3
    return path.parent.as_posix(), width, path.suffix or ".png"


def _entries_for_pages(
    seed_entries: list[dict[str, Any]], pages: list[int], *, label: str
) -> list[dict[str, Any]]:
    parent, width, suffix = _page_template(seed_entries, label=label)
    return [
        {
            "page_image": f"{parent}/{page:0{width}d}{suffix}",
            "page_number": page,
        }
        for page in pages
    ]


def _last_page_from_evidence(entries: list[dict[str, Any]], *, repo_root: Path) -> int:
    parent, _, suffix = _page_template(entries, label="page evidence")
    page_dir = Path(parent)
    if not page_dir.is_absolute():
        page_dir = repo_root / page_dir
    page_dir = page_dir.resolve()
    pages = [
        int(path.stem)
        for path in page_dir.glob(f"*{suffix}")
        if path.stem.isdigit()
    ]
    if not pages:
        raise ValueError(f"no rendered pages found in {page_dir}")
    return max(pages)


def resolve_draft_payload(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    layout: Layout | Literal["auto"] = "auto",
) -> tuple[dict[str, Any], dict[str, Any]]:
    updated = deepcopy(payload)
    items = draft_items(updated)
    pages_by_item = [
        evidence_page_numbers(
            item,
            draft=True,
            label=str(item.get("item_id") or f"item[{index}]"),
        )
        for index, item in enumerate(items)
    ]
    question_starts = [pages["question"][0] for pages in pages_by_item]
    solution_starts = [pages["official_solution"][0] for pages in pages_by_item]
    resolved_layout: Layout = (
        infer_layout(question_starts, solution_starts)
        if layout == "auto"
        else layout
    )
    first_question, _ = _evidence_lists(items[0], draft=True)
    last_page = _last_page_from_evidence(first_question, repo_root=repo_root)
    expected = expected_page_ranges(
        question_starts,
        solution_starts,
        last_page=last_page,
        layout=resolved_layout,
    )
    shared_boundaries = allowed_shared_boundaries(
        question_starts,
        solution_starts,
        layout=resolved_layout,
    )
    changes: list[dict[str, Any]] = []
    for item, current, minimum, boundaries in zip(
        items,
        pages_by_item,
        expected,
        shared_boundaries,
        strict=True,
    ):
        wanted = {
            role: _complete_or_preserved_pages(
                current[role],
                minimum[role],
                boundaries[role],
            )
            for role in ROLES
        }
        question, solution = _evidence_lists(item, draft=True)
        item["question_word_evidence"] = _entries_for_pages(
            question,
            wanted["question"],
            label=f"{item.get('item_id')}.question",
        )
        official = item.setdefault("official_solution", {})
        if not isinstance(official, dict):
            raise ValueError(f"{item.get('item_id')}: official_solution must be a mapping")
        official["word_evidence"] = _entries_for_pages(
            solution,
            wanted["official_solution"],
            label=f"{item.get('item_id')}.official_solution",
        )
        if current != wanted:
            changes.append(
                {
                    "item_id": item.get("item_id"),
                    "before": current,
                    "after": wanted,
                }
            )
    return updated, {
        "layout": resolved_layout,
        "last_page": last_page,
        "changes": changes,
    }


def validate_staging_coverage(
    staging_dir: Path, ordered_item_ids: list[str], *, repo_root: Path
) -> list[str]:
    items = source_items(staging_dir, ordered_item_ids)
    if not items:
        return []
    try:
        pages_by_item = [
            evidence_page_numbers(item, draft=False, label=item_id)
            for item_id, item in zip(ordered_item_ids, items, strict=True)
        ]
    except ValueError as exc:
        if all(not (item.get("word_evidence") or {}) for item in items):
            return []
        return [str(exc)]
    question_starts = [pages["question"][0] for pages in pages_by_item]
    solution_starts = [pages["official_solution"][0] for pages in pages_by_item]
    try:
        layout = infer_layout(question_starts, solution_starts)
        first_question, _ = _evidence_lists(items[0], draft=False)
        last_page = _last_page_from_evidence(first_question, repo_root=repo_root)
        expected = expected_page_ranges(
            question_starts,
            solution_starts,
            last_page=last_page,
            layout=layout,
        )
        shared_boundaries = allowed_shared_boundaries(
            question_starts,
            solution_starts,
            layout=layout,
        )
    except ValueError as exc:
        return [f"Word evidence coverage: {exc}"]

    errors: list[str] = []
    for item_id, actual, wanted, boundaries in zip(
        ordered_item_ids,
        pages_by_item,
        expected,
        shared_boundaries,
        strict=True,
    ):
        for role in ROLES:
            missing = sorted(set(wanted[role]).difference(actual[role]))
            extra = sorted(
                set(actual[role])
                .difference(wanted[role])
                .difference(boundaries[role])
            )
            if missing or extra:
                details = []
                if missing:
                    details.append(f"missing pages {missing}")
                if extra:
                    details.append(f"unexpected pages {extra}")
                errors.append(
                    f"{item_id}: word_evidence.{role} does not cover the complete "
                    f"{layout} range ({'; '.join(details)})"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--layout",
        choices=("auto", "interleaved", "separated"),
        default="auto",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report incomplete ranges without changing the draft",
    )
    args = parser.parse_args()

    draft_path = args.draft.resolve()
    repo_root = args.repo_root.resolve()
    staging_dir = draft_path.parent
    if not args.check and any((staging_dir / "items").glob("*/review.yaml")):
        raise SystemExit(
            "refusing to rewrite a draft with existing review.yaml decisions"
        )
    payload = load_yaml(draft_path)
    updated, report = resolve_draft_payload(
        payload,
        repo_root=repo_root,
        layout=args.layout,
    )
    changes = report["changes"]
    print(
        f"WORD EVIDENCE: layout={report['layout']} "
        f"last_page={report['last_page']} changed_items={len(changes)}"
    )
    for change in changes:
        print(
            f"- {change['item_id']}: "
            f"question {change['before']['question']} -> {change['after']['question']}; "
            f"solution {change['before']['official_solution']} -> "
            f"{change['after']['official_solution']}"
        )
    if args.check:
        return 1 if changes else 0
    write_yaml(draft_path, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
