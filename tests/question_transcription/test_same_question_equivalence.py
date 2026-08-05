"""P4 acceptance: one mathematical question converges across DOCX and PDF.

The fixture is intentionally defined in this test instead of borrowing an
existing transcription golden.  The same semantic question is represented as:

* DOCX: whole rendered-page evidence plus a full-crop ``word/media`` figure;
* PDF: region evidence plus a region-crop figure from an immutable page.

Both representations pass their real adapters and the shared DraftAssembler.
After source-specific evidence, paths, and crop geometry are normalized away,
their semantic drafts must be exactly equal.  Each unnormalized draft must also
pass the real expand -> materialize -> audit pipeline.
"""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow.adapters.source.adapt_docx_images import (  # noqa: E402
    adapt as adapt_docx_images,
)
from scripts.question_transcription.adapt_docx_transcription import (  # noqa: E402
    adapt as adapt_docx_transcription,
)
from scripts.question_transcription.workflow.adapters.source.adapt_pdf_images import (  # noqa: E402
    adapt as adapt_pdf_images,
)
from scripts.question_transcription.adapt_pdf_transcription import (  # noqa: E402
    adapt as adapt_pdf_transcription,
)
from scripts.question_transcription.workflow.adapters.staging.assemble_paper_draft import assemble  # noqa: E402
from scripts.question_transcription.contracts import (  # noqa: E402
    ImageAttributionBundle,
    QuestionTranscriptionBundle,
)
from scripts.question_transcription.docx_observation_contracts import (  # noqa: E402
    DocxObservationBundle,
)
from scripts.question_transcription.pdf_observation_contracts import (  # noqa: E402
    MergedPdfObservation,
)

PDF_INGESTION = ROOT / ".codex/skills/math-pdf-question-bank-ingestion/scripts"
WORD_EVIDENCE = (
    ROOT
    / ".codex/skills/math-docx-question-bank-ingestion/scripts/word_evidence_pages.py"
)

