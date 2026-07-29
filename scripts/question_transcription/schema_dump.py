#!/usr/bin/env python3
"""Emit JSON Schema for the frozen v1 contracts.

The contracts are hand-authoritative; this just mirrors them as JSON Schema so
non-Python providers (or a future Review UI) can validate independently. Run:

    ./.venv/bin/python scripts/question_transcription/schema_dump.py --out schemas/question_transcription/

Writing JSON Schema is new to this repo; it is intentionally a one-way dump
(contracts own the semantics). ``schema.yaml`` (human-readable) and
``<name>.schema.json`` are both produced.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

# Allow running this file as `python scripts/question_transcription/schema_dump.py`
# from the repo root (per the architecture doc CLI) as well as importing it.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.contracts import (  # noqa: E402
    AssemblyReport,
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)
from scripts.question_transcription.review_issue_contracts import (  # noqa: E402
    ReviewIssuesBundle,
    ReviewResolutionsBundle,
)
from scripts.question_transcription.source_contracts import SourcePaper  # noqa: E402

_CONTRACTS = {
    "question_transcription": QuestionTranscriptionBundle,
    "image_attribution": ImageAttributionBundle,
    "draft_assembly_report": AssemblyReport,
    "review_issues": ReviewIssuesBundle,
    "review_resolutions": ReviewResolutionsBundle,
    # v2: authoritative per-paper source contract for DOCX/PDF ingestion. It is
    # additive to v1 -- the Projector turns a SourcePaper back into the v1
    # paper.draft.yaml; v1 stays frozen and is never silently overwritten.
    "source_paper": SourcePaper,
}


def dump_all(out: Path) -> list[str]:
    """Write JSON+YAML schema for every frozen contract into ``out``.

    Returns the contract names written. Importable so tests don't have to shell
    out.
    """
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, model in _CONTRACTS.items():
        schema = model.model_json_schema()
        (out / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        (out / f"{name}.schema.yaml").write_text(
            yaml.safe_dump(schema, allow_unicode=True, sort_keys=False, width=1000),
            encoding="utf-8",
        )
        written.append(name)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("schemas/question_transcription"),
        help="output directory (created if missing)",
    )
    args = parser.parse_args()

    written = dump_all(args.out)
    print(f"JSON SCHEMA DUMPED: {args.out}")
    for name in written:
        print(f"  - {name}.schema.json / .yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
