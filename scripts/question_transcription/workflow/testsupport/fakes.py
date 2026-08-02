"""Offline fake adapters implementing every workflow port.

Used by the graph lifecycle tests (E1-E7) and as the default for unit tests. Real
model/script adapters are bound by :mod:`..composition` for live runs; these fakes
implement the same Protocols so node code is identical.

The fakes are configurable per-run (page text content, transcription payload,
failure injection) via a :class:`FakeScenario`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..contracts import (
    ArtifactRef,
    ExecutionProvenance,
    ExtractedSource,
    ImageAttributionResult,
    PageTextArtifact,
    PageTextExtract,
    PageTextFailure,
    PageTextJob,
    SourceBuildResult,
    SourceInput,
    WholePaperFailure,
    WholePaperTranscription,
)
from ..ports.staging import StageFailure
from ..ports.review import FinalReviewStatus
from ..ports.source import SourceExtractionError


__all__ = ["FakeScenario", "FakeSourceExtractor", "FakePageTextExtractor",
           "FakeWholePaperTranscriber", "FakeImageAttribution",
           "FakeSourcePaperBuilder", "FakeDraftProjector", "FakeEvidenceCompleter",
           "FakeStagingExpander", "FakeAssetMaterializer", "FakeStagingAuditor",
           "FakeCatalogNotifier", "FakeFinalReviewReader", "build_fake_deps"]


@dataclass
class FakeScenario:
    """Controls fake behaviour for a test run."""

    page_count: int = 2
    page_text_factory: Callable[[int], str] = field(
        default_factory=lambda: (lambda n: f"page {n} text content")
    )
    # injectable failures
    page_failure_pages: set[int] = field(default_factory=set)
    transcription_payload: dict[str, Any] | None = None
    transcription_failure_kind: str | None = None
    source_has_issues: bool = False
    final_review_status: FinalReviewStatus = "approved"
    draft_fail: bool = False
    audit_fail: bool = False


def _ref(name: str) -> ArtifactRef:
    return ArtifactRef(
        path=name, sha256="sha256:" + "0" * 64, schema="fake"
    )


class FakeSourceExtractor:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def extract(self, source: SourceInput):
        layout = self.store.layout
        layout.ensure()
        pages = []
        for i in range(self.scenario.page_count):
            ref = self.store.commit_text(
                f"source/page-{i+1:03d}.png.placeholder",
                f"<page {i+1} bytes>",
                "image/png",
            )
            pages.append(ref)
        manifest = self.store.commit_yaml(
            "source/source-ref.yaml",
            {"schema": "fake-source/v1", "paper_id": source.paper_id, "pages": len(pages)},
            "fake-source/v1",
        )
        return (
            ExtractedSource(
                manifest=manifest,
                pages=pages,
                source_sha256="sha256:" + "0" * 64,
            ),
            None,
            None,
        )


class FakePageTextExtractor:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def extract(self, job: PageTextJob):
        if job.page_number in self.scenario.page_failure_pages:
            return None, PageTextFailure(
                adapter_id="fake",
                kind="invalid_response",
                attempts=3,
                detail=f"injected failure for page {job.page_number}",
            )
        text = self.scenario.page_text_factory(job.page_number)
        text_ref = self.store.commit_text(
            f"pages/page-{job.page_number:03d}.txt", text, "text/plain"
        )
        side_ref = self.store.commit_yaml(
            f"pages/page-{job.page_number:03d}.extract.yaml",
            {"page_number": job.page_number, "provider": "fake"},
            "page-text-extract/v1",
        )
        return (
            PageTextExtract(
                artifact=PageTextArtifact(
                    page_number=job.page_number,
                    text=text_ref,
                    metadata=side_ref,
                    provenance=ExecutionProvenance(
                        adapter_id="fake", model="fake-ocr", prompt_version="v1"
                    ),
                )
            ),
            None,
        )


def _fake_prompt_version() -> str:
    """Mirror the real prompt version so the fake's provenance stays in sync."""
    from ..prompts.whole_paper import WHOLE_PAPER_PROMPT_VERSION

    return WHOLE_PAPER_PROMPT_VERSION


class FakeWholePaperTranscriber:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def transcribe(self, request):
        if self.scenario.transcription_failure_kind:
            return None, WholePaperFailure(
                adapter_id="fake",
                kind=self.scenario.transcription_failure_kind,
                attempts=1,
                detail="injected whole-paper failure",
            )
        payload = self.scenario.transcription_payload or {
            "schema": "math_question_transcription/v1",
            "paper": {"id": request.paper_id, "title": "fake", "grade": "初三",
                      "source_archive": "fake"},
            "sections": [],
            "provider": {"kind": "agent", "name": "fake", "version": "v1"},
        }
        import yaml as _yaml

        ref = self.store.commit_text(
            "structured/transcription.yaml",
            _yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
            "math_question_transcription/v1",
        )
        return (
            WholePaperTranscription(
                transcription=ref,
                issues=None,
                execution_id="fake-exec-1",
                model="fake-glm",
                prompt_version=_fake_prompt_version(),
            ),
            None,
        )

    def repair_structured_output(self, previous_execution_id, validation_errors):
        return self.transcribe(_DummyRequest())


