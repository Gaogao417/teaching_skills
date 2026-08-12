"""Shared signature + label-text helpers for marker/text annotation checks.

Lives below both ``tools`` and ``audit`` so neither has to import the other for
these checks (audit already imports from tools; the reverse would cycle).

- ``normalized_segment`` / ``marker_signature`` / ``text_signature`` mirror the
  ordering-insensitive signatures used by the deterministic audit, so the
  compile-boundary strip and the audit agree on what counts as the same marker.
- ``label_text_violation`` returns a non-empty audit-issue string when a label's
  text looks like a serialized Wolfram aggregate (e.g. ``{C["GeometricPoint"][A], ...}``)
  rather than a plain point label, so the compile boundary can sanitize it before
  it reaches the audit.
"""

from __future__ import annotations


def normalized_segment(value: object) -> tuple[str, str]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return ("", "")
    return tuple(sorted((str(value[0]), str(value[1]))))  # type: ignore[return-value]


_MARKER_TYPE_ALIASES = {
    "equal_tick": "equal_ticks",
    "equal_segment": "equal_ticks",
    "equal_segments": "equal_ticks",
    "parallel_mark": "parallel",
    "parallel_marks": "parallel",
}

# Substrings that indicate a label text is a serialized Wolfram/aggregate
# object rather than a plain point label. Kept in sync with the audit.
_BAD_LABEL_SUBSTRINGS = ("ref", "GeometricPoint", "[[", "]]", 'C["', "Centroid")
_BAD_LABEL_MAX_LEN = 24


def marker_signature(value: object) -> tuple[object, ...]:
    if not isinstance(value, dict):
        return ("invalid",)
    marker_type = str(value.get("type") or "")
    marker_type = _MARKER_TYPE_ALIASES.get(marker_type, marker_type)
    if marker_type in {"equal_ticks", "parallel"}:
        segments = value.get("segments") if isinstance(value.get("segments"), list) else []
        return (marker_type, tuple(sorted(normalized_segment(item) for item in segments)))
    arms = value.get("arms") if isinstance(value.get("arms"), list) else []
    return (marker_type, str(value.get("vertex") or ""), tuple(sorted(str(item) for item in arms)))


def text_signature(value: object) -> tuple[object, ...]:
    if not isinstance(value, dict):
        return ("invalid",)
    target = value.get("target") if isinstance(value.get("target"), list) else []
    return (str(value.get("text") or ""), tuple(str(item) for item in target))


def label_text_violation(value: object) -> str:
    """Return a non-empty issue string when label text is serialized garbage."""
    if isinstance(value, dict):
        value = value.get("text", "")
    text = str(value)
    if any(item in text for item in _BAD_LABEL_SUBSTRINGS):
        return f"bad serialized label text: {text[:80]}"
    if len(text) > _BAD_LABEL_MAX_LEN:
        return f"label text too long: {text[:80]}"
    return ""
