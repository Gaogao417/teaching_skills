#!/usr/bin/env python3
"""Tests for BaiLian ``complete_text`` and the PDF per-page prescan (§5.3 / §10.1).

No network: the client's ``provider`` seam returns canned strings. Cases mirror
``docs/question-span-index-redesign.md`` §10.1 prescan requirements.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from PIL import Image

from scripts.question_transcription.workflow.adapters.page_text.bailian_ocr_client import (
    BAILIAN_OCR_MODEL,
    BailianOcrClient,
)
from scripts.question_transcription.workflow.adapters.source.pdf_source_manifest import build_manifest
from scripts.question_transcription.prescan_pdf_pages import (
    PRESCAN_PROMPT,
    PRESCAN_PROMPT_VERSION,
    prescan_pages,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _client(
    tmp_path: Path,
    provider,
    *,
    model: str = BAILIAN_OCR_MODEL,
) -> BailianOcrClient:
    return BailianOcrClient(
        api_key="not-logged",
        cache_dir=tmp_path / "cache",
        provider=provider,
        model=model,
    )


def _manifest(tmp_path: Path, *, n_pages: int = 3) -> tuple[Path, object]:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    # Distinct colours so each page has a distinct SHA (cache key). Identical
    # page bytes would collide, which is unrealistic for real papers.
    colours = ["white", "beige", "lightblue", "lightgreen", "mistyrose"]
    paths = []
    for number in range(1, n_pages + 1):
        path = pages_dir / f"{number:03d}.png"
        Image.new("RGB", (40, 50), colours[(number - 1) % len(colours)]).save(path)
        paths.append(path)
    manifest = build_manifest(
        paper_id="TEST-PDF",
        source_archive=tmp_path.as_posix(),
        page_paths=paths,
    )
    return tmp_path, manifest


# --------------------------------------------------------------------------- #
# §10.1: complete_text does NOT route through JSON extraction
# --------------------------------------------------------------------------- #


def test_complete_text_does_not_extract_json(tmp_path: Path):
    calls: list[dict] = []

    def provider(body):
        calls.append(body)
        # A response that is plainly NOT json and contains characters that would
        # confuse extract_json; complete_text must return it verbatim.
        return "1. 题一\n解：{not json at all}\n2. 题二"

    client = _client(tmp_path, provider)
    text, cached = client.complete_text(
        messages=[{"role": "user", "content": [{"type": "text", "text": "p"}]}],
        cache_material={"task": "pdf_prescan", "prompt_version": PRESCAN_PROMPT_VERSION, "page_sha256": "sha256:abc"},
    )
    assert cached is False
    assert text == "1. 题一\n解：{not json at all}\n2. 题二"
    # The raw text is stored, not an extracted JSON object.
    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert len(cache_files) == 1
    record = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert "raw_text" in record and "normalized" not in record


def test_complete_text_and_complete_json_keep_distinct_cache_records(tmp_path: Path):
    # Same cache_material but different methods must NOT collide: each gets its
    # own cache file (keyed by mode) and a second read returns the right record.
    cache_material = {"task": "pdf_prescan", "prompt_version": "v", "page_sha256": "sha256:abc"}

    def text_provider(body):
        return "plain text"

    client_text = _client(tmp_path / "t", text_provider)
    text_first, _ = client_text.complete_text(
        messages=[{"role": "user", "content": "p"}], cache_material=cache_material
    )

    def json_provider(body):
        return '```json\n{"questions": []}\n```'

    client_json = BailianOcrClient(
        api_key="x", cache_dir=tmp_path / "t" / "cache", provider=json_provider
    )
    json_first, _ = client_json.complete_json(
        messages=[{"role": "user", "content": "p"}], cache_material=cache_material
    )

    cache_files = list((tmp_path / "t" / "cache").glob("*.json"))
    assert len(cache_files) == 2  # one per mode
    assert text_first == "plain text"
    assert json_first == {"questions": []}


# --------------------------------------------------------------------------- #
# §10.1: cache hit does not call the provider again
# --------------------------------------------------------------------------- #


def test_cache_hit_does_not_recall_provider(tmp_path: Path):
    calls: list[dict] = []

    def provider(body):
        calls.append(body)
        return "page text"

    client = _client(tmp_path, provider)
    messages = [{"role": "user", "content": [{"type": "text", "text": "p"}]}]
    cache_material = {"task": "pdf_prescan", "prompt_version": PRESCAN_PROMPT_VERSION, "page_sha256": "sha256:abc"}
    first, first_cached = client.complete_text(messages=messages, cache_material=cache_material)
    second, second_cached = client.complete_text(messages=messages, cache_material=cache_material)
    assert first == second == "page text"
    assert first_cached is False
    assert second_cached is True
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# §10.1: cache key changes with page SHA / prompt / model
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "change",
    [
        {"page_sha256": "sha256:DIFFERENT"},
        {"prompt_version": "pdf-prescan-v2"},
        {"task": "different_task"},
    ],
)
def test_cache_key_changes_with_inputs(tmp_path: Path, change):
    calls: list[str] = []

    def provider(body):
        calls.append(body["messages"][0]["content"])
        return "text"

    client = _client(tmp_path, provider)
    base = {"task": "pdf_prescan", "prompt_version": PRESCAN_PROMPT_VERSION, "page_sha256": "sha256:abc"}
    client.complete_text(messages=[{"role": "user", "content": "p"}], cache_material=base)
    changed = {**base, **change}
    client.complete_text(messages=[{"role": "user", "content": "p"}], cache_material=changed)
    assert len(calls) == 2  # different cache key -> second call hit the provider


def test_cache_key_changes_with_model(tmp_path: Path):
    calls: list[str] = []

    def provider(body):
        calls.append(body["model"])
        return "text"

    base = {"task": "pdf_prescan", "prompt_version": PRESCAN_PROMPT_VERSION, "page_sha256": "sha256:abc"}
    c1 = _client(tmp_path / "a", provider, model="model-A")
    c2 = _client(tmp_path / "a", provider, model="model-B")  # same cache_dir
    c1.complete_text(messages=[{"role": "user", "content": "p"}], cache_material=base)
    c2.complete_text(messages=[{"role": "user", "content": "p"}], cache_material=base)
    assert calls == ["model-A", "model-B"]


# --------------------------------------------------------------------------- #
# §10.1: prescan manifest + page text are written atomically; page numbers read
# explicitly from the manifest (not file-name sort)
# --------------------------------------------------------------------------- #


def test_prescan_writes_manifest_and_page_text_atomically(tmp_path: Path):
    _, manifest = _manifest(tmp_path, n_pages=3)
    texts = {1: "page one text", 2: "page two text", 3: "page three text"}

    # The provider is called once per page in manifest order. Dispatch by count.
    sequence = iter([1, 2, 3])

    def ordered_provider(body):
        return texts[next(sequence)]

    client = _client(tmp_path, ordered_provider)
    out_dir = tmp_path / "prescan"
    result = prescan_pages(manifest, client=client, output_dir=out_dir)

    # Atomic write: no leftover .tmp files.
    assert list(out_dir.glob("*.tmp")) == []
    assert (out_dir / "prescan-manifest.yaml").exists()
    # One text file per page, named by logical page number.
    assert {p.name for p in out_dir.glob("page-*.txt")} == {
        "page-001.txt", "page-002.txt", "page-003.txt"
    }
    for entry in result["pages"]:
        assert (
            (out_dir / entry["text_file"]).read_text(encoding="utf-8")
            == texts[entry["physical_page_number"]]
        )
    # Manifest records explicit page numbers in manifest order.
    assert [p["page_number"] for p in result["pages"]] == [1, 2, 3]
    assert result["prompt_version"] == PRESCAN_PROMPT_VERSION
    assert result["model"] == BAILIAN_OCR_MODEL


def test_prescan_page_number_offset_applied(tmp_path: Path):
    _, manifest = _manifest(tmp_path, n_pages=2)

    def provider(body):
        return "text"

    client = _client(tmp_path, provider)
    out_dir = tmp_path / "prescan"
    result = prescan_pages(
        manifest, client=client, output_dir=out_dir, page_number_offset=8
    )
    # Logical page numbers shifted by offset; text files named accordingly.
    assert [p["page_number"] for p in result["pages"]] == [9, 10]
    assert {p.name for p in out_dir.glob("page-*.txt")} == {"page-009.txt", "page-010.txt"}
    # Physical page numbers preserved for traceability.
    assert [p["physical_page_number"] for p in result["pages"]] == [1, 2]
    assert result["page_number_offset"] == 8


def test_prescan_reuses_cached_text_only_when_sha_model_prompt_match(tmp_path: Path):
    _, manifest = _manifest(tmp_path, n_pages=1)
    calls: list[str] = []

    def provider(body):
        calls.append("call")
        return "first text"

    client = _client(tmp_path, provider)
    out_dir = tmp_path / "prescan"
    prescan_pages(manifest, client=client, output_dir=out_dir)
    # Second run: same page SHA + model + prompt version -> cache hit, no provider call.
    prescan_pages(manifest, client=client, output_dir=out_dir)
    assert len(calls) == 1
    assert (out_dir / "page-001.txt").read_text(encoding="utf-8") == "first text"


# --------------------------------------------------------------------------- #
# §10.1: non-contiguous or misaligned page numbers are rejected
# --------------------------------------------------------------------------- #


def test_prescan_rejects_negative_offset(tmp_path: Path):
    _, manifest = _manifest(tmp_path, n_pages=1)

    def provider(body):
        return "x"

    client = _client(tmp_path, provider)
    with pytest.raises(ValueError):
        prescan_pages(
            manifest, client=client, output_dir=tmp_path / "out", page_number_offset=-1
        )
