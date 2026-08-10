"""OpenCode server HTTP transport (architecture §3.2, M1.2).

A self-contained client for the OpenCode server's session/message API. We
deliberately do NOT depend on the ``opencode-agent`` packages. The client owns the
``POST /session`` then ``POST /session/{id}/message`` two-step and turns transport
errors into provider-neutral :class:`~..contracts.ModelFailure`.

The client is domain-free: it has no knowledge of math questions, transcription
bundles, or ingestion artifacts. It only knows how to send a prompt to the OpenCode
server and return its raw response JSON.

Model binding: the OpenCode server selects the model from its server-side config
(``~/.config/opencode/opencode.json``); the per-request model is not propagated by the
old opencode-agent provider. This is a transport property, not something this module
decides — bootstrap resolves the server URL and agent type.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..contracts import ModelFailure, ModelFailureError, ModelFailureKind


__all__ = ["OpencodeClient", "extract_opencode_text"]


def extract_opencode_text(raw: dict) -> str:
    """Join all text parts from an OpenCode ``/session/.../message`` response."""

    parts = raw.get("parts") or []
    return " ".join(p.get("text", "") for p in parts if p.get("type") == "text").strip()


def _classify_http_error(exc: Exception, status: int | None) -> ModelFailureKind:
    low = str(exc).lower()
    if status is not None:
        if status == 401 or status == 403:
            return "authentication"
        if status == 429:
            return "rate_limited"
        if 500 <= status < 600:
            return "unavailable"
    if "timeout" in low or "timed out" in low:
        return "timed_out"
    return "unavailable"


class OpencodeClient:
    """Stateless caller for the OpenCode ``POST /session`` + ``POST /message`` API.

    The server's session is stateful server-side; a fresh session id is created per
    call. An :class:`httpx.Client` may be injected for tests; otherwise one is created
    per call with ``trust_env=False`` (mirrors the original adapter: prevents httpx
    from routing localhost through a proxy env var that returns 502 against the server).
    """

    PROVIDER = "opencode"

    def __init__(
        self,
        *,
        server_url: str,
        agent_type: str,
        timeout_s: float = 180.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.agent_type = agent_type
        self.timeout_s = timeout_s
        self.http_client = http_client

    def send_message(self, message: str) -> dict[str, Any]:
        """``POST /session`` then ``POST /session/{id}/message``; return raw JSON.

        Raises :class:`ModelFailureError` on transport/auth/rate-limit/timeout errors
        so the caller (the PydanticAI bridge) can surface a provider-neutral failure.
        """

        client = self.http_client or httpx.Client(timeout=self.timeout_s, trust_env=False)
        close = self.http_client is None
        try:
            try:
                create = client.post(f"{self.server_url}/session", json={"title": "question-ingestion"})
            except Exception as exc:  # httpx.RequestError / httpx.HTTPStatusError
                raise ModelFailureError(ModelFailure(
                    provider=self.PROVIDER, kind=_classify_http_error(exc, None),
                    detail=f"POST /session failed: {exc}",
                ))
            if create.is_error:
                raise ModelFailureError(ModelFailure(
                    provider=self.PROVIDER,
                    kind=_classify_http_error(create, create.status_code),
                    detail=f"POST /session HTTP {create.status_code}: {create.text[:300]}",
                ))
            session_id = create.json().get("id")
            if not session_id:
                raise ModelFailureError(ModelFailure(
                    provider=self.PROVIDER, kind="protocol",
                    detail=f"POST /session returned no id: {create.text[:300]}",
                ))

            payload: dict[str, Any] = {
                "messageID": f"msg_{int(time.time() * 1000)}",
                "parts": [{"type": "text", "text": message}],
            }
            if self.agent_type:
                payload["agent"] = self.agent_type
            try:
                msg = client.post(
                    f"{self.server_url}/session/{session_id}/message", json=payload
                )
            except Exception as exc:
                raise ModelFailureError(ModelFailure(
                    provider=self.PROVIDER, kind=_classify_http_error(exc, None),
                    detail=f"POST /session/{session_id}/message failed: {exc}",
                ))
            if msg.is_error:
                raise ModelFailureError(ModelFailure(
                    provider=self.PROVIDER,
                    kind=_classify_http_error(msg, msg.status_code),
                    detail=(
                        f"POST /session/{session_id}/message HTTP {msg.status_code}: "
                        f"{msg.text[:300]}"
                    ),
                ))
            return msg.json()
        finally:
            if close:
                client.close()
