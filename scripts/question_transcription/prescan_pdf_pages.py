#!/usr/bin/env python3
"""Low-cost per-page PDF prescan that feeds the question-span index (§5.3).

Each page is sent to BaiLian on its own for a faithful OCR of the text, formulae
and question-number anchors. No bbox is requested — the formal observation step
(MiMo joint text+bbox) still owns the bbox contract. The output is one text file
per page plus a ``prescan-manifest.yaml`` that records the prompt, model, page
SHA, page number and text-file mapping. Page numbers are read explicitly from the
source manifest (never inferred from file-name string sort).

Page text files are written atomically (temp file + ``replace``) and only reused
when the page SHA, model and prompt version all match.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
from pathlib import Path
import sys
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.question_transcription.workflow.adapters.page_text.bailian_ocr_client import BailianOcrClient
from scripts.question_transcription.pdf_observation_contracts import PdfSourceManifest


PRESCAN_PROMPT_VERSION = "pdf-prescan-v1"
PRESCAN_SCHEMA = "math_pdf_prescan/v1"

PRESCAN_PROMPT = (
    "你是数学试卷逐页 OCR 预扫器。只忠实转录本页可见的文字、公式和题号,不要识别 "
    "bbox、不要解释、不要总结。题号保持原样(如 `1．`、`2.`)。公式用可读文本或 "
    "LaTeX。不要补全、不要合并多页。直接输出该页的纯文本,不要 JSON、不要 Markdown "
    "代码块、不要前后缀说明。"
)


# --------------------------------------------------------------------------- #
# Page path / sha helpers
# --------------------------------------------------------------------------- #


def _page_path(manifest: PdfSourceManifest, page) -> Path:  # noqa: ANN001
    path = Path(page.source)
    if path.is_absolute():
        return path
    return Path(manifest.source_archive) / path


def _data_url(path: Path) -> str:
    media_type = "image/jpeg" if path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


# --------------------------------------------------------------------------- #
# Atomic write helper
# --------------------------------------------------------------------------- #


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------- #
# Prescan entry point
# --------------------------------------------------------------------------- #


def prescan_pages(
    manifest: PdfSourceManifest,
    *,
    client: BailianOcrClient,
    output_dir: Path,
    page_number_offset: int = 0,
    prompt: str = PRESCAN_PROMPT,
    prompt_version: str = PRESCAN_PROMPT_VERSION,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the per-page prescan and write ``prescan-manifest.yaml`` + page texts.

    Returns the prescan manifest dict (also persisted). Page numbers are taken
    from ``manifest.pages[].page_number`` and shifted by ``page_number_offset``
    so separated answer files line up with ``discover_pages()``.
    """
    if page_number_offset < 0:
        raise ValueError("page_number_offset must be non-negative")
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_model = model or client.model

    entries: list[dict[str, Any]] = []
    for page in manifest.pages:
        image_path = _page_path(manifest, page)
        page_sha = _sha256(image_path)
        logical_page_number = page.page_number + page_number_offset
        cache_material = {
            "task": "pdf_prescan",
            "prompt_version": prompt_version,
            "page_sha256": page_sha,
        }
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _data_url(image_path)}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        text, _cache_hit = client.complete_text(
            messages=messages,
            cache_material=cache_material,
        )
        text_file = output_dir / f"page-{logical_page_number:03d}.txt"
        _atomic_write_text(text_file, text)
        entries.append(
            {
                "page_number": logical_page_number,
                "physical_page_number": page.page_number,
                "page_sha256": page_sha,
                "text_file": text_file.name,
                "prompt_version": prompt_version,
                "model": resolved_model,
            }
        )

    prescan_manifest = {
        "schema": PRESCAN_SCHEMA,
        "paper_id": manifest.paper_id,
        "source_archive": manifest.source_archive,
        "prompt": prompt,
        "prompt_version": prompt_version,
        "model": resolved_model,
        "page_number_offset": page_number_offset,
        "pages": entries,
    }
    manifest_path = output_dir / "prescan-manifest.yaml"
    _atomic_write_text(
        manifest_path,
        yaml.safe_dump(prescan_manifest, allow_unicode=True, sort_keys=False, width=1000),
    )
    return prescan_manifest


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--page-number-offset", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    manifest = PdfSourceManifest.model_validate(
        yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    )
    client = BailianOcrClient(
        cache_dir=args.cache_dir, timeout_s=args.timeout
    )
    prescan = prescan_pages(
        manifest,
        client=client,
        output_dir=args.output_dir,
        page_number_offset=args.page_number_offset,
    )
    print(
        f"PDF PRESCAN: {args.output_dir / 'prescan-manifest.yaml'} | "
        f"pages={len(prescan['pages'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
