"""Transport-level retry / cache / rate-limit decorators (ports-design §5/§6/§7.4).

These wrap a bound adapter so that nodes see a single ``extract``/``transcribe``
call and never branch on transport concerns (design §16.13/§16.14). The decorator
retries the SAME inner adapter only — there is no provider/host failover (the
registry has no "next provider"; design §6.3).

Retry semantics (ports §6.3):

- bounded exponential backoff between ``base_delay_ms`` and ``max_delay_ms``;
- retry only on retryable failure kinds (rate-limited / provider-unavailable /
  timed-out / invalid-response); empty-text is retryable, source-hash-mismatch and
  cache-corrupt are not;
- on exhaustion, return the last failure to the node.

Cache is handled inside the real adapters (they wrap the existing
``BailianOcrClient``/``MimoClient`` which already key on content sha + prompt
version), so this module only provides the retry decorator plus a thin rate-limit
permit guard.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from ..config import RetryPolicy
from ..contracts import PageTextFailure, PageTextJob, PageTextExtract, WholePaperFailure


__all__ = [
    "RETRYABLE_PAGE_KINDS",
    "RETRYABLE_WHOLE_KINDS",
    "with_page_retry",
    "with_whole_paper_retry",
    "RateLimiter",
]


RETRYABLE_PAGE_KINDS = {
    "rate_limited",
    "provider_unavailable",
    "request_timed_out",
    "invalid_response",
    "empty_text",
}
RETRYABLE_WHOLE_KINDS = {
    "transcriber_unavailable",
    "execution_timed_out",
    "routing_unverified",
    "invalid_structured_output",
    "page_coverage_invalid",
}


def _backoff(policy: RetryPolicy, attempt: int) -> float:
    delay = min(policy.base_delay_ms * (2 ** (attempt - 1)), policy.max_delay_ms) / 1000.0
    return delay


def with_page_retry(inner, policy: RetryPolicy):
    """Wrap a :class:`PageTextExtractor` with bounded retry (ports §6.3)."""

    def extract(job: PageTextJob):
        last_failure: PageTextFailure | None = None
        for attempt in range(1, policy.max_attempts + 1):
            result, failure = inner.extract(job)
            if failure is None and result is not None:
                return result, None
            last_failure = failure or PageTextFailure(
                adapter_id=None, kind="invalid_response", attempts=attempt,
                detail="no extract and no failure returned",
            )
            if last_failure.kind not in RETRYABLE_PAGE_KINDS:
                return None, last_failure.model_copy(update={"attempts": attempt})
            if attempt < policy.max_attempts:
                time.sleep(_backoff(policy, attempt))
        return None, last_failure.model_copy(update={"attempts": policy.max_attempts})

    extract.__wrapped__ = inner  # type: ignore[attr-defined]
    return extract


def with_whole_paper_retry(inner, policy: RetryPolicy):
    """Wrap a :class:`WholePaperTranscriber` with bounded transport retry (ports §7.4)."""

    def transcribe(request):
        last_failure: WholePaperFailure | None = None
        for attempt in range(1, policy.max_attempts + 1):
            result, failure = inner.transcribe(request)
            if failure is None and result is not None:
                return result, None
            last_failure = failure or WholePaperFailure(
                adapter_id=None, kind="invalid_structured_output", attempts=attempt,
                detail="no transcription and no failure returned",
            )
            if last_failure.kind not in RETRYABLE_WHOLE_KINDS:
                return None, last_failure.model_copy(update={"attempts": attempt})
            if attempt < policy.max_attempts:
                time.sleep(_backoff(policy, attempt))
        return None, last_failure.model_copy(update={"attempts": policy.max_attempts})

    def repair_structured_output(previous_execution_id, validation_errors):
        # Repair is business-level (node-visible); delegate straight to inner.
        return inner.repair_structured_output(previous_execution_id, validation_errors)

    wrapper = type("RetryingWholePaperTranscriber", (), {
        "transcribe": staticmethod(transcribe),
        "repair_structured_output": staticmethod(repair_structured_output),
        "__wrapped__": inner,
    })()
    return wrapper


class RateLimiter:
    """Simple shared RPM semaphore for a provider (ports §6.1).

    Blocking acquire; used by adapters that want a coarse client-side gate on top of
    provider-side 429s. Keep it minimal — the retry decorator already handles 429 via
    backoff.
    """

    def __init__(self, requests_per_minute: int) -> None:
        self.min_interval = 60.0 / max(requests_per_minute, 1)
        self._last = 0.0

    def acquire(self) -> None:
        now = time.monotonic()
        wait = self.min_interval - (now - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
