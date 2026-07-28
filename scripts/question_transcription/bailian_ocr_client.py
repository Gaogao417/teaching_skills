#!/usr/bin/env python3
"""Small BaiLian Qwen-OCR client with deterministic disk caching."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable

import httpx

from scripts.question_transcription.mimo_client import extract_json


BAILIAN_OCR_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BAILIAN_OCR_MODEL = "qwen3.5-ocr"

ProviderCallable = Callable[[dict[str, Any]], dict[str, Any] | str]


class BailianOcrClient:
    """Call BaiLian's OpenAI-compatible Qwen-OCR Chat API.

    The client deliberately does not load ``.env`` files. Production callers
    must export ``DASHSCOPE_API_KEY`` (or pass ``api_key`` explicitly), which
    prevents repository-local credentials from being copied into artifacts or
    logs.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = BAILIAN_OCR_MODEL,
        timeout_s: float = 180.0,
        cache_dir: Path | None = None,
        provider: ProviderCallable | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        self.base_url = (
            base_url
            or os.environ.get("DASHSCOPE_BASE_URL")
            or BAILIAN_OCR_BASE_URL
        ).rstrip("/")
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
        max_tokens: int = 16384,
    ) -> tuple[dict[str, Any], bool]:
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.01,
            "max_tokens": max_tokens,
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
                raise RuntimeError(
                    "DASHSCOPE_API_KEY is required for a live BaiLian OCR call"
                )
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
                if response.is_error:
                    detail = response.text[:2000]
                    raise RuntimeError(
                        f"BaiLian OCR HTTP {response.status_code}: {detail}"
                    )
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