CONTENT = {
    "stem_latex": (
        "如图，在平面直角坐标系中，点$A(0,3)$、$B(4,0)$，求线段$AB$的长。"
    ),
    "answer": "$5$",
    "clue": "利用两点的横、纵坐标差构造直角三角形。",
    "solution_steps": [
        "点$A$与点$B$的横坐标差为$4$，纵坐标差为$3$。",
        "由勾股定理，$AB=\\sqrt{3^2+4^2}$。",
        "所以$AB=5$。",
    ],
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _draw_sources(repo_root: Path) -> tuple[str, str]:
    """Create one figure, a DOCX page, and a PDF page containing that figure."""
    docx_rel = "documents/初三/P4-SAME-QUESTION-DOCX"
    pdf_rel = "documents/初三/P4-SAME-QUESTION-PDF"
    docx_root = repo_root / docx_rel
    pdf_root = repo_root / pdf_rel

    figure = Image.new("RGB", (320, 310), "white")
    draw = ImageDraw.Draw(figure)
    draw.line((35, 275, 285, 275), fill="black", width=3)
    draw.line((35, 275, 35, 25), fill="black", width=3)
    draw.line((35, 75, 235, 275), fill="black", width=4)
    draw.ellipse((28, 68, 42, 82), fill="black")
    draw.ellipse((228, 268, 242, 282), fill="black")
    draw.text((48, 60), "A(0,3)", fill="black")
    draw.text((205, 250), "B(4,0)", fill="black")

    media_path = docx_root / "word/media/coordinate-figure.png"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    figure.save(media_path)

    docx_page = Image.new("RGB", (900, 1200), "white")
    docx_page.paste(figure, (500, 120))
    docx_draw = ImageDraw.Draw(docx_page)
    docx_draw.rectangle((55, 55, 845, 565), outline="black", width=2)
    docx_draw.rectangle((55, 695, 845, 1065), outline="black", width=2)
    docx_page_path = docx_root / "word/pages/001.png"
    docx_page_path.parent.mkdir(parents=True, exist_ok=True)
    docx_page.save(docx_page_path)

    # The PDF page contains the exact same figure pixels at the asserted bbox.
    pdf_page = Image.new("RGB", (900, 1200), "white")
    pdf_page.paste(figure, (500, 120))
    pdf_draw = ImageDraw.Draw(pdf_page)
    pdf_draw.rectangle((55, 55, 845, 565), outline="black", width=2)
    pdf_draw.rectangle((55, 695, 845, 1065), outline="black", width=2)
    pdf_page_path = pdf_root / "pages/001.png"
    pdf_page_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_page.save(pdf_page_path)

    return docx_rel, pdf_rel


def _docx_bundles(
    repo_root: Path, archive: str
) -> tuple[QuestionTranscriptionBundle, ImageAttributionBundle]:
    page_path = repo_root / archive / "word/pages/001.png"
    media_path = repo_root / archive / "word/media/coordinate-figure.png"
    observation = DocxObservationBundle.model_validate(
        {
            "schema": "math_docx_observation/v1",
            "paper": {
                "id": "P4-SAME-QUESTION-DOCX",
                "title": "P4 同题双来源等价卷",
                "grade": "九年级",
                "source_archive": archive,
            },
            "pages": [
                {
                    "page_number": 1,
                    "source": f"{archive}/word/pages/001.png",
                    "width_px": 900,
                    "height_px": 1200,
                    "sha256": _sha256(page_path),
                }
            ],
            "questions": [
                {
                    "question_ref": "1",
                    "question_number": 1,
                    "question_type": "problem",
                    "points": 8,
                    "section_ref": "problem",
                    "section_title": "三、解答题",
                    "content": CONTENT,
                    "evidence": {
                        "question": [
                            {
                                "kind": "page",
                                "source": f"{archive}/word/pages/001.png",
                                "page_number": 1,
                            }
                        ],
                        "solution": [
                            {
                                "kind": "page",
                                "source": f"{archive}/word/pages/001.png",
                                "page_number": 1,
                            }
                        ],
                        "solution_start_anchor": "1．解：",
                        "solution_end_anchor": "<END_OF_SOURCE>",
                    },
                    "transcription_confidence": {
                        "stem": "high",
                        "formula": "high",
                        "solution_steps": "high",
                    },
                }
            ],
            "provider": {
                "kind": "vision_api",
                "name": "mimo-v2.5",
                "version": "v1",
            },
            "conflicts": [],
        }
    )
    word_source = {
        "schema": "math_word_source_extract/v1",
        "media": [
            {
                "path": "media/coordinate-figure.png",
                "sha256": _sha256(media_path),
                "width_px": 320,
                "height_px": 310,
            }
        ],
        "image_attribution": [
            {
                "media": "media/coordinate-figure.png",
                "question_number": 1,
                "bucket": "prompt",
                "paragraph_index": 1,
                "confidence": "high",
            }
        ],
    }
    transcription = adapt_docx_transcription(observation)
    images = ImageAttributionBundle.model_validate(
        adapt_docx_images(
            word_source,
            paper_id=observation.paper.id,
            source_archive=archive,
        )
    )
    return transcription, images


def _pdf_bundles(
    repo_root: Path, archive: str
) -> tuple[QuestionTranscriptionBundle, ImageAttributionBundle]:
    page_path = repo_root / archive / "pages/001.png"
    observation = MergedPdfObservation.model_validate(
        {
            "schema": "math_pdf_merged_observation/v1",
            "paper": {
                "id": "P4-SAME-QUESTION-PDF",
                "title": "P4 同题双来源等价卷",
                "grade": "九年级",
                "source_archive": archive,
            },
            "provider": {
                "kind": "vision_api",
                "name": "mimo-v2.5",
                "version": "v1",
            },
            "prompt_version": "same-question-v1",
            "pages": [
                {
                    "page_number": 1,
                    "source": "pages/001.png",
                    "width_px": 900,
                    "height_px": 1200,
                    "sha256": _sha256(page_path),
                }
            ],
            "questions": [
                {
                    "question_ref": "1",
                    "question_number": 1,
                    "question_type": "problem",
                    "points": 8,
                    "section_ref": "problem",
                    "section_title": "三、解答题",
                    "content": CONTENT,
                    "question_evidence": [
                        {"page_number": 1, "box_px": [60, 60, 840, 560]}
                    ],
                    "solution_evidence": [
                        {"page_number": 1, "box_px": [60, 700, 840, 1060]}
                    ],
                    "solution_start_anchor": "1．解：",
                    "solution_end_anchor": "<END_OF_SOURCE>",
                    "figures": [
                        {
                            "local_id": "q1-prompt",
                            "page_number": 1,
                            "role": "prompt",
                            "order": 0,
                            "box_px": [500, 120, 820, 430],
                            "confidence": "high",
                            "state": "accepted",
                            "note": "coordinate figure",
                        }
                    ],
                    "confidence": {
                        "stem": "high",
                        "formula": "high",
                        "bbox": "high",
                    },
                }
            ],
            "source_windows": ["page-001"],
        }
    )
    transcription = QuestionTranscriptionBundle.model_validate(
        adapt_pdf_transcription(observation)
    )
    # The test acts as the explicit human crop confirmation required by the PDF
    # workflow, so the already checked region is allowed into the assembler.
    images = ImageAttributionBundle.model_validate(
        adapt_pdf_images(observation, allow_model_accepted=True)
    )
    return transcription, images


def _semantic_transcription(bundle: QuestionTranscriptionBundle) -> dict[str, Any]:
    """Keep only source-independent paper/question meaning."""
    return {
        "title": bundle.paper.title,
        "grade": bundle.paper.grade,
        "subject": bundle.paper.subject,
        "sections": [
            {
                "section_ref": section.section_ref,
                "title": section.title,
                "questions": [
                    {
                        "question_ref": question.question_ref,
                        "question_number": question.question_number,
                        "question_type": question.question_type,
                        "points": question.points,
                        "content": question.content.model_dump(),
                    }
                    for question in section.questions
                ],
            }
            for section in bundle.sections
        ],
    }


def _semantic_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Drop evidence/crop/path details while preserving image-role cardinality."""
    normalized = deepcopy(draft)
    normalized["paper"]["id"] = "<SOURCE-INDEPENDENT>"
    normalized["paper"]["source_archive"] = "<SOURCE-INDEPENDENT>"
    for section in normalized["sections"]:
        for item in section["items"]:
            item.pop("question_evidence", None)
            item.pop("question_word_evidence", None)
            item["prompt"] = [{"role": "prompt"} for _ in item.get("prompt", [])]
            official = item["official_solution"]
            official.pop("crops", None)
            official.pop("word_evidence", None)
    return normalized


def _run_downstream(
    repo_root: Path,
    draft: dict[str, Any],
    *,
    docx_track: bool,
) -> subprocess.CompletedProcess[str]:
    paper_id = draft["paper"]["id"]
    staging = repo_root / "staging" / paper_id
    staging.mkdir(parents=True)
    draft["question_bank"] = "../../question-bank.yaml"

    if docx_track:
        word_evidence = _load_module(
            f"word_evidence_{paper_id}", WORD_EVIDENCE
        )
        draft, resolution = word_evidence.resolve_draft_payload(
            draft, repo_root=repo_root
        )
        assert resolution["changes"] == []

    draft_path = staging / "paper.draft.yaml"
    draft_path.write_text(
        yaml.safe_dump(draft, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )

    expand = _load_module(f"expand_{paper_id}", PDF_INGESTION / "expand_staging_draft.py")
    expand.expand_draft(draft_path)

    materialize = subprocess.run(
        [
            sys.executable,
            str(PDF_INGESTION / "materialize_staging.py"),
            str(staging),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
    )
    assert materialize.returncode == 0, (
        f"{paper_id} materialize failed:\n{materialize.stderr}\n{materialize.stdout}"
    )
    return subprocess.run(
        [
            sys.executable,
            str(PDF_INGESTION / "audit_staging.py"),
            str(staging),
            "--repo-root",
            str(repo_root),
        ],
        capture_output=True,
        text=True,
    )


@pytest.fixture()
def isolated_repo(tmp_path: Path) -> Path:
    (tmp_path / ".codex").symlink_to(ROOT / ".codex", target_is_directory=True)
    (tmp_path / "question-bank.yaml").write_text(
        "schema: math_topic_question_bank/v1\n", encoding="utf-8"
    )
    return tmp_path


def test_same_question_docx_pdf_semantics_and_full_pipeline(
    isolated_repo: Path,
) -> None:
    docx_archive, pdf_archive = _draw_sources(isolated_repo)
    docx_text, docx_images = _docx_bundles(isolated_repo, docx_archive)
    pdf_text, pdf_images = _pdf_bundles(isolated_repo, pdf_archive)

    # First convergence boundary: both provider-specific text adapters emit
    # exactly the same source-independent question semantics.
    assert _semantic_transcription(docx_text) == _semantic_transcription(pdf_text)

    docx_draft, docx_report = assemble(docx_text, docx_images)
    pdf_draft, pdf_report = assemble(pdf_text, pdf_images)
    assert docx_draft is not None, docx_report.errors
    assert pdf_draft is not None, pdf_report.errors
    assert docx_report.accepted_attributions == 1
    assert pdf_report.accepted_attributions == 1

    # Second convergence boundary: after the explicitly source-specific fields
    # are removed, the shared assembler's semantic output is byte-for-byte
    # equivalent, including one prompt image role on each track.
    assert _semantic_draft(docx_draft) == _semantic_draft(pdf_draft)

    docx_audit = _run_downstream(
        isolated_repo, docx_draft, docx_track=True
    )
    pdf_audit = _run_downstream(
        isolated_repo, pdf_draft, docx_track=False
    )
    assert docx_audit.returncode == 0, (
        f"DOCX audit failed:\n{docx_audit.stderr}\n{docx_audit.stdout}"
    )
    assert pdf_audit.returncode == 0, (
        f"PDF audit failed:\n{pdf_audit.stderr}\n{pdf_audit.stdout}"
    )
    assert "STAGING VALID" in docx_audit.stdout
    assert "STAGING VALID" in pdf_audit.stdout

    # The two different crop strategies materialize identical prompt pixels.
    docx_prompt = (
        isolated_repo
        / "staging/P4-SAME-QUESTION-DOCX/items/Q001/assets/prompt-01.png"
    )
    pdf_prompt = (
        isolated_repo
        / "staging/P4-SAME-QUESTION-PDF/items/Q001/assets/prompt-01.png"
    )
    assert docx_prompt.read_bytes() == pdf_prompt.read_bytes()
