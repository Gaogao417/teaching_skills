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
# Single-item single-role evidence pages are at most a handful (the largest real
# value observed across every staged paper is 11). A blow-up into dozens or
# hundreds of pages is always a mis-inferred layout or an outlier seed page, so
# cap the expansion: a role that would expand past this ceiling fails loudly
# instead of silently producing 300+ bogus source pages.
MAX_PAGES_PER_ROLE = 50
# Upper bound on a whole paper's rendered-page count (the largest real paper in
# the corpus is ~60 pages). The rendered-pages folder must hold only page PNGs;
# a count in the hundreds means the folder is actually the Word-source root that
# also holds a ``media/`` dump of formula fragments, which would inflate
# ``last_page`` and, with it, the runaway-expansion ceiling.
MAX_WHOLE_PAPER_PAGES = 200


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


def coerce_question_seeds(
    question_starts: list[int],
    solution_starts: list[int],
    *,
    layout: Layout,
) -> tuple[list[int], list[dict[str, int]]]:
    """Clamp non-monotonic question seeds to fit a manually confirmed ``layout``.

    Transcription drafts occasionally record the *answer* page of a trailing
    question as its ``question_word_evidence`` first page (e.g. Q22->p28 when the
    real question sits on page 6). Such a seed violates the ascending/in-layout
    invariants ``infer_layout`` enforces, so a bare ``--layout separated`` would
    silently expand it into a nonsensical multi-page range that still passes the
    structural audit (every page stays in range and covered).

    This helper repairs those seeds conservatively -- it only ever *clamps down*,
    never invents new pages -- and returns a per-item correction list for the
    completion report so a reviewer can see exactly what was changed:

    * ``separated``: a question seed at or past the first solution page is an
      outlier recorded in the answer block. Clamp it to ``first_solution_page -
      1`` and keep the result monotonic non-decreasing. If the source is actually
      interleaved (``first_solution_page == 1``) this layout is impossible and the
      run must be replayed with ``--layout interleaved`` instead.
    * ``interleaved``: a question seed past its own solution page (``q[i] >
      s[i]``) is the same kind of mis-recording. Clamp it to ``s[i]`` and keep it
      monotonic non-decreasing.
    """
    count = len(question_starts)
    if count != len(solution_starts) or count == 0:
        raise ValueError("question and solution page seeds must have equal non-zero length")

    if layout == "separated":
        first_solution = min(solution_starts)
        if first_solution <= 1:
            raise ValueError(
                "separated layout impossible: solution evidence starts at page "
                f"{first_solution}; this source is interleaved, "
                "replay with --layout interleaved"
            )
        question_ceiling = first_solution - 1
    else:  # interleaved
        question_ceiling = None

    coerced: list[int] = []
    corrections: list[dict[str, int]] = []
    previous = 1
    for index in range(count):
        original = question_starts[index]
        clamped = original
        if layout == "separated" and clamped >= first_solution:
            clamped = min(clamped, question_ceiling)
        elif layout == "interleaved" and clamped > solution_starts[index]:
            clamped = solution_starts[index]
        if layout == "separated":
            # Keep the question block monotonic non-decreasing. A clamped seed
            # below the running maximum would otherwise invert the block order.
            if clamped < previous:
                clamped = previous
        # Interleaved clamps each item independently to its own solution page;
        # a running maximum would propagate one outlier across every later item
        # (e.g. a single answer-block seed at p14 would force every subsequent
        # legitimate question seed up to p14, destroying valid evidence).
        coerced.append(clamped)
        if clamped != original:
            corrections.append(
                {"index": index, "original": original, "coerced": clamped}
            )
        previous = clamped
    return coerced, corrections


