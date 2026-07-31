"""Current ingestion-specific bundle normalization (architecture §8.2).

The model produces question/answer/solution content but NOT page-evidence geometry
(that's an OCR-pipeline concern). ``normalize_bundle`` injects per-question evidence
pointing at the first page and fills required non-empty strings (clue, anchors), so
the bundle validates. Downstream evidence completion refines these later.
"""

from __future__ import annotations

from typing import Any


def normalize_bundle(data: dict[str, Any], first_page: int = 1) -> dict[str, Any]:
    """In-place normalize a model JSON dict so it validates as QuestionTranscriptionBundle."""

    data.setdefault("schema", "math_question_transcription/v1")
    paper = data.setdefault("paper", {})
    paper.setdefault("id", "unknown")
    paper.setdefault("title", "未知")
    paper.setdefault("grade", "初三")
    paper.setdefault("subject", "数学")
    for section in data.get("sections", []):
        for q in section.get("questions", []):
            content = q.setdefault("content", {})
            if not content.get("clue"):
                content["clue"] = content.get("answer", "")
            evidence = q.setdefault("evidence", {})
            for key in ("question", "solution"):
                vals = evidence.get(key) or []
                norm = [v for v in vals if isinstance(v, dict)]
                if not norm:
                    norm = [{"kind": "page", "source": "transcription", "page_number": first_page}]
                evidence[key] = norm
            if not evidence.get("solution"):
                evidence["solution"] = [
                    {"kind": "page", "source": "transcription", "page_number": first_page}
                ]
            if not evidence.get("solution_start_anchor"):
                evidence["solution_start_anchor"] = content.get("answer", "")
            if not evidence.get("solution_end_anchor"):
                evidence["solution_end_anchor"] = content.get("answer", "")
    return data
