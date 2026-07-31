"""OpenCode PydanticAI ``Model`` bridge (architecture §3.2, M1.3).

:class:`OpencodeModel` subclasses the installed PydanticAI 2.x :class:`Model` with
``provider=None`` and turns the OpenCode session/message transport into the
``request()`` member the Agent calls. It is domain-free: it never references a math
question schema, and surfaces failures as provider-neutral
:class:`~scripts.infrastructure.ai.contracts.ModelFailureError` rather than a domain
exception.

The bridge intentionally keeps the existing "flatten all PydanticAI messages into a
single text prompt" mapping: the OpenCode transport is text-only and stateless from
the caller's perspective (a fresh session id per call), so on ``ModelRetry`` the whole
conversation (user + prior assistant text + retry instruction) is replayed in order.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models import Model, check_allow_model_requests
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RequestUsage

from ..contracts import ModelFailure, ModelFailureError
from .client import OpencodeClient, extract_opencode_text


__all__ = ["OpencodeModel", "convert_messages_to_prompt"]


def convert_messages_to_prompt(messages: list[Any]) -> str:
    """Flatten PydanticAI messages into the text-only OpenCode transport.

    On ``ModelRetry`` the Agent calls the Model again with the prior assistant text
    and validation feedback appended. Keeping every part in order lets the existing
    stateless ``POST /session`` transport receive the complete retry conversation.
    """

    blocks: list[str] = []
    for message in messages:
        for part in getattr(message, "parts", []):
            content = getattr(part, "content", None)
            if isinstance(content, list):
                fragments: list[str] = []
                for item in content:
                    if isinstance(item, str):
                        fragments.append(item)
                    elif isinstance(getattr(item, "text", None), str):
                        fragments.append(item.text)
                    elif isinstance(item, dict):
                        fragments.append(json.dumps(item, ensure_ascii=False))
                    else:
                        fragments.append(str(item))
                content = "\n".join(fragments)
            if not isinstance(content, str) or not content.strip():
                continue
            part_type = type(part).__name__
            if "System" in part_type or "Instruction" in part_type:
                role = "system"
            elif "User" in part_type:
                role = "user"
            elif "Text" in part_type:
                role = "assistant"
            else:
                role = "user"
            blocks.append(f"[{role}]\n{content.strip()}")
    return "\n\n".join(blocks)


class OpencodeModel(Model):
    """PydanticAI ``Model`` backed by the OpenCode session/message HTTP API.

    No PydanticAI provider object is installed: ``Model.provider`` remains ``None``.
    The injected :class:`OpencodeClient` (or ``send_message`` callable for backward
    compatibility) is the transport boundary.
    """

    def __init__(
        self,
        *,
        model_name: str,
        send_message=None,
        client: OpencodeClient | None = None,
        settings: ModelSettings | None = None,
    ) -> None:
        super().__init__(settings=settings)
        self._model_name = model_name
        # ``send_message`` is the legacy injection seam (a callable prompt->dict).
        # ``client`` is the explicit transport; exactly one must be provided.
        self._send_message = send_message
        self._client = client

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return "opencode"

    def _call_transport(self, prompt: str) -> dict[str, Any]:
        if self._client is not None:
            return self._client.send_message(prompt)
        if self._send_message is None:  # pragma: no cover - defensive
            raise ModelFailureError(ModelFailure(
                provider="opencode", kind="protocol",
                detail="OpencodeModel has no client or send_message",
            ))
        try:
            return self._send_message(prompt)
        except ModelFailureError:
            raise
        except Exception as exc:
            low = str(exc).lower()
            kind = "timed_out" if "timeout" in low else "unavailable"
            raise ModelFailureError(ModelFailure(
                provider="opencode", kind=kind,
                detail=f"server call failed: {exc}",
            ))

    async def request(
        self,
        messages: list[Any],
        model_settings: ModelSettings | None,
        model_request_parameters: Any,
    ) -> ModelResponse:
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters
        )
        check_allow_model_requests()

        prompt = convert_messages_to_prompt(messages)
        raw = await asyncio.to_thread(self._call_transport, prompt)

        text = extract_opencode_text(raw)
        if not text:
            raise ModelFailureError(ModelFailure(
                provider="opencode", kind="protocol",
                detail="server returned empty text",
            ))

        return ModelResponse(
            parts=[TextPart(content=text)],
            usage=RequestUsage(input_tokens=0, output_tokens=0),
            model_name=self._model_name,
            provider_name="opencode",
        )
