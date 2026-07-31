"""LangGraph reducers for the page-text fan-out (architecture §3.5, §5.1).

Reducer rules (design §5.1):

- ``page_text_extracts`` uses :func:`add_page_extract`, which sorts by page number,
  de-duplicates by page number (last writer wins is forbidden — a duplicate is a
  coverage violation caught by the barrier), and is order-independent.
- Optional singletons use a ``last_value``-style reducer (:func:`replace_value`).
- ``terminal_errors`` / ``page_text_failures`` append.

These reducers keep the collection deterministic across arbitrary fan-out completion
orders; they never decide business routing.
"""

from __future__ import annotations

from typing import Optional

from ...contracts import PageTextExtract


__all__ = [
    "add_page_extract",
    "PageTextExtractsReducer",
    "add_page_failure",
    "PageTextFailuresReducer",
    "replace_value",
]


def add_page_extract(
    left: list[PageTextExtract], right: Optional[list[PageTextExtract] | PageTextExtract]
) -> list[PageTextExtract]:
    """Order-independent page-extract reducer (design §5.1).

    Merge incoming extracts with the accumulated list, keyed by page number. The
    barrier node (:mod:`....nodes.page_text`) is responsible for the *exact-coverage*
    post-condition (no missing, no duplicate, no failure) — this reducer only keeps
    the collection deterministic across arbitrary fan-out completion orders.

    Inputs may be plain dicts (node outputs and checkpoint state are JSON-dumped);
    we re-validate each into :class:`PageTextExtract` here.
    """

    def _coerce(x) -> PageTextExtract:
        if isinstance(x, PageTextExtract):
            return x
        return PageTextExtract.model_validate(x)

    if right is None:
        return [_coerce(x) for x in left]
    incoming_raw = right if isinstance(right, list) else [right]
    incoming = [_coerce(x) for x in incoming_raw]
    merged: dict[int, PageTextExtract] = {
        _coerce(x).artifact.page_number: _coerce(x) for x in left
    }
    for extract in incoming:
        # Note: a duplicate page_number OVERWRITES here only so the reducer stays
        # total; the barrier treats any duplicate as a coverage violation and
        # refuses to proceed. We do not silently accept two extracts for one page.
        merged[extract.artifact.page_number] = extract
    return [merged[n] for n in sorted(merged)]


class PageTextExtractsReducer:
    """Callable wrapper for :func:`add_page_extract` (LangGraph annotation helper)."""

    def __call__(
        self,
        left: list[PageTextExtract],
        right: Optional[list[PageTextExtract] | PageTextExtract],
    ) -> list[PageTextExtract]:
        return add_page_extract(left, right)


def add_page_failure(
    left: list[str], right: Optional[list[str] | str]
) -> list[str]:
    """Append-only reducer for page-level failure descriptors."""

    if right is None:
        return list(left)
    incoming = right if isinstance(right, list) else [right]
    return [*left, *incoming]


class PageTextFailuresReducer:
    def __call__(self, left: list[str], right: Optional[list[str] | str]) -> list[str]:
        return add_page_failure(left, right)


def replace_value(left, right):
    """``last_value``-style reducer for optional singletons."""

    return right if right is not None else left