class _DummyRequest:
    paper_id = "fake"


class FakeImageAttribution:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def attribute(self, extracted_source):
        ref = self.store.commit_yaml(
            "structured/image-attribution.yaml",
            {"schema": "math_image_attribution/v1", "paper_id": "fake",
             "assets": [], "attributions": []},
            "math_image_attribution/v1",
        )
        return ref, "complete", None, None


class FakeSourcePaperBuilder:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def build(self, transcription_ref, images_ref, extracted_source_ref, resolutions_ref):
        import yaml as _yaml

        source = {
            "schema": "math_exam_source_paper/v2",
            "paper_id": "fake",
            "questions": [
                {
                    "question_ref": "1",
                    "question_number": 1,
                    "question_type": "problem",
                    "points": 10,
                    "content": {
                        "stem": [{"kind": "text", "text": "fake stem"}],
                        "answer": "1",
                        "clue": "clue",
                        "solution_steps": [
                            {"step_id": "1", "content": [{"kind": "text", "text": "step"}]}
                        ],
                    },
                }
            ],
        }
        ref = self.store.commit_yaml(
            "structured/paper.source.yaml", source, "math_exam_source_paper/v2"
        )
        issues = None
        if self.scenario.source_has_issues and resolutions_ref is None:
            issues = self.store.commit_yaml(
                "review/review-issues.yaml",
                {"schema": "math_transcription_review_issues/v1", "paper_id": "fake",
                 "issues": []},
                "math_transcription_review_issues/v1",
            )
        return SourceBuildResult(source_paper=ref, issues=issues), None, None


class FakeDraftProjector:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def project(self, source_paper_ref):
        if self.scenario.draft_fail:
            return None, "project_failed", "injected"
        ref = self.store.commit_yaml(
            "structured/paper.draft.yaml",
            {"schema": "math_exam_staging_draft/v1", "paper_id": "fake", "sections": []},
            "math_exam_staging_draft/v1",
        )
        return ref, None, None


class FakeEvidenceCompleter:
    def __init__(self, store) -> None:
        self.store = store

    def complete(self, draft_ref, source_kind, layout=None, layout_override_seeds=False):
        return draft_ref, None, None


class FakeStagingExpander:
    def __init__(self, store) -> None:
        self.store = store

    def expand(self, draft_ref):
        staging = str(self.store.layout.root / "staging")
        Path(staging).mkdir(parents=True, exist_ok=True)
        return staging, None, None


class FakeAssetMaterializer:
    def __init__(self, store) -> None:
        self.store = store

    def materialize(self, staging_directory):
        return _ref("reports/materialize.yaml"), None, None


class FakeStagingAuditor:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def audit(self, staging_directory, require_approved_review):
        if self.scenario.audit_fail:
            return None, "audit_failed", "injected"
        return _ref("reports/audit-report.yaml"), None, None


class FakeCatalogNotifier:
    def __init__(self, store) -> None:
        self.store = store

    def refresh(self, staging_directory):
        return None, None, None


class FakeFinalReviewReader:
    def __init__(self, store, scenario: FakeScenario) -> None:
        self.store = store
        self.scenario = scenario

    def read_status(self, staging_directory):
        return self.scenario.final_review_status, None, None, []


def build_fake_deps(store, scenario: FakeScenario | None = None):
    """Assemble :class:`WorkflowDependencies` entirely from offline fakes."""

    from ..bootstrap.dependencies import DeterministicPorts, WorkflowDependencies

    sc = scenario or FakeScenario()
    deterministic = DeterministicPorts(
        source_extractor=FakeSourceExtractor(store, sc),
        source_paper_builder=FakeSourcePaperBuilder(store, sc),
        image_attribution=FakeImageAttribution(store, sc),
        draft_projector=FakeDraftProjector(store, sc),
        evidence_completer=FakeEvidenceCompleter(store),
        staging_expander=FakeStagingExpander(store),
        asset_materializer=FakeAssetMaterializer(store),
        staging_auditor=FakeStagingAuditor(store, sc),
        catalog_notifier=FakeCatalogNotifier(store),
        final_review_reader=FakeFinalReviewReader(store, sc),
    )
    return WorkflowDependencies(
        run_layout=store.layout,
        artifact_store=store,
        trace_sink=None,  # filled by caller; nodes tolerate None via the context manager
        page_text_extractor=FakePageTextExtractor(store, sc),
        whole_paper_transcriber=FakeWholePaperTranscriber(store, sc),
        deterministic=deterministic,
        whole_paper_max_repairs=2,
    )
