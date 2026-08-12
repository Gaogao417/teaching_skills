"""Failure classification policy for the geometry diagram workflow.

Replaces the old ``_audit_failure_is_repairable`` any()-style judgment with a
per-issue, worst-class-wins taxonomy. The point: a single repairable-looking
serialization issue can no longer mask a terminal semantic/environment problem.

A mixed failure such as ``invalid_point_label + prompt_disallowed_marker`` is
classified ``semantic_contract`` (terminal), never "repairable", so the workflow
stops and the batch layer caches the terminal fingerprint instead of
blindly re-attempting the same job across runs.

Four classes (most severe wins when issues are mixed):

  - ``syntax_serialization`` : malformed scene code / renderer spec / point-label
    serialization. Eligible for ONE targeted repair.
  - ``transient``            : Wolfram solve / random-instance hiccups. Eligible
    for ONE targeted repair (the workflow loop still only repairs on round 0).
  - ``semantic_contract``    : prompt disallowed/missing markers, degenerate
    geometry, auxiliary-construction violations. TERMINAL — requires a plan or
    scene-payload change, never a blind retry.
  - ``environment_invariant``: renderer produced no tikz/preview, or the renderer
    itself failed / Wolfram missing. TERMINAL — stop immediately.

The structured ``FailureClassification`` (failure_class, terminal, retry_allowed,
repair_target, issues, failure_fingerprint) is attached to the failing
``WorkflowStageError`` evidence and the workflow result, so the batch layer can
cache terminal failures and short-circuit re-runs (see ``run_diagram_batch``
failure fingerprint).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class FailureClass(str, Enum):
    SYNTAX_SERIALIZATION = "syntax_serialization"
    TRANSIENT = "transient"
    SEMANTIC_CONTRACT = "semantic_contract"
    ENVIRONMENT_INVARIANT = "environment_invariant"


# Severity for worst-issue-wins. Higher value == more terminal. Distinct values
# make the "max" deterministic regardless of issue ordering.
_SEVERITY: dict[FailureClass, int] = {
    FailureClass.SYNTAX_SERIALIZATION: 1,
    FailureClass.TRANSIENT: 2,
    FailureClass.SEMANTIC_CONTRACT: 3,
    FailureClass.ENVIRONMENT_INVARIANT: 4,
}

_TERMINAL: frozenset[FailureClass] = frozenset(
    {FailureClass.SEMANTIC_CONTRACT, FailureClass.ENVIRONMENT_INVARIANT}
)

# Audit issue prefix → class. Order only matters for readability (longest-match
# is not required: prefixes are disjoint).
_AUDIT_PREFIX_CLASS: tuple[tuple[str, FailureClass], ...] = (
    # serialization / payload-structure
    ("invalid_scene_code:", FailureClass.SYNTAX_SERIALIZATION),
    ("invalid_renderer_spec:", FailureClass.SYNTAX_SERIALIZATION),
    ("renderer_spec_not_ready:", FailureClass.SYNTAX_SERIALIZATION),
    ("invalid_point_label:", FailureClass.SYNTAX_SERIALIZATION),
    ("bad serialized label text:", FailureClass.SYNTAX_SERIALIZATION),
    ("label text too long:", FailureClass.SYNTAX_SERIALIZATION),
    # transient
    ("wolfram_failed:", FailureClass.TRANSIENT),
    # environment / invariant — renderer pipeline produced nothing usable
    ("renderer_failed:", FailureClass.ENVIRONMENT_INVARIANT),
    ("invalid_renderer_result:", FailureClass.ENVIRONMENT_INVARIANT),
    ("missing_tikz_fragment:", FailureClass.ENVIRONMENT_INVARIANT),
    ("missing_preview_png:", FailureClass.ENVIRONMENT_INVARIANT),
    # semantic contract — explicit
    ("prompt_disallowed_marker:", FailureClass.SEMANTIC_CONTRACT),
    ("prompt_disallowed_text_annotation:", FailureClass.SEMANTIC_CONTRACT),
    ("missing_required_marker:", FailureClass.SEMANTIC_CONTRACT),
    ("missing_required_text_annotation:", FailureClass.SEMANTIC_CONTRACT),
)

# Semantic-contract prefixes (degenerate geometry + auxiliary constructions).
# Listed explicitly for readability; any *unmatched* issue also falls back to
# semantic_contract below (the safe "do not blind-retry" default).
_SEMANTIC_PREFIXES: tuple[str, ...] = (
    "degenerate_",
    "invalid_auxiliary_construction:",
    "missing_auxiliary_segment:",
    "auxiliary_segment_not_dashed:",
    "missing_auxiliary_carrier_segment:",
    "auxiliary_construction_missing_point:",
    "auxiliary_construction_invalid_coordinates:",
    "auxiliary_carrier_degenerate:",
    "auxiliary_point_off_carrier:",
    "missing_auxiliary_carrier_extension:",
    "auxiliary_carrier_extension_not_dashed:",
)

_REPAIR_TARGET: dict[FailureClass, str] = {
    FailureClass.SYNTAX_SERIALIZATION: "scene_payload.diagram_spec (labels / spec serialization)",
    FailureClass.TRANSIENT: "scene_payload.scene_code (Wolfram solve)",
    FailureClass.SEMANTIC_CONTRACT: "plan.visual_requirements or scene_payload semantic constraints",
    FailureClass.ENVIRONMENT_INVARIANT: "environment (Wolfram / renderer install or paths)",
}

# Stage fail_type → class, used to label non-audit stage failures so the batch
# layer can fingerprint them uniformly. This is for labeling/fingerprinting only;
# it does NOT override the per-stage ``repairable`` flags in workflow.py, which
# are preserved to keep existing retry behavior intact.
_STAGE_FAILTYPE_CLASS: dict[str, FailureClass] = {
    # wolfram syntax (already gets one repair round in workflow.py)
    "invalid_scene_code": FailureClass.SYNTAX_SERIALIZATION,
    "invalid_head": FailureClass.SYNTAX_SERIALIZATION,
    "runtime_error": FailureClass.SYNTAX_SERIALIZATION,
    # wolfram transient
    "timeout": FailureClass.TRANSIENT,
    "no_solution": FailureClass.TRANSIENT,
    "random_instance_failed": FailureClass.TRANSIENT,
    "wolfram_scene_failed": FailureClass.TRANSIENT,
    # wolfram semantic / base-point contract
    "solution_base_point_drift": FailureClass.SEMANTIC_CONTRACT,
    "solution_base_lock_missing": FailureClass.ENVIRONMENT_INVARIANT,
    # compile / render payload
    "scene_spec_compile_failed": FailureClass.SYNTAX_SERIALIZATION,
    "tikz_compile_failed": FailureClass.SYNTAX_SERIALIZATION,
    "invalid_renderer_spec": FailureClass.SYNTAX_SERIALIZATION,
    "invalid_scene_or_renderer_payload": FailureClass.SYNTAX_SERIALIZATION,
    # render / environment
    "renderer_failed": FailureClass.ENVIRONMENT_INVARIANT,
    "preview_pipeline_failed": FailureClass.ENVIRONMENT_INVARIANT,
    "preview_revision_budget_exhausted": FailureClass.SEMANTIC_CONTRACT,
    "render_revision_budget_exhausted": FailureClass.SEMANTIC_CONTRACT,
    "host_environment_or_invariant_failed": FailureClass.ENVIRONMENT_INVARIANT,
    "host_watchdog_timeout": FailureClass.ENVIRONMENT_INVARIANT,
    "worker_no_result": FailureClass.ENVIRONMENT_INVARIANT,
    "missing_rendered_image": FailureClass.ENVIRONMENT_INVARIANT,
    # audit
    "deterministic_audit_failed": FailureClass.SEMANTIC_CONTRACT,
    # human-in-the-loop stop (already resolved; not a blind-retry candidate)
    "human_confirmation_required": FailureClass.SEMANTIC_CONTRACT,
}


@dataclass(frozen=True)
class FailureClassification:
    """Structured, serializable verdict for one workflow failure."""

    failure_class: FailureClass
    issues: tuple[str, ...] = ()
    failure_fingerprint: str = ""

    @property
    def terminal(self) -> bool:
        return self.failure_class in _TERMINAL

    @property
    def retry_allowed(self) -> bool:
        """True when a targeted repair pass is permitted (non-terminal)."""
        return self.failure_class not in _TERMINAL

    @property
    def repair_target(self) -> str:
        return _REPAIR_TARGET[self.failure_class]

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_class": self.failure_class.value,
            "terminal": self.terminal,
            "retry_allowed": self.retry_allowed,
            "repair_target": self.repair_target,
            "issues": list(self.issues),
            "failure_fingerprint": self.failure_fingerprint,
        }


def _class_for_audit_issue(issue: str) -> FailureClass:
    text = str(issue)
    for prefix, cls in _AUDIT_PREFIX_CLASS:
        if text.startswith(prefix):
            return cls
    for prefix in _SEMANTIC_PREFIXES:
        if text.startswith(prefix):
            return FailureClass.SEMANTIC_CONTRACT
    # Unknown deterministic-audit issue → safe terminal default: do not blind-retry.
    return FailureClass.SEMANTIC_CONTRACT


def _fingerprint(failure_class: FailureClass, issues: Iterable[str]) -> str:
    payload = {"failure_class": failure_class.value, "issues": sorted(issues)}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def classify_audit_issues(issues: object) -> FailureClassification:
    """Classify a deterministic-audit issue list, worst-class-wins.

    Unlike the old any()-based check, a single terminal (semantic/environment)
    issue dominates any number of repairable serialization issues. An empty
    issue list (audit failed but produced nothing structured) is treated as
    semantic_contract (terminal) rather than guessed to be a serialization blip.
    """
    issue_list: list[str] = [str(i) for i in issues] if isinstance(issues, list) else []
    if not issue_list:
        cls = FailureClass.SEMANTIC_CONTRACT
    else:
        cls = max(
            (_class_for_audit_issue(i) for i in issue_list),
            key=lambda c: _SEVERITY[c],
        )
    return FailureClassification(
        failure_class=cls,
        issues=tuple(issue_list),
        failure_fingerprint=_fingerprint(cls, issue_list),
    )


def classify_stage_failure(
    stage: str,
    fail_type: str,
    *,
    issues: object = None,
) -> FailureClassification:
    """Label a non-audit stage failure for fingerprinting/reporting.

    This does not change retry behavior (the workflow loop still uses its own
    per-stage ``repairable`` flags); it gives the batch layer a uniform
    classification + fingerprint to cache terminal failures across runs.
    """
    issue_list: list[str]
    if isinstance(issues, list) and issues:
        issue_list = [str(i) for i in issues]
    else:
        issue_list = [f"{stage}:{fail_type}"]
    cls = _STAGE_FAILTYPE_CLASS.get(str(fail_type), FailureClass.SEMANTIC_CONTRACT)
    return FailureClassification(
        failure_class=cls,
        issues=tuple(issue_list),
        failure_fingerprint=_fingerprint(cls, issue_list),
    )


def classify_error(
    stage: str,
    fail_type: str,
    *,
    issues: object = None,
) -> FailureClassification:
    """Uniform entry point: audit issues (if present) take precedence over the
    bare fail_type, because audit issues carry the structured per-check detail."""
    if stage == "audit" or isinstance(issues, list):
        return classify_audit_issues(issues)
    return classify_stage_failure(stage, fail_type, issues=issues)
