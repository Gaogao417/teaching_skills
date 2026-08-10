"""Page-text application stage helpers (architecture §3.4, M4).

Pure, framework-agnostic decisions for the page-text fan-out barrier. These do not
import LangGraph and can be unit-tested in isolation. The LangGraph node wrappers call
:func:`decide_page_barrier` and project the result into graph state.
"""

from __future__ import annotations

from typing import Any

from ...contracts import PageTextExtract


__all__ = ["PageBarrierDecision", "decide_page_barrier"]


class PageBarrierDecision:
    READY = "ready_for_whole_paper"
    WAIT = "wait_for_remaining_pages"
    STOP_FAILURES = "stop_for_page_failures"
    STOP_COVERAGE = "stop_for_coverage_violation"


def decide_page_barrier(
    expected_pages: list[int],
    completed: list[PageTextExtract],
    failures: list[str],
) -> tuple[str, Any]:
    """Pure barrier decision (ports §6.4). Returns ``(decision, detail)``.

    - any failure → ``STOP_FAILURES`` with the failure list;
    - duplicate page extracts → ``STOP_COVERAGE``;
    - missing pages → ``WAIT`` with the missing page list;
    - unexpected pages → ``STOP_COVERAGE``;
    - exact coverage → ``READY`` with the ordered completed page list.
    """

    if failures:
        return PageBarrierDecision.STOP_FAILURES, failures
    page_numbers = [e.artifact.page_number for e in completed]
    if len(page_numbers) != len(set(page_numbers)):
        return PageBarrierDecision.STOP_COVERAGE, "duplicate page extracts"
    missing = sorted(set(expected_pages) - set(page_numbers))
    if missing:
        return PageBarrierDecision.WAIT, missing
    extra = sorted(set(page_numbers) - set(expected_pages))
    if extra:
        return PageBarrierDecision.STOP_COVERAGE, f"unexpected pages: {extra}"
    return PageBarrierDecision.READY, [e.artifact.page_number for e in completed]
