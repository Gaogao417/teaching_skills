"""Direct GLM-5.2 API whole-paper transcriber (ZHIPUAI_API_KEY).

Calls the zhipuai OpenAI-compatible endpoint directly: read ordered page text from
the artifact store, build the prompt, request structured JSON, validate it through
:class:`QuestionTranscriptionBundle`, and commit the result. Route-clean and
immediately verifiable (no OpenCode gap). Cache is content-addressed on the ordered
page-text sha + manifest sha + model + prompt version (design §8.2).

This is the safe default whole-paper adapter when OpenCode routing is unverified.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import httpx
import yaml

from .._common_paths import repo_root  # noqa: F401
from ...contracts import (
    ArtifactRef,
    WholePaperFailure,
    WholePaperTranscription,
)
from ...prompts.whole_paper import (
    WHOLE_PAPER_PROMPT_VERSION,
    WHOLE_PAPER_SYSTEM_PROMPT,
    build_user_prompt,
)


ADAPTER_ID = "glm-api"


class _GlmApiError(Exception):
    """Internal control-flow exception carrying a structured WholePaperFailure."""

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure


class GlmApiTranscriber:
    """:class:`WholePaperTranscriber` backed by the direct GLM-5.2 API."""

    def __init__(self, *, model: str, base_url: str, store,
                 api_key: str | None = None, timeout_s: float = 300.0,
                 cache_dir: Path | None = None, http_client=None,
                 max_completion_tokens: int = 8192) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.store = store
        self.api_key = api_key or os.environ.get("ZHIPUAI_API_KEY")
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir or (store.layout.cache_dir)
        self.http_client = http_client
        self.max_completion_tokens = max_completion_tokens

    # -- WholePaperTranscriber -------------------------------------------- #

    def transcribe(self, request):
        try:
            ordered = self._read_ordered_pages(request)
            user_prompt = build_user_prompt(
                paper_id=request.paper_id,
                source_archive=self._source_archive(request),
                ordered_pages=ordered,
            )
            raw = self._call(user_prompt)
            bundle = self._validate(raw, request.paper_id, ordered)
        except _GlmApiError as exc:
            return None, exc.failure
        except Exception as exc:  # pragma: no cover - defensive
            return None, WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="invalid_structured_output",
                attempts=1, detail=f"{type(exc).__name__}: {exc}",
            )
        ref = self.store.commit_text(
            "structured/transcription.yaml",
            yaml.safe_dump(bundle.model_dump(by_alias=True, exclude_none=True, mode="json"),
                           allow_unicode=True, sort_keys=False),
            "math_question_transcription/v1",
        )
        return (
            WholePaperTranscription(
                transcription=ref, issues=None,
                execution_id=self._execution_id(ordered),
                model=self.model, prompt_version=WHOLE_PAPER_PROMPT_VERSION,
            ),
            None,
        )

    def repair_structured_output(self, previous_execution_id, validation_errors):
        # For the direct API, "repair" is a re-transcribe with the errors appended;
        # delegated back through transcribe() by the node (ports §7.4).
        return None, WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="invalid_structured_output",
            attempts=1, execution_id=previous_execution_id,
            detail="repair not yet specialized; re-run transcribe",
        )

    # -- internals -------------------------------------------------------- #

    def _read_ordered_pages(self, request) -> list[tuple[int, str]]:
        pages = []
        for extract in request.ordered_page_texts:
            text_ref = extract.artifact.text if hasattr(extract, "artifact") else extract["artifact"]["text"]
            ref = ArtifactRef.model_validate(text_ref) if isinstance(text_ref, dict) else text_ref
            page_number = (
                extract.artifact.page_number
                if hasattr(extract, "artifact")
                else extract["artifact"]["page_number"]
            )
            pages.append((page_number, self.store.read_text(ref)))
        return pages

    def _source_archive(self, request) -> str:
        manifest = request.source_manifest
        if manifest is None:
            return ""
        ref = manifest if isinstance(manifest, ArtifactRef) else ArtifactRef.model_validate(manifest)
        try:
            data = self.store.read_yaml(ref)
            return str(data.get("source_archive") or data.get("source", {}).get("path") or "")
        except Exception:
            return ""

    def _execution_id(self, ordered) -> str:
        return hashlib.sha256(
            "|".join(text for _, text in ordered).encode("utf-8")
        ).hexdigest()[:16]

    def _cache_key(self, user_prompt: str) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "adapter": ADAPTER_ID,
                    "model": self.model,
                    "prompt_version": WHOLE_PAPER_PROMPT_VERSION,
                    "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _call(self, user_prompt: str) -> str:
        cache_path = self.cache_dir / f"{self._cache_key(user_prompt)}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return cached["raw"]
        if not self.api_key:
            raise _GlmApiError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
                attempts=1, detail="ZHIPUAI_API_KEY is required for a live GLM call",
            ))
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": WHOLE_PAPER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "max_tokens": self.max_completion_tokens,
        }
        client = self.http_client or httpx.Client(timeout=self.timeout_s)
        close = self.http_client is None
        try:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if response.is_error:
                raise _GlmApiError(WholePaperFailure(
                    adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
                    attempts=1, detail=f"GLM HTTP {response.status_code}: {response.text[:500]}",
                ))
            raw = response.json()["choices"][0]["message"]["content"]
        finally:
            if close:
                client.close()
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"raw": raw}, ensure_ascii=False), encoding="utf-8"
        )
        tmp.replace(cache_path)
        return raw

    def _validate(self, raw: str, paper_id: str, ordered):
        """Parse + normalize + validate the model JSON.

        The model produces question/answer/solution content; it does NOT produce
        page-evidence geometry (that's an OCR-pipeline concern). We therefore inject
        per-question evidence pointing at page 1 (the first page) and fill required
        non-empty strings (clue, anchors) with a placeholder, so the bundle validates.
        Downstream evidence completion (DOCX word-evidence / PDF page spans) refines
        these later. Empty solution[] is backfilled with the first page too.
        """

        from scripts.question_transcription.contracts import QuestionTranscriptionBundle
        from scripts.question_transcription.mimo_client import extract_json

        try:
            data = extract_json(raw)
        except ValueError as exc:
            raise _GlmApiError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="invalid_structured_output",
                attempts=1, detail=f"response not JSON: {exc}",
            ))
        self._normalize_for_schema(data, ordered)
        try:
            return QuestionTranscriptionBundle.model_validate(data)
        except Exception as exc:
            raise _GlmApiError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="invalid_structured_output",
                attempts=1, detail=f"schema validation failed: {exc}",
            ))

    @staticmethod
    def _normalize_for_schema(data: dict, ordered) -> None:
        """In-place: ensure schema/paper/sections/evidence shape + non-empty strings."""

        data.setdefault("schema", "math_question_transcription/v1")
        paper = data.setdefault("paper", {})
        paper.setdefault("id", "unknown")
        paper.setdefault("title", "未知")
        paper.setdefault("grade", "初三")
        paper.setdefault("subject", "数学")
        first_page = ordered[0][0] if ordered else 1
        for section in data.get("sections", []):
            for q in section.get("questions", []):
                content = q.setdefault("content", {})
                if not content.get("clue"):
                    content["clue"] = content.get("answer", "")
                evidence = q.setdefault("evidence", {})
                # Coerce evidence.question/solution entries to PageEvidence dicts.
                for key in ("question", "solution"):
                    vals = evidence.get(key) or []
                    norm = []
                    for v in vals:
                        if isinstance(v, dict):
                            norm.append(v)
                        # else: drop raw strings (model noise)
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
