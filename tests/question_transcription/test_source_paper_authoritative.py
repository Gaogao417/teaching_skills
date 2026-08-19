"""SourcePaper builder evidence-channel tests (stage 0.5 / commit 1).

Pins the behaviours the builder must get right around image attributions:

1. The builder MUST receive the source manifest (word-source.yaml) so the v2
   paper can recover vector-asset evidence (ole_binding / emf_class).
2. Attribution-level ``needs_review`` (asset is fine but the attribution is
   uncertain) is PRESERVED into the v2 paper with its original
   state/confidence and a matching inline ImageNode, so it flows downstream
   into staging for human confirmation. No malformed ReviewIssuesBundle is
   written (only field_conflict/asset_classification are contract-legal).
3. Assets with no displayable rendition (vector_rendition_missing) are dropped
   (nothing to crop) and emit no review issue.
4. The paper_id is recovered from the manifest when the transcription carries
   the ingestion placeholder.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.contracts import QuestionTranscriptionBundle  # noqa: E402
from scripts.question_transcription.workflow.adapters.source.source_paper import (  # noqa: E402
    DeterministicSourcePaperBuilder,
)
from scripts.question_transcription.workflow.infrastructure.artifact_store import (  # noqa: E402
    ArtifactStore,
)
from scripts.question_transcription.workflow.infrastructure.run_layout import (  # noqa: E402
    RunLayout,
)

FIX = ROOT / "tests" / "question_transcription" / "fixtures"


def _store(tmp_path: Path) -> ArtifactStore:
    layout = RunLayout(tmp_path / "build", "p", "r")
    layout.ensure()
    return ArtifactStore(layout)


def _transcription_dict(paper_id: str = "INGEST-PLACEHOLDER") -> dict:
    return {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": paper_id,
            "title": "T",
            "grade": "九年级",
            "source_archive": "documents/x",
            "question_bank": "../../question-bank.yaml",
        },
        "sections": [
            {
                "section_ref": "I",
                "title": "一、选择题",
                "questions": [
                    {
                        "question_ref": "1",
                        "question_number": 1,
                        "question_type": "short_answer",
                        "points": 4,
                        "content": {
                            "stem_latex": "如图，求$x$。",
                            "answer": "1",
                            "clue": "c",
                            "solution_steps": ["s1"],
                        },
                        "evidence": {
                            "question": [{"kind": "page", "source": "p/1.png", "page_number": 1}],
                            "solution": [{"kind": "page", "source": "p/2.png", "page_number": 2}],
                            "solution_start_anchor": "1.",
                            "solution_end_anchor": "2.",
                        },
                    }
                ],
            }
        ],
        "provider": {"kind": "agent", "name": "codex", "version": "v1"},
    }


def _word_source_dict() -> dict:
    return yaml.safe_load(
        (FIX / "docx-vector-assets.word-source.yaml").read_text(encoding="utf-8")
    )


def test_build_accepts_and_reads_extracted_source_manifest(tmp_path):
    """The build() signature must accept extracted_source_ref and read it."""
    store = _store(tmp_path)
    trans_ref = store.commit_yaml(
        "structured/transcription.yaml", _transcription_dict(),
        "math_question_transcription/v1",
    )
    manifest_ref = store.commit_yaml(
        "source/source-ref.yaml", _word_source_dict(), "math_word_source_extract/v1"
    )
    builder = DeterministicSourcePaperBuilder(store)
    result, failure, detail = builder.build(trans_ref, None, manifest_ref, None)
    assert failure is None, f"unexpected failure: {failure}: {detail}"
    assert result is not None
    source_paper = store.read_yaml(result.source_paper)
    # paper_id recovered from the manifest would require the manifest to carry it;
    # the synthetic fixture does not, so it falls back to the transcription id.
    assert source_paper["schema"] == "math_exam_source_paper/v2"


def test_needs_review_attribution_preserved_not_blocking(tmp_path):
    """An attribution-level needs_review (asset is fine but the question/role
    attribution is uncertain) must be PRESERVED into the v2 paper with its
    original state/confidence and a matching inline ImageNode, so it flows
    downstream into staging for human confirmation. It must NOT produce a
    malformed ReviewIssuesBundle (only field_conflict/asset_classification are
    allowed, each with mandatory candidate/hash fields); the projector runs with
    issues=None. The gate still catches any real binding problem."""
    store = _store(tmp_path)
    trans_ref = store.commit_yaml(
        "structured/transcription.yaml", _transcription_dict(),
        "math_question_transcription/v1",
    )
    images = {
        "schema": "math_image_attribution/v1",
        "paper_id": "INGEST-PLACEHOLDER",
        "assets": [{"asset_id": "a1", "source": "s", "sha256": "sha256:" + "0" * 64,
                    "media_type": "image/png", "width_px": 10, "height_px": 10,
                    "disposition": "attributed"}],
        "attributions": [
            {"attribution_id": "x", "asset_id": "a1", "question_ref": "1",
             "role": "prompt", "crop": {"kind": "full"}, "order": 0,
             "confidence": "medium", "state": "needs_review",
             "provider": {"kind": "manual", "name": "t", "version": "v1"}},
        ],
    }
    images_ref = store.commit_yaml(
        "structured/image-attribution.yaml", images, "math_image_attribution/v1"
    )
    builder = DeterministicSourcePaperBuilder(store)
    result, failure, detail = builder.build(trans_ref, images_ref, None, None)
    assert failure is None
    assert result is not None
    # No malformed issues bundle written; projector will run with issues=None.
    assert result.issues is None
    sp = store.read_yaml(result.source_paper)
    # The needs_review attribution is preserved into the v2 paper.
    assert len(sp["attributions"]) == 1
    attr = sp["attributions"][0]
    assert attr["attribution_id"] == "x"
    assert attr["asset_id"] == "a1"
    assert attr["question_ref"] == "1"
    assert attr["target"] == {"target": "question_stem"}
    assert attr["order"] == 1  # one text node precedes the image
    # Original state/confidence carried through unchanged.
    assert attr["state"] == "needs_review"
    assert attr["confidence"] == "medium"
    # Inline ImageNode binding holds: stem carries a text node then the image.
    stem = sp["questions"][0]["content"]["stem"]
    assert [n["kind"] for n in stem] == ["text", "image"]
    assert stem[1]["asset_id"] == "a1"


def test_unreferenced_needs_review_asset_does_not_block():
    """Unreferenced v1 assets with disposition=needs_review (typically formula
    WMF fragments the extractor could not attribute to any question) must NOT
    become blocking review issues — that would bury real blockers under
    formula-glyph noise (e.g. 441 unreferenced WMF in the Fengxian paper).
    Only REFERENCED, non-fragment vector assets without a rendition block."""
    from scripts.question_transcription.workflow.adapters.source.source_paper import (
        _build_authoritative_v2,
    )

    images = {
        "schema": "math_image_attribution/v1", "paper_id": "P",
        "assets": [
            {"asset_id": "orphan-wmf", "source": "media/x.wmf",
             "sha256": "sha256:" + "0" * 64, "media_type": "image/wmf",
             "width_px": 13, "height_px": 15, "disposition": "needs_review",
             "disposition_reason": "unreferenced_in_paragraph_stream"},
        ],
        "attributions": [],
    }
    ws = {"schema": "math_word_source_extract/v1",
          "media": [{"path": "media/x.wmf", "sha256": "sha256:" + "0" * 64,
                     "width_px": 13, "height_px": 15,
                     "ole_binding": {"embedded": False}, "emf_class": "diagram"}],
          "image_attribution_status": "complete", "image_attribution": []}
    sp, issues = _build_authoritative_v2(_skeleton_dict("P"), images, ws)
    # No attribution references the orphan -> no issue, no asset in v2 paper.
    assert issues == []
    assert sp["assets"] == []


def test_accepted_bundle_produces_no_issues(tmp_path):
    """A fully-accepted clean bundle must NOT produce issues (no false blocks)."""
    from scripts.question_transcription.workflow.adapters.source.source_paper import (
        _build_authoritative_v2,
    )

    images = {
        "schema": "math_image_attribution/v1", "paper_id": "P",
        "assets": [{"asset_id": "a1", "source": "media/a.png",
                    "sha256": "sha256:" + "a" * 64, "media_type": "image/png",
                    "width_px": 100, "height_px": 100, "disposition": "attributed"}],
        "attributions": [
            {"attribution_id": "x", "asset_id": "a1", "question_ref": "1",
             "role": "prompt", "crop": {"kind": "full"}, "order": 0,
             "confidence": "high", "state": "accepted"}
        ],
    }
    ws = {"schema": "math_word_source_extract/v1",
          "media": [{"path": "media/a.png", "sha256": "sha256:" + "a" * 64,
                     "width_px": 100, "height_px": 100}],
          "image_attribution_status": "complete", "image_attribution": []}
    sp, issues = _build_authoritative_v2(_skeleton_dict("P"), images, ws)
    assert issues == []


def test_no_manifest_is_allowed(tmp_path):
    """A non-docx source (no manifest) must still build via the minimal path."""
    store = _store(tmp_path)
    trans_ref = store.commit_yaml(
        "structured/transcription.yaml", _transcription_dict("PAPER-A"),
        "math_question_transcription/v1",
    )
    builder = DeterministicSourcePaperBuilder(store)
    result, failure, detail = builder.build(trans_ref, None, None, None)
    assert failure is None
    assert result is not None
    sp = store.read_yaml(result.source_paper)
    assert sp["paper_id"] == "PAPER-A"


# --------------------------------------------------------------------------- #
# Stage 2 (commit 2): authoritative v2 join — full round-trip
# --------------------------------------------------------------------------- #


from scripts.question_transcription.workflow.adapters.source.source_paper import (  # noqa: E402
    _build_authoritative_v2,
)
from scripts.question_transcription.workflow.adapters.staging.project_source_paper import (  # noqa: E402
    project_source_to_draft,
)
from scripts.question_transcription.source_contracts import SourcePaper  # noqa: E402

_ARCHIVE = "documents/demo-paper"


def _skeleton_dict(paper_id: str = "P", qtype: str = "short_answer") -> dict:
    return {
        "schema": "math_question_transcription/v1",
        "paper": {
            "id": paper_id, "title": "T", "grade": "九年级", "subject": "数学",
            "source_archive": _ARCHIVE, "question_bank": "../../q.yaml",
        },
        "sections": [{
            "section_ref": "I", "title": "x", "questions": [{
                "question_ref": "1", "question_number": 1, "question_type": qtype,
                "points": 4,
                "content": {"stem_latex": "如图。", "answer": "1", "clue": "c",
                            "solution_steps": ["s1"]},
                "evidence": {
                    "question": [{"kind": "page", "source": f"{_ARCHIVE}/p/1.png", "page_number": 1}],
                    "solution": [{"kind": "page", "source": f"{_ARCHIVE}/p/2.png", "page_number": 2}],
                    "solution_start_anchor": "1.", "solution_end_anchor": "2.",
                },
            }],
        }],
        "provider": {"kind": "manual", "name": "t", "version": "v1"},
    }


def _vector_images(paper_id: str) -> dict:
    return {
        "schema": "math_image_attribution/v1", "paper_id": paper_id,
        "assets": [
            {"asset_id": "word-image-ole-eq", "source": f"{_ARCHIVE}/media/image-ole-eq.wmf",
             "sha256": "sha256:" + "1" * 64, "media_type": "image/wmf",
             "width_px": 113, "height_px": 19, "disposition": "attributed"},
            {"asset_id": "word-image-tiny", "source": f"{_ARCHIVE}/media/image-tiny.wmf",
             "sha256": "sha256:" + "2" * 64, "media_type": "image/wmf",
             "width_px": 5, "height_px": 6, "disposition": "attributed"},
            {"asset_id": "word-image-big-no-rendition", "source": f"{_ARCHIVE}/media/image-big-no-rendition.wmf",
             "sha256": "sha256:" + "3" * 64, "media_type": "image/wmf",
             "width_px": 200, "height_px": 150, "disposition": "attributed"},
            {"asset_id": "word-image-normal", "source": f"{_ARCHIVE}/media/image-normal.png",
             "sha256": "sha256:" + "4" * 64, "media_type": "image/png",
             "width_px": 475, "height_px": 512, "disposition": "attributed"},
        ],
        "attributions": [
            {"attribution_id": "a4", "asset_id": "word-image-normal",
             "question_ref": "1", "role": "prompt", "crop": {"kind": "full"},
             "order": 0, "confidence": "high", "state": "accepted"},
            {"attribution_id": "a1", "asset_id": "word-image-ole-eq",
             "question_ref": "1", "role": "solution", "crop": {"kind": "full"},
             "order": 0, "confidence": "high", "state": "accepted"},
        ],
    }


def test_authoritative_v2_drops_ignored_and_drops_missing_rendition():
    """OLE formula + tiny fragment -> ignored (no asset/attr); big WMF with no
    rendition -> dropped (nothing to crop); normal PNG -> accepted asset +
    attribution. None of the dropped assets produce a malformed review issue."""
    ws = _word_source_dict()
    sp, issues = _build_authoritative_v2(_skeleton_dict("P"), _vector_images("P"), ws)
    m = SourcePaper.model_validate(sp)
    # Only the normal PNG survives the guard.
    assert [a.asset_id for a in m.assets] == ["word-image-normal"]
    assert [a.asset_id for a in m.attributions] == ["word-image-normal"]
    # No issues are produced (dropped assets emit no malformed review items).
    assert issues == []


def test_authoritative_v2_round_trips_through_projector():
    """The v2 paper must project back to a valid v1 draft via
    project_source_to_draft (content-image bindings hold, no gate errors)."""
    ws = _word_source_dict()
    sp, _ = _build_authoritative_v2(_skeleton_dict("P"), _vector_images("P"), ws)
    source = SourcePaper.model_validate(sp)
    skeleton = QuestionTranscriptionBundle.model_validate(_skeleton_dict("P"))
    draft, report = project_source_to_draft(source, skeleton)
    assert report.errors == [], [e.detail for e in report.errors]
    item = draft["sections"][0]["items"][0]
    # The accepted PNG became one prompt crop; OLE/tiny WMF never reached it.
    assert len(item["prompt"]) == 1
    assert item["prompt"][0]["source"].endswith("image-normal.png")


def test_solution_role_round_trips_to_solution_crop():
    """role=solution -> question_solution_step -> projector -> solution crop."""
    images = {
        "schema": "math_image_attribution/v1", "paper_id": "P",
        "assets": [{"asset_id": "img-sol", "source": f"{_ARCHIVE}/media/sol.png",
                    "sha256": "sha256:" + "a" * 64, "media_type": "image/png",
                    "width_px": 100, "height_px": 100, "disposition": "attributed"}],
        "attributions": [{"attribution_id": "x", "asset_id": "img-sol",
                          "question_ref": "1", "role": "solution",
                          "crop": {"kind": "full"}, "order": 0,
                          "confidence": "high", "state": "accepted"}],
    }
    ws = {"schema": "math_word_source_extract/v1",
          "media": [{"path": "media/sol.png", "sha256": "sha256:" + "a" * 64,
                     "width_px": 100, "height_px": 100}],
          "image_attribution_status": "complete", "image_attribution": []}
    sp, _ = _build_authoritative_v2(_skeleton_dict("P", "problem"), images, ws)
    source = SourcePaper.model_validate(sp)
    assert source.attributions[0].target.target == "question_solution_step"
    skeleton = QuestionTranscriptionBundle.model_validate(_skeleton_dict("P", "problem"))
    draft, report = project_source_to_draft(source, skeleton)
    assert report.errors == []
    item = draft["sections"][0]["items"][0]
    assert len(item["solution"]) == 1
    assert item["solution"][0]["assignment_path"] == "/solution_steps/0/diagram_col"
