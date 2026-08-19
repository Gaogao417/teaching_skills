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

import os
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

    def _stamp_page_plan(self, draft: dict) -> None:
        """Carry the run's non-question-page claims onto the draft paper header.

        The declaration is authored next to the original source files and frozen
        by extraction into ``source/page-plan.yaml``. The draft is the only
        hand-off the legacy staging pipeline has, so the claims travel on the
        paper header: ``expand_staging_draft`` copies them into the staging
        ``paper.yaml`` and the audit enforces them fail closed (declared pages
        are the sole exemption from whole-paper coverage).
        """
        page_plan_path = self.store.layout.source_dir / "page-plan.yaml"
        if not page_plan_path.is_file():
            return
        import yaml as _yaml

        plan = _yaml.safe_load(page_plan_path.read_text(encoding="utf-8")) or {}
        declared = plan.get("non_question_pages")
        if isinstance(declared, list) and declared:
            paper = draft.setdefault("paper", {})
            paper["non_question_pages"] = declared

    def project(self, source_paper_ref):
        try:
            from .project_source_paper import (
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
            self._stamp_page_plan(draft)
            # Resolve multi-image placements: a role with several images would
            # otherwise trip the expander's "every crop needs assignment_path"
            # check. The planner rewrites the draft to single-crop roles with a
            # deterministic composed path + box_px derived from the members. The
            # actual PNG composition happens later in the materialize step (after
            # expand creates the staging tree); the composition plan is stashed
            # on the renderer and committed as a sidecar the materializer reads.
            from .materialize_image_group import (
                resolve_placement_decisions,
            )
            resolved = resolve_placement_decisions(draft, repo_root(), staging_dir=None)
            self._group_renderer = resolved.renderer
            draft_ref = self.store.commit_yaml(
                "structured/paper.draft.yaml", draft, "math_exam_staging_draft/v1"
            )
            # Persist the composition plan so the materialize step (which runs as
            # a separate node and cannot see this renderer instance) can write
            # the composed PNGs after expand creates the staging tree.
            plan = getattr(resolved.renderer, "_last_composition_plan", None) or {}
            if plan:
                self.store.commit_yaml(
                    "structured/placement-plan.yaml",
                    {
                        "schema": "placement_plan/v1",
                        "groups": [
                            {"question_id": qid, "role": role, **entry}
                            for (qid, role), entry in plan.items()
                        ],
                    },
                    "placement_plan/v1",
                )
            return draft_ref, None, None
        except Exception as exc:
            return None, "project_failed", f"{type(exc).__name__}: {exc}"


class DeterministicEvidenceCompleter:
    """Expand DOC/DOCX seed pages into complete Word evidence ranges.

    The whole-paper transcriber records the first question/solution page for each
    item.  The DOCX ingestion contract requires the deterministic
    ``word_evidence_pages`` resolver to fill the continuous ranges *before* the
    draft is expanded.  Keeping this work in the ``complete_evidence`` adapter makes
    the graph node observable and independently regression-testable. Pre-rendered
    page-image packs (``pages``) carry page-span evidence too — the transcriber
    only ever emits page-kind refs — so they go through the same resolver, which
    also enforces the declared non-question-page exemption; region-only volumes
    are short-circuited inside the resolver itself.

    ``layout`` / ``layout_override_seeds`` carry an optional human-confirmed Word
    layout through the recover command's replay path; both default to leaving the
    resolver on its normal ``auto`` inference, so the live graph is unaffected.
    """

    def __init__(self, store) -> None:
        self.store = store

    def complete(self, draft_ref, source_kind, layout=None, layout_override_seeds=False):
        if source_kind not in ("doc", "docx", "pages"):
            return draft_ref, None, None
        try:
            _skill_scripts("math-docx-question-bank-ingestion")
            from word_evidence_pages import resolve_draft_payload  # type: ignore

            ref = _as_ref(draft_ref)
            payload = self.store.read_yaml(ref)
            # 含图题的整页题图兜底：扫描卷没有检测分支、闵行 2020 的 docx
            # 图片归属失败（question-number 断档）——两者都没有 prompt crop，
            # 但 audit 正确地要求含图题干带可视证据。已有归属 crop 的题
            # 不受影响（fallback 只补空位），审核者可在 Review UI 精裁替换。
            payload = self._attach_full_page_prompt_crops(payload)
            # ``layout`` is None for the normal graph path, which selects the
            # resolver's "auto" inference. The recover command passes an explicit
            # "interleaved"/"separated" after a human confirms the source layout,
            # paired with ``layout_override_seeds`` to repair answer-block seeds.
            resolve_layout = layout or "auto"
            updated, report = resolve_draft_payload(
                payload,
                repo_root=repo_root(),
                layout=resolve_layout,
                layout_override_seeds=layout_override_seeds,
            )
            completed_ref = self.store.commit_yaml(
                ref.path,
                updated,
                "math_exam_staging_draft/v1",
            )
            self.store.commit_yaml(
                "reports/word-evidence-report.yaml",
                {
                    "schema": "math_word_evidence_completion_report/v1",
                    **report,
                },
                "math_word_evidence_completion_report/v1",
            )
            return completed_ref, None, None
        except Exception as exc:
            return None, "evidence_failed", f"{type(exc).__name__}: {exc}"

    @staticmethod
    def _attach_full_page_prompt_crops(payload: dict) -> dict:
        """扫描卷（pages）含图题的整页题图兜底（audit 图题规则的诚实满足）。

        扫描来源没有检测分支可产出独立题图 crop，但 audit 正确地要求含图
        （如图/图所示…）题干必须带可视证据。这里把题干首个证据页整页作为
        prompt crop 附上：materialize 会把它裁成 assets/prompt-01.png 并注入
        teacher/student 的题图位，审核者可在 Review UI 里进一步手工替换精裁。
        不放松 audit 规则本身。
        """
        import re as _re

        from PIL import Image as _Image

        figure_reference = _re.compile(r"如图|图所示|下图|上图|图中|示意图")
        attached = []
        for section in payload.get("sections") or []:
            for item in section.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("prompt"):
                    continue
                stem = str((item.get("block") or {}).get("stem_latex") or "")
                if not figure_reference.search(stem):
                    continue
                entries = item.get("question_word_evidence") or []
                if not entries:
                    continue
                page_image = str(entries[0].get("page_image") or "")
                if not page_image:
                    continue
                page_path = Path(page_image)
                if not page_path.is_absolute():
                    page_path = repo_root() / page_image
                with _Image.open(page_path) as image:
                    width, height = image.size
                item["prompt"] = [
                    {
                        "source": str(page_path),
                        "box_px": [0, 0, width, height],
                    }
                ]
                attached.append(item.get("item_id"))
        return payload


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
            # Write composed group PNGs BEFORE materializing items. The projector
            # stashed the composition plan in structured/placement-plan.yaml; each
            # composed crop's source points at items/<id>/assets/<role>-group.png,
            # which must exist before materialize_item opens it.
            plan_path = self.store.layout.structured_dir / "placement-plan.yaml"
            if plan_path.exists():
                from .materialize_image_group import (
                    ImageGroupRenderer,
                )
                renderer = ImageGroupRenderer.from_plan_file(plan_path, root)
                renderer.compose_groups(staging)
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
    """Publish a run-local Review UI catalog and bump its source version.

    Workflow staging lives under the gitignored run directory, while the Review UI
    discovers ``<bank-root>/*/staging/*/paper.yaml``.  A run-local catalog symlink
    exposes the already-materialized staging without copying assets or publishing a
    not-yet-approved paper into the formal artifact bank.
    """

    def __init__(self, store) -> None:
        self.store = store

    def refresh(self, staging_directory):
        try:
            _skill_scripts("math-topic-question-bank")
            from notify_catalog_version import bump_version_file  # type: ignore

            staging = Path(staging_directory).resolve()
            bump_version_file(staging)
            catalog_root = self.store.layout.root / "review-catalog"
            alias = (
                catalog_root
                / "langgraph"
                / "staging"
                / self.store.layout.paper_id
            )
            alias.parent.mkdir(parents=True, exist_ok=True)
            if alias.is_symlink():
                if alias.resolve() != staging:
                    raise ValueError(
                        f"review catalog alias points at {alias.resolve()}, expected {staging}"
                    )
            elif alias.exists():
                raise ValueError(f"review catalog alias already exists and is not a symlink: {alias}")
            else:
                relative_target = os.path.relpath(staging, start=alias.parent)
                alias.symlink_to(relative_target, target_is_directory=True)
            return None, None, None
        except Exception as exc:
            return None, "notify_failed", f"{type(exc).__name__}: {exc}"


def _as_ref(value) -> ArtifactRef:
    if isinstance(value, ArtifactRef):
        return value
    return ArtifactRef.model_validate(value)
