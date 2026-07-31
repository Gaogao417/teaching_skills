"""Deterministic per-run directory layout (architecture §3.7, §6, M6).

Run layout (under the gitignored repo-root ``build/``)::

    build/question-ingestion/<paper-id>/<run-id>/
        run-manifest.yaml
        source/source-ref.yaml
        pages/page-NNN.txt + page-NNN.extract.yaml
        structured/{transcription,image-attribution,paper.source,paper.draft}.yaml
        review/{review-issues,review-resolutions}.yaml
        reports/{assembly,audit,trace-summary}.yaml
        cache/provider-results/

Split out of :mod:`.artifact_store` (M6) so the layout contract has its own home. The
paths and ``ensure()`` semantics are byte-identical to the pre-split implementation;
the artifact store consumes a :class:`RunLayout` unchanged.
"""

from __future__ import annotations

from pathlib import Path


__all__ = ["RunLayout"]


class RunLayout:
    """Deterministic per-run directory layout (architecture §6).

    All paths are relative to ``build_root`` (default repo-root ``build/``). The
    layout is created lazily; tests may point ``build_root`` at a tmp_path.
    """

    def __init__(
        self, build_root: Path | str, paper_id: str, run_id: str
    ) -> None:
        self.build_root = Path(build_root)
        self.paper_id = paper_id
        self.run_id = run_id
        self.root = self.build_root / "question-ingestion" / paper_id / run_id

    # -- subdirectories ----------------------------------------------------- #
    @property
    def source_dir(self) -> Path:
        return self.root / "source"

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"

    @property
    def structured_dir(self) -> Path:
        return self.root / "structured"

    @property
    def review_dir(self) -> Path:
        return self.root / "review"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache" / "provider-results"

    @property
    def manifest_path(self) -> Path:
        return self.root / "run-manifest.yaml"

    # -- known artifact paths ---------------------------------------------- #
    @property
    def page_text_path_template(self) -> str:
        return "page-{n:03d}.txt"

    def page_text_path(self, page_number: int) -> Path:
        return self.pages_dir / f"page-{page_number:03d}.txt"

    def page_sidecar_path(self, page_number: int) -> Path:
        return self.pages_dir / f"page-{page_number:03d}.extract.yaml"

    @property
    def transcription_path(self) -> Path:
        return self.structured_dir / "transcription.yaml"

    @property
    def image_attribution_path(self) -> Path:
        return self.structured_dir / "image-attribution.yaml"

    @property
    def source_paper_path(self) -> Path:
        return self.structured_dir / "paper.source.yaml"

    @property
    def draft_path(self) -> Path:
        return self.structured_dir / "paper.draft.yaml"

    @property
    def review_issues_path(self) -> Path:
        return self.review_dir / "review-issues.yaml"

    @property
    def review_resolutions_path(self) -> Path:
        return self.review_dir / "review-resolutions.yaml"

    @property
    def assembly_report_path(self) -> Path:
        return self.reports_dir / "assembly-report.yaml"

    @property
    def audit_report_path(self) -> Path:
        return self.reports_dir / "audit-report.yaml"

    @property
    def trace_summary_path(self) -> Path:
        return self.reports_dir / "trace-summary.yaml"

    def ensure(self) -> "RunLayout":
        """Create all subdirectories (idempotent)."""
        for d in (
            self.source_dir,
            self.pages_dir,
            self.structured_dir,
            self.review_dir,
            self.reports_dir,
            self.cache_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self
