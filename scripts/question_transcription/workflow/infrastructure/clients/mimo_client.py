#!/usr/bin/env python3
"""Small OpenAI-compatible MiMo client with deterministic disk caching."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import httpx

MIMO_BASE_URL = "https://api.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5"

ProviderCallable = Callable[[dict[str, Any]], dict[str, Any] | str]


def extract_json(value: str | dict[str, Any]) -> dict[str, Any]:
    """Extract one JSON object from a provider response, including fenced JSON."""
    if isinstance(value, dict):
        return value
    text = value.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                result, _ = decoder.raw_decode(text[index:])
                break
            except json.JSONDecodeError:
                continue
        else:
            raise ValueError("provider response does not contain a JSON object")
    if not isinstance(result, dict):
        raise ValueError("provider response JSON root must be an object")
    return result


class MimoClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = MIMO_BASE_URL,
        model: str = MIMO_MODEL,
        timeout_s: float = 120.0,
        cache_dir: Path | None = None,
        provider: ProviderCallable | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("MIMO_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.cache_dir = cache_dir
        self.provider = provider
        self.http_client = http_client

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
        cache_material: dict[str, Any],
        max_completion_tokens: int = 8192,
    ) -> tuple[dict[str, Any], bool]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {"type": "json_object"},
        }
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "request": cache_material,
                    "model": self.model,
                    "base_url": self.base_url,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json" if self.cache_dir else None
        if cache_path and cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return extract_json(cached["normalized"]), True

        if self.provider is not None:
            raw = self.provider(body)
        else:
            if not self.api_key:
                raise RuntimeError("MIMO_API_KEY is required for a live MiMo call")
            client = self.http_client or httpx.Client(timeout=self.timeout_s)
            close_client = self.http_client is None
            try:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
                raw = payload["choices"][0]["message"]["content"]
            finally:
                if close_client:
                    client.close()

        normalized = extract_json(raw)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {
                        "cache_key": cache_key,
                        "raw": raw,
                        "normalized": normalized,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            tmp.replace(cache_path)
        return normalized, False
