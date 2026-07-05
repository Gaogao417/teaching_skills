#!/usr/bin/env python3
"""Validate a SkillTraceDraft JSON file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

try:
    from .contracts import validate_skill_trace_payload
except ImportError:  # pragma: no cover - supports direct script execution.
    from contracts import validate_skill_trace_payload


def validate_trace_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        return {"ok": False, "errors": [f"invalid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}"], "warnings": []}
    except OSError as exc:
        return {"ok": False, "errors": [f"cannot read {path}: {exc}"], "warnings": []}

    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["draft JSON must be an object"], "warnings": []}

    try:
        return validate_skill_trace_payload(payload)
    except ValidationError as exc:
        return {"ok": False, "errors": _format_validation_errors(exc), "warnings": []}


def _format_validation_errors(exc: ValidationError) -> list[str]:
    errors: list[str] = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item["loc"])
        message = item["msg"]
        errors.append(f"{location}: {message}" if location else message)
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path, help="Path to a SkillTraceDraft JSON file")
    args = parser.parse_args(argv)

    result = validate_trace_file(args.draft)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

