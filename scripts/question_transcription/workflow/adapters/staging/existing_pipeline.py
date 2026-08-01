"""Current staging-pipeline wrappers (architecture §8.1).

Wraps the existing deterministic functions, importing them directly (not via CLI,
so we get exceptions instead of ``SystemExit``). Each returns the
``(result, failure, detail)`` triple the nodes expect.

- :class:`DeterministicDraftProjector` — :func:`assemble_paper_draft.assemble`
  produces the v1 ``paper.draft.yaml`` the rest of the pipeline consumes.
- :class:`DeterministicStagingExpander` — :func:`expand_staging_draft.expand_draft`
- :class:`DeterministicAssetMaterializer` — :func:`materialize_staging.materialize_item` loop
- :class:`DeterministicStagingAuditor` — :func:`audit_staging` (via subprocess for the
  ``--require-approved-review`` gate, since it needs sys.path surgery)
- :class:`DeterministicCatalogNotifier` — :func:`notify_catalog_version.bump_version_file`
- :class:`DeterministicEvidenceCompleter` — no-op for now (Word evidence is DOCX-specific)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .._common_paths import repo_root  # noqa: F401
from ...contracts import ArtifactRef
from ...ports.staging import StageFailure


__all__ = [
    "DeterministicDraftProjector",
    "DeterministicEvidenceCompleter",
    "DeterministicStagingExpander",
    "DeterministicAssetMaterializer",
    "DeterministicStagingAuditor",
    "DeterministicCatalogNotifier",
]


def _skill_scripts(*names: str) -> None:
    root = repo_root()
    for n in names:
        p = root / ".codex/skills" / n / "scripts"
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


class DeterministicDraftProjector:
    """Project the authoritative v2 source paper to the v1-compatible draft.

    Consumes the v2 ``SourcePaper`` (the authoritative image record produced by
    :class:`DeterministicSourcePaperBuilder`) via ``project_source_to_draft``,
    instead of re-deriving a draft from the v1 transcription + image bundles.
    The v1 bundles are a frozen compatibility contract that cannot carry
    ``emf_class`` / ``ole_binding`` / ``rendition``; only the v2 paper has the
    vector-asset classification that prevents raw WMF bytes from reaching the
    materializer.
    """

    def __init__(self, store) -> None:
        self.store = store

    def project(self, source_paper_ref):
        try:
            from scripts.question_transcription.project_source_paper import (
                project_source_to_draft,
            )
            from scripts.question_transcription.source_contracts import SourcePaper
            from scripts.question_transcription.contracts import (
                QuestionTranscriptionBundle,
            )
            from scripts.question_transcription.review_issue_contracts import (
                ReviewIssuesBundle, ReviewResolutionsBundle,
            )
            import yaml as _yaml

            source = SourcePaper.model_validate(
                self.store.read_yaml(_as_ref(source_paper_ref))
            )
            # The projector needs the transcription skeleton for the question_ref
            # join (paper_id + section/question structure + evidence). The builder
            # consumed the same skeleton when building the v2 paper.
            trans_path = self.store.layout.transcription_path
            if not trans_path.exists():
                return None, "project_failed", "transcription artifact missing"
            skeleton = QuestionTranscriptionBundle.model_validate(
                _yaml.safe_load(trans_path.read_text(encoding="utf-8"))
            )
            # Optional review issues / resolutions: the gate (inside
            # project_source_to_draft) blocks when blocking issues are unresolved.
            issues = None
            issues_path = self.store.layout.review_dir / "review-issues.yaml"
            if issues_path.exists():
                issues = ReviewIssuesBundle.model_validate(
                    _yaml.safe_load(issues_path.read_text(encoding="utf-8"))
                )
            resolutions = None
            res_path = self.store.layout.review_resolutions_path
            if res_path.exists():
                resolutions = ReviewResolutionsBundle.model_validate(
                    _yaml.safe_load(res_path.read_text(encoding="utf-8"))
                )
            draft, report = project_source_to_draft(
                source, skeleton, issues, resolutions
            )
            if report.errors:
                return None, "project_failed", "; ".join(e.detail for e in report.errors)
            # Resolve multi-image placements: a role with several images would
            # otherwise trip the expander's "every crop needs assignment_path"
            # check. The planner composes such groups into one PNG and stamps an
            # assignment_path, so the committed draft is expander-ready.
            from scripts.question_transcription.materialize_image_group import (
                resolve_placement_decisions,
            )
            resolve_placement_decisions(draft, repo_root())
            draft_ref = self.store.commit_yaml(
                "structured/paper.draft.yaml", draft, "math_exam_staging_draft/v1"
            )
            return draft_ref, None, None
        except Exception as exc:
            return None, "project_failed", f"{type(exc).__name__}: {exc}"


class DeterministicEvidenceCompleter:
    """Evidence completion (Word evidence is DOCX-specific; PDF is page-based).

    For the first milestone this is a passthrough — the assembler already attaches
    page evidence from the transcription. DOCX word-evidence enrichment is layered in
    when the DOCX skill's ``word_evidence_pages`` is wired.
    """

    def __init__(self, store) -> None:
        self.store = store

    def complete(self, draft_ref, source_kind):
        return draft_ref, None, None


class DeterministicStagingExpander:
    """Expand the draft into per-question staging directories."""

    def __init__(self, store) -> None:
        self.store = store

    def expand(self, draft_ref):
        try:
            _skill_scripts("math-pdf-question-bank-ingestion")
            from expand_staging_draft import expand_draft  # type: ignore

            draft_path = self.store.layout.root / draft_ref.path
            staging_dir = expand_draft(draft_path)
            return str(staging_dir), None, None
        except Exception as exc:
            return None, "expand_failed", f"{type(exc).__name__}: {exc}"


class DeterministicAssetMaterializer:
    """Crop images, refresh hashes, derive student/teacher assignments."""

    def __init__(self, store) -> None:
        self.store = store

    def materialize(self, staging_directory):
        try:
            _skill_scripts("math-pdf-question-bank-ingestion", "math-topic-question-bank")
            from materialize_staging import item_ids, materialize_item  # type: ignore

            root = repo_root()
            staging = Path(staging_directory)
            ids = item_ids(staging, only=set())
            for item_id in ids:
                materialize_item(staging / "items" / item_id, root)
            return ArtifactRef(
                path="reports/materialize.yaml",
                sha256="sha256:" + "0" * 64,
                schema="materialize-report/v1",
            ), None, None
        except Exception as exc:
            return None, "materialize_failed", f"{type(exc).__name__}: {exc}"


class DeterministicStagingAuditor:
    """Audit staging via the CLI (sys.path surgery is owned by the script)."""

    def __init__(self, store) -> None:
        self.store = store

    def audit(self, staging_directory, require_approved_review):
        try:
            root = repo_root()
            venv_py = root / ".venv/bin/python"
            script = root / ".codex/skills/math-pdf-question-bank-ingestion/scripts/audit_staging.py"
            cmd = [str(venv_py), str(script), str(staging_directory), "--repo-root", str(root)]
            if require_approved_review:
                cmd.append("--require-approved-review")
            proc = subprocess.run(
                cmd, capture_output=True, text=True, cwd=str(root), timeout=300
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()[:1000]
                return None, "audit_failed", detail
            return ArtifactRef(
                path="reports/audit-report.yaml",
                sha256="sha256:" + "0" * 64,
                schema="audit-report/v1",
            ), None, None
        except subprocess.TimeoutExpired as exc:
            return None, "audit_failed", f"timeout: {exc}"
        except Exception as exc:
            return None, "audit_failed", f"{type(exc).__name__}: {exc}"


class DeterministicCatalogNotifier:
    """Bump ``.catalog-version`` so the Review UI rebuilds."""

    def __init__(self, store) -> None:
        self.store = store

    def refresh(self, staging_directory):
        try:
            _skill_scripts("math-topic-question-bank")
            from notify_catalog_version import bump_version_file  # type: ignore

            bump_version_file(Path(staging_directory))
            return None, None, None
        except Exception as exc:
            return None, "notify_failed", f"{type(exc).__name__}: {exc}"


def _as_ref(value) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    return ArtifactRef.model_validate(value)
