"""Current OpenCode glm-5.2 whole-paper transcriber (architecture §3.2 and §3.6).

A self-contained HTTP client for the OpenCode server's session/message API. We
deliberately do NOT depend on the ``opencode-agent`` packages: their ``OpencodeModel``
+ PydanticAI ``Agent`` stack targets ``pydantic-ai>=0.0.14`` and breaks under the
installed ``pydantic_ai`` 2.x, and importing ``opencode_agent_server.engine`` pulls
in a ``Graph(...)`` that fails at import time. Only the session/message protocol
concept is borrowed (POST ``/session`` to create, POST
``/session/{id}/message`` to send; response ``parts[*].text`` joined).

Model binding: the OpenCode server selects the model from its server-side config
(``~/.config/opencode/opencode.json``); the per-request model is not propagated by
opencode's provider (design ports §7.2 GAP 3). So this adapter relies on the server
config binding glm-5.2 (verified by the live canary asserting a validated bundle).
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

import httpx
import yaml

from .._common_paths import repo_root  # noqa: F401  (sys.path bootstrap for contracts)
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


ADAPTER_ID = "opencode"


def _strip_fences(text: str) -> str:
    """Strip ```json ... ``` fences and surrounding prose to recover the JSON object."""

    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s[: -3]
        s = s.strip()
    if not s.startswith("{"):
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            s = s[start : end + 1]
    return s


def _extract_text(raw: dict) -> str:
    """Join all text parts from an OpenCode /session/.../message response."""

    parts = raw.get("parts") or []
    return " ".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


class OpencodeGlmTranscriber:
    """:class:`WholePaperTranscriber` backed by the OpenCode server (glm-5.2).

    Self-contained: only stdlib + httpx + the repo's own Pydantic contracts. No
    ``opencode-agent`` import. The server's session/message API is simple enough to
    call directly.
    """

    def __init__(self, *, model: str, server_url: str, agent_type: str, store,
                 timeout_s: float = 180.0, cache_dir=None, http_client=None) -> None:
        self.model = model
        self.server_url = server_url.rstrip("/")
        self.agent_type = agent_type
        self.store = store
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir or (store.layout.cache_dir)
        self.http_client = http_client  # injectable for tests

    # -- WholePaperTranscriber -------------------------------------------- #

    def transcribe(self, request):
        try:
            ordered = self._read_ordered_pages(request)
            mode = getattr(request, "prompt_mode", "interleaved") or "interleaved"
            solution_raw = getattr(request, "solution_page_texts", None) or []
            if mode == "separated" and solution_raw:
                solution = self._read_ordered_pages_from(solution_raw)
                user_prompt = build_user_prompt(
                    paper_id=request.paper_id,
                    source_archive=self._source_archive(request),
                    question_pages=ordered,
                    solution_pages=solution,
                    mode="separated",
                )
            else:
                user_prompt = build_user_prompt(
                    paper_id=request.paper_id,
                    source_archive=self._source_archive(request),
                    ordered_pages=ordered,
                    mode="interleaved",
                )
            first_page = ordered[0][0] if ordered else 1
            bundle = self._run(user_prompt, first_page)
        except _OpcError as exc:
            return None, exc.failure
        except Exception as exc:  # pragma: no cover - defensive
            return None, WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="transcriber_unavailable",
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
        return None, WholePaperFailure(
            adapter_id=ADAPTER_ID, kind="invalid_structured_output",
            attempts=1, execution_id=previous_execution_id,
            detail="repair delegated to re-transcribe",
        )

    # -- OpenCode server transport ---------------------------------------- #

    def _run(self, user_prompt: str, first_page: int):
        """Create a session, send the prompt, return a validated bundle."""

        cache_path = self.cache_dir / f"{self._cache_key(user_prompt)}.json" if self.cache_dir else None
        if cache_path and cache_path.exists():
            from scripts.question_transcription.contracts import QuestionTranscriptionBundle

            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return QuestionTranscriptionBundle.model_validate(cached["bundle"])

        message = f"{WHOLE_PAPER_SYSTEM_PROMPT}\n\n{user_prompt}"
        try:
            raw = self._send_message(message)
        except _OpcError:
            raise
        except Exception as exc:
            low = str(exc).lower()
            kind = "execution_timed_out" if "timeout" in low else "transcriber_unavailable"
            raise _OpcError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind=kind, attempts=1,
                detail=f"server call failed: {exc}",
            ))

        text = _extract_text(raw)
        if not text.strip():
            raise _OpcError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="invalid_structured_output",
                attempts=1, detail="server returned empty text",
            ))
        try:
            from ._normalize import normalize_bundle
            from scripts.question_transcription.contracts import QuestionTranscriptionBundle
            from scripts.question_transcription.mimo_client import extract_json

            data = extract_json(_strip_fences(text))
            normalize_bundle(data, first_page)
            bundle = QuestionTranscriptionBundle.model_validate(data)
        except _OpcError:
            raise
        except Exception as exc:
            raise _OpcError(WholePaperFailure(
                adapter_id=ADAPTER_ID, kind="invalid_structured_output",
                attempts=1, detail=f"bundle validation failed: {exc}; head={text[:200]!r}",
            ))

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"bundle": bundle.model_dump(by_alias=True, mode="json")},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            tmp.replace(cache_path)
        return bundle

    def _send_message(self, message: str) -> dict[str, Any]:
        """POST /session then /session/{id}/message; return the raw response JSON.

        Reuses one httpx client per call (created if not injected). The session id is
        created fresh per transcription; opencode's session is stateful server-side.
        """

        # trust_env=False mirrors OpencodeProvider: prevents httpx from routing
        # localhost through a proxy env var (which returns 502 against the server).
        client = self.http_client or httpx.Client(timeout=self.timeout_s, trust_env=False)
        close = self.http_client is None
        try:
            # 1. create session
            create = client.post(f"{self.server_url}/session", json={"title": "question-ingestion"})
            if create.is_error:
                raise RuntimeError(f"POST /session HTTP {create.status_code}: {create.text[:300]}")
            session_id = create.json().get("id")
            if not session_id:
                raise RuntimeError(f"POST /session returned no id: {create.text[:300]}")
            # 2. send message (messageID must start with "msg")
            payload: dict[str, Any] = {
                "messageID": f"msg_{int(time.time() * 1000)}",
                "parts": [{"type": "text", "text": message}],
            }
            if self.agent_type:
                payload["agent"] = self.agent_type
            msg = client.post(
                f"{self.server_url}/session/{session_id}/message", json=payload
            )
            if msg.is_error:
                raise RuntimeError(
                    f"POST /session/{session_id}/message HTTP {msg.status_code}: {msg.text[:300]}"
                )
            return msg.json()
        finally:
            if close:
                client.close()

    # -- helpers ----------------------------------------------------------- #

    def _read_ordered_pages(self, request):
        return self._read_ordered_pages_from(request.ordered_page_texts)

    def _read_ordered_pages_from(self, extracts) -> list[tuple[int, str]]:
        pages = []
        for extract in extracts:
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
            return str(data.get("source_archive") or "")
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
                    "agent_type": self.agent_type,
                    "prompt_version": WHOLE_PAPER_PROMPT_VERSION,
                    "user_prompt_sha256": hashlib.sha256(user_prompt.encode("utf-8")).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()


class _OpcError(Exception):
    """Internal control-flow exception carrying a structured WholePaperFailure."""

    def __init__(self, failure: WholePaperFailure) -> None:
        super().__init__(failure.detail)
        self.failure = failure
