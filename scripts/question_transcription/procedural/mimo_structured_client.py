#!/usr/bin/env python3
"""Structured MiMo client backed by ``pydantic_ai`` tool-calling.

``MimoClient.complete_json`` only requests ``response_format=json_object``: MiMo
honours "return legal JSON" but freely drifts on enum values, nested confidence
shapes and missing fields (it even accepts a ``json_schema`` parameter without
enforcing it). MiMo *does* enforce a schema supplied via tool-calling, so this
client drives a :class:`pydantic_ai.Agent` whose ``output_type`` is the caller's
Pydantic model. The model is forced to return structurally-correct objects at the
source, which removes the need for the ad-hoc ``normalize_*`` post-hoc patches.

The client deliberately mirrors ``MimoClient``'s conventions:

* explicit ``MIMO_API_KEY`` (no ``.env`` loading);
* a deterministic, atomic disk cache keyed on the output schema + request
  material + model;
* a ``provider`` injection seam so tests can fake the tool-call response without
  touching the network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

import httpx
from pydantic import BaseModel

from scripts.question_transcription.workflow.infrastructure.clients.mimo_client import MIMO_BASE_URL, MIMO_MODEL

T = TypeVar("T", bound=BaseModel)

# Test seam: a callable that receives the business-level inputs and returns the
# output-tool arguments dict. Production leaves this None so the real
# pydantic_ai Agent runs.
StructuredProviderCallable = Callable[
    [str, str, str, Sequence[Path], dict[str, Any]], dict[str, Any]
]


def _output_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for the output model, folded into the cache key."""
    return model_cls.model_json_schema()


class MimoStructuredClient:
    """Call MiMo via pydantic_ai tool-calling and return a validated model."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = MIMO_BASE_URL,
        model: str = MIMO_MODEL,
        timeout_s: float = 120.0,
        cache_dir: Path | None = None,
        provider: StructuredProviderCallable | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("MIMO_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir
        self.provider = provider

    def complete_structured(
        self,
        *,
        output_type: type[T],
        system_prompt: str,
        prompt: str,
        image_paths: Sequence[Path],
        cache_material: dict[str, Any],
    ) -> tuple[T, bool]:
        """Return ``(validated_model, cache_hit)``.

        The public boundary deliberately accepts paths rather than OpenAI or
        pydantic-ai message objects. The adapter owns conversion to
        :class:`pydantic_ai.BinaryContent`, preventing callers from mixing the
        OpenAI wire format with PydanticAI's ``UserContent`` API.
        """
        schema = _output_schema(output_type)
        paths = tuple(Path(path) for path in image_paths)
        media_fingerprint = [
            {
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "media_type": _image_media_type(path),
            }
            for path in paths
        ]
        cache_key = self._cache_key(
            {
                **cache_material,
                "prompt": prompt,
                "media": media_fingerprint,
            },
            schema,
        )
        cache_path = self.cache_dir / f"{cache_key}.json" if self.cache_dir else None
        if cache_path and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return output_type.model_validate(cached["validated"]), True

        if self.provider is not None:
            args = self.provider(self.model, system_prompt, prompt, paths, schema)
        else:
            args = self._run_agent(output_type, system_prompt, prompt, paths)

        validated = output_type.model_validate(args)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"cache_key": cache_key, "validated": validated.model_dump(mode="json")},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            tmp.replace(cache_path)
        return validated, False

    # ------------------------------------------------------------------ #

    def _cache_key(self, cache_material: dict[str, Any], schema: dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "mode": "structured",
                    "request": cache_material,
                    "output_schema": schema,
                    "model": self.model,
                    "base_url": self.base_url,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def _run_agent(
        self,
        output_type: type[T],
        system_prompt: str,
        prompt: str,
        image_paths: Sequence[Path],
    ) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("MIMO_API_KEY is required for a live MiMo call")
        # Import lazily so the module imports cleanly when pydantic_ai is absent.
        from pydantic_ai import Agent, ToolOutput
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        async def run() -> T:
            async with httpx.AsyncClient(timeout=self.timeout_s) as http_client:
                provider = OpenAIProvider(
                    api_key=self.api_key,
                    base_url=self.base_url,
                    http_client=http_client,
                )
                model = OpenAIChatModel(self.model, provider=provider)
                agent = Agent(
                    model,
                    output_type=ToolOutput(
                        output_type,
                        name="final_result",
                        max_retries=2,
                    ),
                    system_prompt=system_prompt,
                )
                result = await agent.run(_pydantic_user_content(prompt, image_paths))
                return result.output

        result = asyncio.run(run())
        return result.model_dump(mode="json")


def _image_media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    raise ValueError(f"unsupported image type for MiMo structured input: {path}")


def _pydantic_user_content(prompt: str, image_paths: Sequence[Path]) -> list[Any]:
    """Build PydanticAI-native multimodal input, never OpenAI wire messages."""
    from pydantic_ai import BinaryContent

    content: list[Any] = [prompt]
    content.extend(
        BinaryContent(
            data=path.read_bytes(),
            media_type=_image_media_type(path),
            vendor_metadata={"detail": "high"},
        )
        for path in image_paths
    )
    return content