def _seeds_violate_layout(
    question_starts: list[int], solution_starts: list[int], *, layout: Layout
) -> bool:
    """Whether the recorded seeds break the confirmed ``layout``'s invariant.

    This mirrors the repair policy in :func:`coerce_question_seeds` so the guard
    fires for exactly the cases the repair handles:

    * ``separated``: every question page must precede the first solution page.
      A question seed at or past ``min(solution_starts)`` is an answer-block
      mis-recording (e.g. the trailing question whose only evidence page is its
      solution). Non-monotonic question seeds also violate this, because they
      cannot all stay below the solution block.
    * ``interleaved``: each question page must not run past its own solution
      page (``q[i] <= s[i]``). Monotonicity is not required here because the
      repair clamps each item independently to its own solution page.
    """
    if not question_starts:
        return False
    if layout == "separated":
        first_solution = min(solution_starts)
        return any(seed >= first_solution for seed in question_starts)
    # interleaved
    return any(
        question_starts[index] > solution_starts[index]
        for index in range(len(question_starts))
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
    ceiling = min(last_page, MAX_PAGES_PER_ROLE)
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
        # Guard against runaway expansion. interleaved fills
        # ``range(question_start, solution_start + 1)`` and the separated trailing
        # item fills up to ``solution_starts[0]`` / ``last_page``; a mis-inferred
        # layout or an outlier seed page turns either into hundreds of pages that
        # still pass the structural audit (every page stays in range and the whole
        # paper stays covered). Reject that here so a 306-page evidence list can
        # never reach ``source.yaml`` or the review UI.
        _reject_runaway_role(
            index,
            "question",
            question_pages,
            ceiling=ceiling,
            layout=layout,
        )
        _reject_runaway_role(
            index,
            "official_solution",
            solution_pages,
            ceiling=ceiling,
            layout=layout,
        )
        expected.append(
            {
                "question": question_pages,
                "official_solution": solution_pages,
            }
        )
    return expected


def _reject_runaway_role(
    index: int,
    role: str,
    pages: list[int],
    *,
    ceiling: int,
    layout: Layout,
) -> None:
    if len(pages) <= ceiling:
        return
    raise ValueError(
        f"item[{index}].{role}: word evidence expanded to {len(pages)} pages "
        f"(pages {pages[0]}..{pages[-1]}), which exceeds the per-role ceiling of "
        f"{ceiling}. This almost always means the Word layout is mis-inferred "
        f"(got {layout}) or a seed page is an outlier recorded in the answer "
        "block. Re-run with an explicit --layout separated/interleaved after "
        "manual confirmation, or fix the draft seed pages."
    )


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


def _page_index_from_name(stem: str) -> int | None:
    """Extract a 1-based page index from a rendered-page file stem.

    Two naming conventions exist in the corpus:

    - **DOCX rendered pages**: pure zero-padded digits (``001``, ``042``),
      produced by ``extract_docx_source.py``. ``isdigit()`` handles these.
    - **PDF extracted pages**: ``page-01``, ``page-1`` (``page-N.png``),
      produced by the older PDF extraction path. These are not digits, so the
      original ``int(path.stem)`` silently skipped every PDF-sourced page and
      ``_last_page_from_evidence`` reported "no rendered pages found" (the
      D-pages precheck failure on 2026-BAOSHAN / 2024-QINGPU).

    Returns ``None`` for a stem that is neither convention (e.g. a ``media/``
    formula fragment named ``image1``), so callers can skip non-page files
    without treating them as page 0.
    """
    if stem.isdigit():
        return int(stem)
    if stem.startswith("page-"):
        tail = stem.removeprefix("page-").lstrip("0") or "0"
        return int(tail) if tail.isdigit() else None
    return None


def _page_template(entries: list[dict[str, Any]], *, label: str) -> tuple[str, str, int, str]:
    """Return ``(parent, prefix, width, suffix)`` for emitting page-image paths.

    ``prefix`` is empty for the pure-digit DOCX convention and ``"page-"`` for
    the PDF-extracted convention, so :func:`_entries_for_pages` can emit names
    that match the on-disk rendered pages in either case.
    """
    if not entries or not isinstance(entries[0], dict):
        raise ValueError(f"{label}: first evidence page is required")
    raw = str(entries[0].get("page_image") or "")
    path = Path(raw)
    if not raw or not path.name:
        raise ValueError(f"{label}: page_image is required")
    stem = path.stem
    if stem.isdigit():
        prefix = ""
        width = len(stem)
    elif stem.startswith("page-"):
        prefix = "page-"
        width = 2
    else:
        prefix = ""
        width = 3
    return path.parent.as_posix(), prefix, width, path.suffix or ".png"


def _entries_for_pages(
    seed_entries: list[dict[str, Any]], pages: list[int], *, label: str
) -> list[dict[str, Any]]:
    parent, prefix, width, suffix = _page_template(seed_entries, label=label)
    return [
        {
            "page_image": f"{parent}/{prefix}{page:0{width}d}{suffix}",
            "page_number": page,
        }
        for page in pages
    ]


def _last_page_from_evidence(entries: list[dict[str, Any]], *, repo_root: Path) -> int:
    parent, _, _, suffix = _page_template(entries, label="page evidence")
    page_dir = Path(parent)
    if not page_dir.is_absolute():
        page_dir = repo_root / page_dir
    page_dir = page_dir.resolve()
    # ``_page_template`` derives the directory from the first evidence entry's
    # ``page_image`` path, so this MUST be the rendered-pages directory (e.g.
    # ``.../word/pages``), never the Word-source root (``.../word``) that also
    # holds a ``media/`` folder of formula fragments. Reject a directory that
    # looks like a media/asset dump before its numeric file count inflates
    # ``last_page`` and, with it, the runaway-expansion ceiling.
    if page_dir.name in ("media", "assets"):
        raise ValueError(
            f"page evidence directory resolved to {page_dir}, which is a media/"
            "asset folder, not the rendered-pages folder; check that page_image "
            "points at .../pages/<NNN>.png"
        )
    # Accept both pure-digit (001.png, DOCX) and page-N (page-01.png, PDF)
    # naming via _page_index_from_name, so PDF-sourced papers like
    # 2026-BAOSHAN / 2024-QINGPU are no longer silently skipped.
    pages = []
    for path in page_dir.glob(f"*{suffix}"):
        index = _page_index_from_name(path.stem)
        if index is not None:
            pages.append(index)
    if not pages:
        raise ValueError(f"no rendered pages found in {page_dir}")
    if len(pages) > MAX_WHOLE_PAPER_PAGES:
        raise ValueError(
            f"page evidence directory {page_dir} contains {len(pages)} numeric "
            f"page files, far more than any real paper ({MAX_WHOLE_PAPER_PAGES} "
            "cap); it likely includes non-page images -- check that page_image "
            "points at the rendered-pages folder, not the Word-source root"
        )
    return max(pages)


def resolve_draft_payload(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    layout: Layout | Literal["auto"] = "auto",
    layout_override_seeds: bool = False,
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
    if layout == "auto":
        resolved_layout: Layout = infer_layout(question_starts, solution_starts)
        seed_corrections: list[dict[str, int]] = []
    else:
        # The layout was manually confirmed, so skip the inference checks. But a
        # seed that violates the confirmed layout's invariant (a question page
        # recorded in the answer block, or a non-monotonic sequence) must still
        # be repaired before expansion, otherwise ``expected_page_ranges`` would
        # silently produce multi-page ranges that pass the structural audit while
        # pointing the review UI at wrong pages. Require an explicit opt-in so a
        # bare ``--layout`` cannot mask bad data.
        if _seeds_violate_layout(question_starts, solution_starts, layout=layout):
            if not layout_override_seeds:
                raise ValueError(
                    "page seeds violate the confirmed layout; confirm the repair "
                    "policy and pass --layout-override-seeds, or fix the draft "
                    "seeds manually"
                )
            question_starts, seed_corrections = coerce_question_seeds(
                question_starts,
                solution_starts,
                layout=layout,
            )
        else:
            seed_corrections = []
        resolved_layout = layout
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
        "seed_corrections": seed_corrections,
    }


def validate_staging_coverage(
    staging_dir: Path, ordered_item_ids: list[str], *, repo_root: Path
) -> list[str]:
    """Validate that staging word evidence is reasonable, not contiguous.

    ``word_evidence`` records where a question/solution lives in the source pages
    so the review UI can locate it for human checking. It is *not* a precise
    stem/solution slice, so we no longer force each item to cover a contiguous
    range. Three lightweight checks remain:

    1. each role is non-empty and lists unique ascending page numbers
       (enforced by ``evidence_page_numbers``);
    2. every evidence page number falls within ``[1, last_page]``;
    3. every page ``1..last_page`` is covered by at least one item's question or
       official_solution evidence (whole-paper coverage, no dropped pages).
    """
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

    first_question, _ = _evidence_lists(items[0], draft=False)
    try:
        last_page = _last_page_from_evidence(first_question, repo_root=repo_root)
    except ValueError as exc:
        return [f"Word evidence coverage: {exc}"]

    errors: list[str] = []
    covered: set[int] = set()
    for item_id, pages in zip(ordered_item_ids, pages_by_item, strict=True):
        for role in ROLES:
            out_of_range = sorted(
                page for page in pages[role] if page < 1 or page > last_page
            )
            if out_of_range:
                errors.append(
                    f"{item_id}: word_evidence.{role} pages {out_of_range} "
                    f"outside [1, {last_page}]"
                )
            covered.update(pages[role])

    uncovered = sorted(set(range(1, last_page + 1)) - covered)
    if uncovered:
        errors.append(
            f"Word evidence coverage: pages {uncovered} not covered by any item "
            f"(expected full coverage of pages 1..{last_page})"
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
    parser.add_argument(
        "--layout-override-seeds",
        action="store_true",
        help=(
            "with an explicit --layout, repair question seeds that violate the "
            "confirmed layout (e.g. an outlier recorded in the answer block) "
            "instead of failing; a bare --layout never masks bad data; "
            "ignored for --layout auto"
        ),
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
        layout_override_seeds=args.layout_override_seeds,
    )
    changes = report["changes"]
    seed_corrections = report.get("seed_corrections") or []
    print(
        f"WORD EVIDENCE: layout={report['layout']} "
        f"last_page={report['last_page']} changed_items={len(changes)} "
        f"seed_corrections={len(seed_corrections)}"
    )
    for correction in seed_corrections:
        print(
            f"- item[{correction['index']}] question seed "
            f"{correction['original']} -> {correction['coerced']}"
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
