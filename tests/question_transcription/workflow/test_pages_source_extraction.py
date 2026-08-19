"""Phase 2 P2-01 source-extraction tests: ``pages`` packs, answer supplements,
and the fail-closed non-question-page declaration.

These cover the ingestion entry contract for the two real MVP source packs:

- ``pages`` (2025-HUANGPU-YIMO): original page images + ``manifest.json``
  integrity manifest, mixed ``.jpg``/``.png`` suffixes, explicit cover/QR
  declarations;
- ``docx`` + ``answer_archive`` (2020-MINHANG-YIMO): question-only exam docx
  whose official answers live in a separate original document, with the
  answer's rendered pages continuing the exam's page numbering.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.source import (  # noqa: E402
    extraction,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (  # noqa: E402
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import (  # noqa: E402
    RunLayout,
)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _jpg_bytes(seed: int = 0, width: int = 1500) -> bytes:
    from PIL import Image

    import io

    buffer = io.BytesIO()
    Image.new("RGB", (width + seed, 40), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def _png_bytes(seed: int = 0, width: int = 1500) -> bytes:
    """Distinct real PNG bytes per seed (width varies so hashes never collide)."""
    from PIL import Image

    import io

    buffer = io.BytesIO()
    Image.new("RGB", (width + seed, 60), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "PAPER-PAGES", "run-test")
    layout.root.mkdir(parents=True, exist_ok=True)
    return ArtifactStore(layout)


def _make_pages_pack(tmp_path: Path, *, with_declaration: bool = True) -> Path:
    """A miniature HUANGPU-shaped pack: jpg cover, png pages, jpg QR tail."""
    pack = tmp_path / "documents/初三/PAGES-PACK"
    pack.mkdir(parents=True)
    images = []
    for name, payload in [
        ("001.jpg", _jpg_bytes(0)),
        ("002.png", _png_bytes(1)),
        ("003.png", _png_bytes(2)),
        ("004.png", _png_bytes(3)),
        ("005.jpg", _jpg_bytes(9)),
    ]:
        (pack / name).write_bytes(payload)
        images.append(
            {
                "index": len(images) + 1,
                "file": name,
                "sha256": _sha256_bytes(payload),
            }
        )
    (pack / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_url": "https://example.invalid/article",
                "images": images,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pack / "page.html").write_text("<html></html>", encoding="utf-8")
    if with_declaration:
        (pack / "non-question-pages.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema": "math_non_question_pages/v1",
                    "pages": [
                        {
                            "page_number": 1,
                            "role": "cover",
                            "note": "article cover",
                        },
                        {
                            "page_number": 5,
                            "role": "qr_code",
                            "note": "tail QR",
                        },
                    ],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
    return pack


def _extract_pages(store: ArtifactStore, pack: Path, **kwargs):
    source = extraction.SourceInput(
        paper_id="PAPER-PAGES",
        source_kind="pages",
        source_path=str(pack),
        source_archive=str(pack),
        **kwargs,
    )
    return extraction.DocxOrPdfSourceExtractor(store).extract(source)


def test_pages_pack_extracts_with_integrity_and_declaration(tmp_path: Path) -> None:
    pack = _make_pages_pack(tmp_path)
    store = _store(tmp_path)
    extracted, error_kind, detail = _extract_pages(store, pack)

    assert error_kind is None, detail
    assert extracted is not None
    # All five original pages are frozen (byte-exact copies), in pack numbering.
    assert [ref.path for ref in extracted.pages] == [
        "source/pages/001.jpg",
        "source/pages/002.png",
        "source/pages/003.png",
        "source/pages/004.png",
        "source/pages/005.jpg",
    ]
    copied = store.layout.root / "source/pages/002.png"
    assert copied.read_bytes() == (pack / "002.png").read_bytes()

    # The non-question claims travel on ExtractedSource and the page plan.
    assert [entry.page_number for entry in extracted.non_question_pages] == [1, 5]
    assert extracted.non_question_pages[0].role == "cover"
    plan = yaml.safe_load(
        (store.layout.root / "source/page-plan.yaml").read_text(encoding="utf-8")
    )
    assert plan["schema"] == "math_page_plan/v1"
    assert plan["non_question_pages"][1]["role"] == "qr_code"
    assert plan["pages"][2]["origin_archive"].endswith("PAGES-PACK")
    assert plan["pages"][2]["origin_page_number"] == 3
    assert plan["sources"][0]["role"] == "primary"

    # The committed source manifest uses the pack's own numbering and is a
    # math_pdf_source/v1 payload (empty attribution downstream, no detection).
    manifest = yaml.safe_load(
        (store.layout.root / "source/source-ref.yaml").read_text(encoding="utf-8")
    )
    assert manifest["schema"] == "math_pdf_source/v1"
    assert [page["page_number"] for page in manifest["pages"]] == [1, 2, 3, 4, 5]
    assert manifest["pages"][0]["source"] == "001.jpg"


def test_pages_pack_rejects_tampered_page_hash(tmp_path: Path) -> None:
    """C-INT-04 premise: a page whose bytes drift from manifest.json fails closed."""
    pack = _make_pages_pack(tmp_path)
    (pack / "003.png").write_bytes(b"tampered-page-bytes")

    store = _store(tmp_path)
    extracted, error_kind, detail = _extract_pages(store, pack)

    assert extracted is None
    assert error_kind == "source_integrity_failed"
    assert "003.png" in detail


def test_pages_pack_requires_manifest_json(tmp_path: Path) -> None:
    pack = _make_pages_pack(tmp_path)
    (pack / "manifest.json").unlink()

    store = _store(tmp_path)
    extracted, error_kind, detail = _extract_pages(store, pack)

    assert extracted is None
    assert error_kind == "source_not_found"
    assert "manifest.json" in detail


def test_declaration_outside_page_set_fails_extraction(tmp_path: Path) -> None:
    pack = _make_pages_pack(tmp_path)
    (pack / "non-question-pages.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_non_question_pages/v1",
                "pages": [{"page_number": 9, "role": "blank"}],
            }
        ),
        encoding="utf-8",
    )

    store = _store(tmp_path)
    extracted, error_kind, detail = _extract_pages(store, pack)

    assert extracted is None
    assert error_kind == "normalization_failed"
    assert "[9]" in detail


def test_malformed_declaration_role_fails_extraction(tmp_path: Path) -> None:
    pack = _make_pages_pack(tmp_path)
    (pack / "non-question-pages.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "math_non_question_pages/v1",
                "pages": [{"page_number": 1, "role": "suspicious"}],
            }
        ),
        encoding="utf-8",
    )

    store = _store(tmp_path)
    extracted, error_kind, _ = _extract_pages(store, pack)

    assert extracted is None
    assert error_kind == "normalization_failed"


# --------------------------------------------------------------------------- #
# DOCX + supplementary answer document (2020-MINHANG-YIMO shape)
# --------------------------------------------------------------------------- #


class _FakeDocxExtract:
    """Monkeypatch stand-in for extract_docx_source.extract.

    Emits a word-source-shaped manifest with real on-disk page PNGs so the
    merge path exercises real file copies and hash verification.
    """

    def __init__(self, page_count: int) -> None:
        self.page_count = page_count

    def __call__(self, source: Path, output_dir: Path, soffice, dpi, render_pdf: bool):
        pages_dir = output_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        rendered = []
        answer = "official-answer" in str(source)
        for number in range(1, self.page_count + 1):
            payload = _png_bytes(100 + number if answer else number)
            page_path = pages_dir / f"{number:03d}.png"
            page_path.write_bytes(payload)
            rendered.append(
                {
                    "path": f"pages/{number:03d}.png",
                    "sha256": _sha256_bytes(payload),
                    "width_px": 40,
                    "height_px": 60,
                }
            )
        return {
            "schema": "math_word_source_extract/v1",
            "source": {"path": "source.docx", "sha256": _sha256_bytes(b"doc")},
            "media": [],
            "image_attribution": [],
            "rendered_pages": rendered,
        }


def _extract_docx_with_answer(tmp_path: Path, *, declare_blank: bool = True):
    exam_dir = tmp_path / "documents/初三/EXAM-PACK"
    exam_dir.mkdir(parents=True)
    exam_docx = exam_dir / "source.docx"
    exam_docx.write_bytes(b"exam-docx-bytes")
    answer_docx = tmp_path / "documents/answers/official-answer.docx"
    answer_docx.parent.mkdir(parents=True)
    answer_docx.write_bytes(b"answer-docx-bytes")
    if declare_blank:
        (exam_dir / "non-question-pages.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema": "math_non_question_pages/v1",
                    "pages": [
                        {
                            "page_number": 7,
                            "role": "blank",
                            "note": "trailing blank render page",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    store = _store(tmp_path)
    source = extraction.SourceInput(
        paper_id="PAPER-PAGES",
        source_kind="docx",
        source_path=str(exam_docx),
        source_archive=str(exam_docx),
        answer_archive=str(answer_docx),
    )

    # ``from extract_docx_source import extract`` inside the adapter resolves
    # through sys.modules first, so a pre-registered fake module wins without
    # touching builtins.__import__.
    def extract(source_path, output_dir, soffice, dpi, render_pdf):
        is_answer = "official-answer" in str(source_path)
        pages = 3 if is_answer else 7
        return _FakeDocxExtract(pages)(source_path, output_dir, soffice, dpi, render_pdf)

    fake_module = type(sys)("extract_docx_source")
    fake_module.extract = extract
    saved_module = sys.modules.get("extract_docx_source")
    sys.modules["extract_docx_source"] = fake_module
    try:
        result = extraction.DocxOrPdfSourceExtractor(store).extract(source)
    finally:
        if saved_module is None:
            sys.modules.pop("extract_docx_source", None)
        else:
            sys.modules["extract_docx_source"] = saved_module
    return store, result


def test_docx_answer_supplement_continues_page_numbering(tmp_path: Path) -> None:
    store, (extracted, error_kind, detail) = _extract_docx_with_answer(tmp_path)

    assert error_kind is None, detail
    assert extracted is not None
    # 7 exam pages + 3 answer pages, one contiguous numbering.
    assert len(extracted.pages) == 10
    assert extracted.pages[7].path == "source/docx/pages/008.png"
    assert extracted.pages[9].path == "source/docx/pages/010.png"
    assert extracted.answer_source.endswith("official-answer.docx")
    assert extracted.answer_sha256 == _sha256_bytes(b"answer-docx-bytes")

    plan = yaml.safe_load(
        (store.layout.root / "source/page-plan.yaml").read_text(encoding="utf-8")
    )
    roles = {entry["role"]: entry for entry in plan["sources"]}
    assert set(roles) == {"primary", "answer_supplement"}
    # Page 8 is answer page 1; page 7 is the (declared blank) exam page 7.
    assert plan["pages"][7]["origin_page_number"] == 1
    assert "official-answer" in plan["pages"][7]["origin_archive"]
    assert plan["pages"][6]["origin_page_number"] == 7
    assert plan["pages"][6]["origin_archive"].endswith("source.docx")
    assert plan["non_question_pages"] == [
        {"page_number": 7, "role": "blank", "note": "trailing blank render page"}
    ]
    # The merged word-source manifest lists all ten rendered pages in order.
    manifest = yaml.safe_load(
        (store.layout.root / "source/source-ref.yaml").read_text(encoding="utf-8")
    )
    assert [
        page["path"] for page in manifest["rendered_pages"]
    ] == [f"pages/{number:03d}.png" for number in range(1, 11)]


def test_docx_without_declaration_keeps_strict_default(tmp_path: Path) -> None:
    _, (extracted, error_kind, _) = _extract_docx_with_answer(
        tmp_path, declare_blank=False
    )
    assert error_kind is None
    assert extracted is not None
    assert extracted.non_question_pages == []


# --------------------------------------------------------------------------- #
# Node-level wiring: declared pages are excluded from the page-text fan-out
# --------------------------------------------------------------------------- #


def test_extract_source_node_skips_declared_pages(tmp_path: Path) -> None:
    pack = _make_pages_pack(tmp_path)
    store = _store(tmp_path)
    extracted, error_kind, _ = _extract_pages(store, pack)
    assert error_kind is None and extracted is not None

    from scripts.question_transcription.workflow.nodes.source import (
        make_extract_source_node,
    )

    class _Deps:
        deterministic = type("D", (), {})()
        artifact_store = store
        run_layout = store.layout

    _Deps.deterministic.source_extractor = type(
        "E", (), {"extract": staticmethod(lambda source: (extracted, None, None))}
    )()

    node = make_extract_source_node(_Deps)
    update = node(
        {
            "run_id": "run-test",
            "paper_id": "PAPER-PAGES",
            "source_kind": "pages",
            "source_archive": str(pack),
        }
    )
    # Pages 1 (cover) and 5 (QR) are declared → no page-text jobs for them.
    assert [job["page_number"] for job in update["page_text_jobs"]] == [2, 3, 4]
    serialized = update["extracted_source"]
    assert serialized["non_question_pages"][0]["page_number"] == 1


def test_draft_projector_stamps_page_plan_declaration(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.commit_yaml(
        "source/page-plan.yaml",
        {
            "schema": "math_page_plan/v1",
            "paper_id": "P",
            "sources": [],
            "pages": [],
            "non_question_pages": [
                {"page_number": 2, "role": "cover", "note": "封面"}
            ],
        },
        "math_page_plan/v1",
    )
    from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
        DeterministicDraftProjector,
    )

    projector = DeterministicDraftProjector(store)
    draft = {"schema": "math_exam_staging_draft/v1", "paper": {"id": "P"}}
    projector._stamp_page_plan(draft)
    assert draft["paper"]["non_question_pages"] == [
        {"page_number": 2, "role": "cover", "note": "封面"}
    ]

    # No page plan (legacy runs) → draft untouched.
    draft2 = {"schema": "math_exam_staging_draft/v1", "paper": {"id": "P"}}
    (store.layout.source_dir / "page-plan.yaml").unlink()
    projector._stamp_page_plan(draft2)
    assert "non_question_pages" not in draft2["paper"]


def test_full_page_prompt_crops_attached_for_figure_stems(tmp_path: Path) -> None:
    from PIL import Image

    page = tmp_path / "pages" / "002.png"
    page.parent.mkdir(parents=True)
    Image.new("RGB", (120, 200), "white").save(page)
    payload = {
        "schema": "math_exam_staging_draft/v1",
        "sections": [
            {
                "id": "fillin",
                "title": "填空",
                "items": [
                    {
                        "item_id": "Q001",
                        "prompt": [],
                        "block": {"stem_latex": "如图，求 BE 的长。"},
                        "question_word_evidence": [
                            {"page_image": str(page), "page_number": 2}
                        ],
                    },
                    {
                        "item_id": "Q002",
                        "prompt": [],
                        "block": {"stem_latex": "计算 2+2。"},
                        "question_word_evidence": [
                            {"page_image": str(page), "page_number": 2}
                        ],
                    },
                ],
            }
        ],
    }
    from scripts.question_transcription.workflow.adapters.staging.existing_pipeline import (
        DeterministicEvidenceCompleter,
    )

    updated = DeterministicEvidenceCompleter._attach_full_page_prompt_crops(payload)
    items = updated["sections"][0]["items"]
    # 含图题获得整页题图 crop；纯文字题不受影响。
    assert items[0]["prompt"] == [
        {"source": str(page), "box_px": [0, 0, 120, 200]}
    ]
    assert items[1]["prompt"] == []


def test_low_resolution_page_gets_2x_ocr_upscale(tmp_path: Path) -> None:
    """低于 OCR 分辨率阈值的扫描页：run 副本 2x 放大并记入 page plan。"""
    pack = _make_pages_pack(tmp_path)
    # 把 003.png 换成低分辨率页（宽度 800 < 1400 阈值）。
    from PIL import Image

    import io

    buffer = io.BytesIO()
    Image.new("RGB", (800, 1000), "white").save(buffer, format="PNG")
    low_res = buffer.getvalue()
    (pack / "003.png").write_bytes(low_res)
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["images"]:
        if entry["file"] == "003.png":
            entry["sha256"] = _sha256_bytes(low_res)
    (pack / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    store = _store(tmp_path)
    extracted, error_kind, detail = _extract_pages(store, pack)
    assert error_kind is None, detail

    run_copy = store.layout.root / "source/pages/003.png"
    with Image.open(run_copy) as image:
        assert image.size == (1600, 2000)
    plan = yaml.safe_load(
        (store.layout.root / "source/page-plan.yaml").read_text(encoding="utf-8")
    )
    by_page = {entry["page_number"]: entry for entry in plan["pages"]}
    assert by_page[3]["ocr_enhancement"] == "2x-lanczos"
    assert "ocr_enhancement" not in by_page[2]
    # manifest 里的 sha256 仍是原始包文件的字节（完整性锚点不被放大改写）。
    source_ref = yaml.safe_load(
        (store.layout.root / "source/source-ref.yaml").read_text(encoding="utf-8")
    )
    by_source = {entry["source"]: entry for entry in source_ref["pages"]}
    assert by_source["003.png"]["sha256"] == _sha256_bytes(low_res)
