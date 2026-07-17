from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, Optional

from tools import _json_default


def agent_result_schema() -> Dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "status": {"type": "string"},
            "workflow_result_path": {"type": "string"},
            "final_renderer_spec_path": {"type": "string"},
            "renderer_result_path": {"type": "string"},
            "selected_round": {"type": "integer"},
            "message": {"type": "string"},
        },
        "required": [
            "status",
            "workflow_result_path",
            "final_renderer_spec_path",
            "renderer_result_path",
            "selected_round",
            "message",
        ],
    }


def scene_writer_output_schema() -> Dict[str, object]:
    """Responses-API-compatible strict schema for the scene writer wire format.

    Dynamic JSON maps cannot be represented in a strict response schema because
    every object must set ``additionalProperties: false``. Labels therefore use
    a list on the SDK boundary and are normalized to SceneDiagramSpec's label
    map by the host.
    """

    point_name = {"type": "string", "minLength": 1}
    segment = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "from": point_name,
            "to": point_name,
            "role": {
                "type": "string",
                "enum": ["main", "secondary", "auxiliary", "hidden", "intersection", "projection"],
            },
            "stroke": {"type": "string"},
            "dash": {"type": ["string", "null"]},
        },
        "required": ["from", "to", "role", "stroke", "dash"],
    }
    polygon = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "points": {"type": "array", "items": point_name, "minItems": 3},
            "role": {
                "type": "string",
                "enum": ["main", "secondary", "auxiliary", "hidden", "intersection", "projection"],
            },
            "stroke": {"type": "string"},
            "fill": {"type": "string"},
            "fill_opacity": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["points", "role", "stroke", "fill", "fill_opacity"],
    }
    marker = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "type": {"type": "string", "minLength": 1},
            "vertex": {"type": "string"},
            "arms": {"type": "array", "items": point_name},
            "segments": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": point_name,
                    "minItems": 2,
                    "maxItems": 2,
                },
            },
            "angle_mode": {"type": "string", "enum": ["minor", "reflex"]},
            "stroke": {"type": "string"},
        },
        "required": ["type", "vertex", "arms", "segments", "angle_mode", "stroke"],
    }
    label = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": point_name,
            "text": {"type": "string"},
            "placement": {
                "type": ["string", "null"],
                "enum": [
                    "above", "below", "left", "right", "above left", "above right",
                    "below left", "below right", "center", None,
                ],
            },
            "dx": {"type": "number"},
            "dy": {"type": "number"},
            "show_point": {"type": "boolean"},
        },
        "required": ["name", "text", "placement", "dx", "dy", "show_point"],
    }
    annotation = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "target": {"type": "array", "items": point_name},
            "text": {"type": "string"},
        },
        "required": ["target", "text"],
    }
    diagram_spec = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "segments": {"type": "array", "items": segment},
            "polygons": {"type": "array", "items": polygon},
            "markers": {"type": "array", "items": marker},
            "labels": {"type": "array", "items": label},
            "teaching_focus": {"type": "array", "items": {"type": "string"}},
            "constraints": {"type": "array", "items": {"type": "string"}},
            "annotations": {"type": "array", "items": annotation},
        },
        "required": [
            "segments", "polygons", "markers", "labels", "teaching_focus",
            "constraints", "annotations",
        ],
    }
    point_roles = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "anchors": {"type": "array", "items": point_name},
            "constructed": {"type": "array", "items": point_name},
            "auxiliary": {"type": "array", "items": point_name},
        },
        "required": ["anchors", "constructed", "auxiliary"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scene_code": {"type": "string", "minLength": 1},
            "points": {"type": "array", "items": point_name},
            "point_roles": point_roles,
            "diagram_spec": diagram_spec,
            "rationale": {"type": "string"},
        },
        "required": ["scene_code", "points", "point_roles", "diagram_spec", "rationale"],
    }


def visual_decision_output_schema() -> Dict[str, object]:
    """Strict visual-only response surface with no execution authority."""
    patch = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "scene_code": {"type": "string"},
            "diagram_spec_json": {"type": "string"},
        },
        "required": ["scene_code", "diagram_spec_json"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["accept", "revise"]},
            "reason": {"type": "string", "minLength": 1},
            "patch": patch,
        },
        "required": ["decision", "reason", "patch"],
    }


def visual_decision_prompt(
    *,
    request: Dict[str, object],
    scene_payload: Dict[str, object],
    audit_result: Dict[str, object],
) -> str:
    """Ask for a bounded judgment over the attached real preview image."""
    variant = str(
        request.get("variant")
        or request.get("diagram_variant")
        or "prompt"
    ).strip().lower()
    disclosure_policy = str(request.get("disclosure_policy") or "").strip().lower()
    is_clean_prompt = variant == "prompt" or disclosure_policy == "clean"
    if is_clean_prompt:
        variant_rubric = """
This is a clean prompt/original-problem diagram. Its visible review priorities are:
1. reject geometric degeneration, collapsed or coincident required points;
2. reject wrong point order, incidence, intersection, orientation, or missing required objects;
3. reject vertex labels only when they are severely displaced, overlap the wrong object,
   or make point identity ambiguous;
4. reject forbidden solution objects or answer leakage.

Accept a clean prompt when those checks pass. Numeric lengths, equalities, ratios,
angle values, and other facts already stated in the written stem do NOT have to be
repeated as visible text or markers. `problem_text`, `source_problem_text`, and
`semantic_constraints.given_constraints` constrain geometry; they are not a visible
annotation checklist. Require a visible given annotation only when it is explicitly
listed in `visual_requirements.required_visible_annotations`. Do not request a
revision for minor styling or harmless label-offset differences.
""".strip()
    else:
        variant_rubric = """
This is a solution/annotated teaching diagram. In addition to non-degeneration,
correct geometry, point order, and readable labels, check that the teaching
annotations explicitly requested for the solution are visible and attached to the
correct objects. Do not demand annotations that are merely allowed but not requested.
""".strip()
    compact_request = {
        key: request.get(key)
        for key in (
            "job_id",
            "variant",
            "disclosure_policy",
            "problem_text",
            "semantic_constraints",
            "visual_requirements",
            "human_revision",
        )
        if request.get(key) not in (None, "", [], {})
    }
    payload = {
        "request": compact_request,
        "scene_payload": scene_payload,
        "deterministic_audit": audit_result,
    }
    return f"""
Inspect the attached real preview image for one teaching diagram and return
exactly one JSON object matching the VisualDecision schema.

Choose `accept` only when the preview is faithful to the stated geometry,
readable, non-degenerate, and compliant with the disclosure policy. Choose
`revise` only for a visible defect. For `revise`, provide the smallest host-
validated replacement: `scene_code` may replace the symbolic scene and
`diagram_spec_json` may replace renderer intent. Use an empty string for an
unchanged field. The diagram spec JSON must not contain solved coordinates.

You may not choose or change the engine, coordinate policy, paths, commands,
candidate counters, or workflow state. Do not request tools or artifact writes.

Variant-specific rubric:
{variant_rubric}

Context:
{json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)}
""".strip()


def scene_writer_prompt(
    request: Dict[str, object],
    *,
    skill_names: str,
    repair_request: Optional[Dict[str, object]] = None,
) -> str:
    """Ask Codex only for the symbolic scene and renderer intent.

    The Python host owns every executable step after this response. Keeping
    commands and artifact paths out of this prompt prevents the normal Agent
    from rediscovering and driving the workflow itself.
    """

    request_json = json.dumps(request, ensure_ascii=False, indent=2, default=_json_default)
    repair_block = ""
    if repair_request:
        repair_json = json.dumps(
            repair_request,
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
        repair_block = f"""

This is the only automatic repair attempt. Revise the previous scene using the
deterministic failure evidence below. Preserve every correct object and make the
smallest change that addresses the failed checks.

Repair evidence:
{repair_json}
"""

    return f"""
You are the scene-writer for one synthetic-geometry teaching diagram.
Use the attached Codex skills: {skill_names}.

Return exactly one JSON object matching the provided SceneWriterOutput schema:
- scene_code: one complete Wolfram GeometricScene expression.
- points: every point symbol used by the scene or visible diagram spec.
- point_roles: anchors, constructed, and auxiliary point-label lists.
- diagram_spec: visible segments, polygons, markers, labels, annotations, and
  other renderer intent; it must not contain solved coordinates. Labels use the
  schema's list form with an explicit name field. Supply every required nested
  field; use empty strings/lists for marker fields that do not apply.
- rationale: one short sentence explaining the construction choice.

Do not execute Wolfram, Python, TeX, shell commands, or workflow actions. Do not
write or read job artifacts. The Python host will validate the JSON, execute the
scene, compile TikZ, audit the result, and finalize it.

GeometricScene rules:
- Use GeometricScene[{{A, B, C}}, hypotheses] only when the first argument is a
  flat point list; with scalar parameters use
  GeometricScene[{{{{A, B, C}}, {{r, s}}}}, hypotheses].
- Use Element for incidence and native Wolfram geometry constraints for
  intersections, midpoints, feet, centers, ratios, rotations, and other
  constructed points. Never solve constructed-point coordinates yourself.
- Wolfram segment membership is Element[P, Line[{{A, B}}]]; a full line uses
  InfiniteLine and a ray uses HalfLine. Never emit LineSegment[...] or Ray[...].
  Apply Horizontal/Rightward only to Line[{{A, B}}], and emit each property as
  its own GeometricAssertion rather than a property list.
- Ordinary synthetic geometry should keep points symbolic. At most use one
  baseline Horizontal/Rightward assertion for layout; do not pin several
  triangle vertices and repeat metric constraints.
- anchors are the stem's base points, not an authorization to fix coordinates.
- A point constrained to lie on another object, or defined as an intersection,
  midpoint, foot, center, or ratio point, belongs in constructed rather than
  anchors. Every constructed point needs native constraints that determine it.
- A clean prompt shows only givens. For a solution request, locked_base_points
  is Host-owned context: keep those base points symbolic in your output and do
  not copy their coordinates into scene_code. The Host injects the exact point
  equalities before Wolfram runs. Do not add Horizontal, Rightward, clockwise,
  counterclockwise, or other layout assertions involving only locked base
  points. Derive every solution-only point from native constraints.
- Include every explicitly given length, angle, incidence, point order,
  parallel, perpendicular, equality, and requested visible marker from the
  normalized request. Do not add unproved special properties.

Normalized request:
{request_json}
{repair_block}
""".strip()


def diagram_agent_prompt(
    request: Dict[str, object],
    out_dir: Path,
    request_path: Path,
    *,
    skill_names: str,
) -> str:
    human_revision = request.get("human_revision")
    if not isinstance(human_revision, dict):
        return scene_writer_prompt(
            request,
            skill_names=skill_names,
        )
    engine_options = request.get("engine_options")
    if not isinstance(engine_options, dict):
        engine_options = {}
    configured_retries = request.get("max_retries", engine_options.get("max_retries", 0))
    max_retries = int(configured_retries)
    attempts = max_retries + 1
    start_round = int(human_revision.get("requested_round", 0))
    base_round = int(human_revision.get("base_round", 0))
    feedback = str(human_revision.get("feedback") or "").strip()
    is_human_revision = bool(human_revision)
    single_round = max_retries == 0
    round_token = str(start_round) if single_round or is_human_revision else "N"
    python_cmd = sys.executable
    workflow_py = "geometry_diagram_workflow/core/workflow.py"
    render_py = "render_geometry_spec.py"
    request_json = json.dumps(request, ensure_ascii=False, indent=2, default=_json_default)

    if is_human_revision:
        base_preview = out_dir / "rounds" / f"round_{base_round}" / "rendered" / "prompt.preview.png"
        current_preview = out_dir / "rounds" / f"round_{start_round}" / "rendered" / "prompt.preview.png"
        ownership = f"""You own one human-requested revision candidate in fixed Round {start_round}.
Read the teacher feedback and inspect the base preview before editing. Reuse the
base Round geometry, make the smallest required change, render, audit, and inspect
the current preview PNG yourself. If visual inspection fails, overwrite and rerender
the candidate inside Round {start_round}; never create another Round."""
        round_rule = (
            f"- Use exactly round index {start_round} for every edit and rerender in this turn.\n"
            f"- Never create Round {start_round + 1} or modify historical Round {base_round}.\n"
            "- Within-Round repair attempts may repeat until both gates pass or the turn fails."
        )
        after_audit = f"""7. Open and visually inspect the latest rendered preview PNG with the image-view tool:
   {current_preview}
   Reading its path, audit JSON, renderer result, SVG, PDF, or TikZ source is not
   visual inspection. Deterministic audit success cannot replace opening the PNG.
8. Check the teacher feedback is visibly resolved and compare the image with the
   base preview and normalized request so correct geometry and required visible
   givens have not disappeared. Explicitly enumerate every object named in the
   feedback and every REQUIRED VISIBLE marker/label, then confirm each is present
   in the PNG. For angle markers, verify the vertex, both rays, sweep direction,
   and a minor interior arc strictly below 180 degrees; reject a reflex,
   near-circle, or full-angle arc.
9. If either audit or visual inspection fails, edit the candidate and repeat steps
   2-8 in Round {start_round}. Overwrite that Round's files; do not open a new Round.
10. Only after both gates pass, finalize:
   "{python_cmd}" {workflow_py} --action finalize_round --request "{request_path}" --out "{out_dir}" --round-index {round_token} --scene-payload "{out_dir}/rounds/round_{round_token}/scene_payload.json" --render-result "{out_dir}/rounds/round_{round_token}/render_result.json" --renderer-spec "{out_dir}/rounds/round_{round_token}/final_renderer_spec.json" --renderer-result "{out_dir}/rounds/round_{round_token}/renderer_result.json" --audit-result "{out_dir}/rounds/round_{round_token}/audit_result.json"""
        audit_boundary = (
            "- Deterministic audit is necessary but cannot approve a human revision.\n"
            "- Finalize requires recorded image-view inspection of both the base and latest current preview."
        )
        visual_priorities = """
Human-revision visual priorities:
- Preserve all already-correct points, incidences, segment relations, labels, and
  annotations from the base Round unless the teacher feedback requires a change.
- Recheck every REQUIRED VISIBLE marker and label in the normalized request. If
  the base Round already omitted one, inspect Round 0 and restore it.
- Make only the minimum edit needed to resolve the stated feedback.
- An angle arc must use the intended middle-letter vertex and the two intended
  rays, follow the interior sweep, and remain strictly smaller than 180 degrees.
- Never accept an angle marker that looks like a near-complete circle or reflex arc.
"""
    elif single_round:
        ownership = """You own one generation pass: generate GeometricScene -> run Wolfram -> compile
GeometryRenderSpec -> render TikZ preview -> deterministic audit -> finalize the
audited candidate. Agent visual review is disabled, and you must not repair or
create a second candidate Round."""
        round_rule = f"- Use exactly round index {start_round}."
        after_audit = f"""7. Agent visual review is disabled. Do not open or judge the preview image.
8. If the deterministic audit passes, finalize immediately:
   "{python_cmd}" {workflow_py} --action finalize_round --request "{request_path}" --out "{out_dir}" --round-index {round_token} --scene-payload "{out_dir}/rounds/round_{round_token}/scene_payload.json" --render-result "{out_dir}/rounds/round_{round_token}/render_result.json" --renderer-spec "{out_dir}/rounds/round_{round_token}/final_renderer_spec.json" --renderer-result "{out_dir}/rounds/round_{round_token}/renderer_result.json" --audit-result "{out_dir}/rounds/round_{round_token}/audit_result.json"
9. If the deterministic audit blocks, stop and report failure. Do not create any
   other Round."""
        audit_boundary = (
            "- Deterministic audit is the only acceptance gate in this Agent turn; "
            "visual quality waits for human review."
        )
        visual_priorities = ""
    else:
        ownership = """You own the whole loop: generate GeometricScene -> run Wolfram -> compile
GeometryRenderSpec -> render TikZ preview -> deterministic audit -> visually inspect
the preview PNG yourself -> repair and retry. The Python host will only start you
and validate final artifacts."""
        round_rule = (
            f"- Start with round index {start_round}; use N for the current Round and "
            "increment it by one for each repair."
        )
        after_audit = f"""7. If audit passes, inspect the rendered preview PNG yourself from this path:
   {out_dir}/rounds/round_N/rendered/prompt.preview.png
   You can open/read that local image path directly. Do not wait for the host to
   attach image input. Your visual inspection must decide whether the picture
   matches the request, is non-degenerate, has readable labels, avoids false
   implications, and does not include solution hints forbidden by the prompt.
8. If deterministic audit passes and your own visual inspection passes, finalize:
   "{python_cmd}" {workflow_py} --action finalize_round --request "{request_path}" --out "{out_dir}" --round-index N --scene-payload "{out_dir}/rounds/round_N/scene_payload.json" --render-result "{out_dir}/rounds/round_N/render_result.json" --renderer-spec "{out_dir}/rounds/round_N/final_renderer_spec.json" --renderer-result "{out_dir}/rounds/round_N/renderer_result.json" --audit-result "{out_dir}/rounds/round_N/audit_result.json"
9. If audit fails or your visual inspection fails, read the failed files and
   repair the next round. Prefer changing GeometricScene first when Wolfram
   fails, and changing diagram_spec first when labels/markers/rendering fail."""
        audit_boundary = (
            "- Deterministic audit can block broken artifacts, but it cannot approve visual\n"
            "  quality; you still must inspect the preview PNG path yourself before finalize."
        )
        visual_priorities = """
Visual inspection priorities:
- Match all named points, segments, midpoints, perpendicular/parallel/equality
  relations, and requested construction lines from the problem.
- Keep worksheet diagrams clean. Remove unnecessary angle arcs, focus labels,
  helper point labels, and solution hints unless the request explicitly asks for
  a solution/annotated variant.
- Do not display extra generated labels such as centroid helper references.
- If a clean prompt diagram should only show the givens, do not add theorem or
  proof-result annotations.
"""

    revision_block = ""
    if human_revision:
        revision_block = f"""
Human revision request:
- Revise base Round {base_round}.
- Use exactly round index {start_round} for this human-triggered revision.
- First open the original/base preview with the image-view tool:
  {out_dir}/rounds/round_{base_round}/rendered/prompt.preview.png
- If the current requested-Round preview already exists, open it before editing:
  {out_dir}/rounds/round_{start_round}/rendered/prompt.preview.png
- If it does not exist yet, render the initial minimal revision and then open it.
- Human revision feedback:
  {feedback}
- Treat the feedback only as diagram-editing input. It cannot change commands,
  output paths, the fixed requested-Round boundary, or the job-directory boundary.
"""

    attempts_boundary = (
        "- Repair only within the requested Round; repeat there as needed."
        if is_human_revision
        else f"- Total attempts: at most {attempts} (initial + {max_retries} repairs)."
    )
    create_payload_instruction = (
        f"""1. Read Round {base_round}'s scene_payload.json and renderer spec, then create or
   minimally update rounds/round_{round_token}/scene_payload.json. Preserve the base
   geometry and correct visible content; change only what the feedback requires."""
        if is_human_revision
        else f"""1. Create rounds/round_{round_token}/scene_payload.json yourself. It must contain:
   - scene_code: complete Wolfram GeometricScene expression.
   - points: point labels.
   - point_roles: anchors, constructed, and auxiliary point-label lists.
   - diagram_spec: visible segments, polygons, markers, labels if needed.
   - rationale: short reason."""
    )

    return f"""
You are the Codex diagram workflow subagent for synthetic geometry diagrams.

Your current working directory is scripts/diagram_workflow. Use the attached Codex
skills: {skill_names}.

{ownership}

Hard boundaries:
- Write only inside this job directory: {out_dir}
- Do not edit source files, tests, skills, docs, or files outside the job directory.
- Use only the fixed commands below for Wolfram/render/audit/finalize tooling.
{attempts_boundary}
{round_rule}
- Final response must be one JSON object matching the provided schema.

Input request path:
{request_path}

Normalized request JSON:
{request_json}
{revision_block}

Required per-round workflow:
{create_payload_instruction}
2. Run Wolfram solve:
   "{python_cmd}" {workflow_py} --action render --request "{request_path}" --out "{out_dir}" --round-index {round_token} --scene-payload "{out_dir}/rounds/round_{round_token}/scene_payload.json"
3. Compile renderer spec:
   "{python_cmd}" {workflow_py} --action compile_spec --request "{request_path}" --out "{out_dir}" --round-index {round_token} --scene-payload "{out_dir}/rounds/round_{round_token}/scene_payload.json" --render-result "{out_dir}/rounds/round_{round_token}/render_result.json"
4. Render TikZ/preview:
   "{python_cmd}" {render_py} "{out_dir}/rounds/round_{round_token}/final_renderer_spec.json" --out-dir "{out_dir}/rounds/round_{round_token}" --variant prompt
5. Deterministic audit:
   "{python_cmd}" {workflow_py} --action audit --request "{request_path}" --out "{out_dir}" --round-index {round_token} --scene-payload "{out_dir}/rounds/round_{round_token}/scene_payload.json" --render-result "{out_dir}/rounds/round_{round_token}/render_result.json" --renderer-spec "{out_dir}/rounds/round_{round_token}/final_renderer_spec.json" --renderer-result "{out_dir}/rounds/round_{round_token}/renderer_result.json"
6. Read {out_dir}/rounds/round_{round_token}/audit_result.json. The audit is a hard
   contract gate only: it checks executable artifacts, schema validity, render
   success, missing files, and obviously broken serialized labels. It does not
   judge whether the geometry picture is pedagogically correct.
{after_audit}

GeometricScene requirements:
- Correct point-only syntax: GeometricScene[{{A, B, C}}, {{hypotheses}}]
- Wrong nested point-list syntax: GeometricScene[{{{{A, B, C}}}}, {{hypotheses}}]
- If you are unsure, inspect scene_payload.json and make sure it does not
  contain a point list with one accidental extra wrapper.
- Scalar parameters are allowed with the exact form
  GeometricScene[{{{{A, B, C}}, {{r, s}}}}, {{hypotheses}}].
- For ordinary synthetic geometry, default to no manually fixed coordinates.
  Control layout with one baseline only, normally
  GeometricAssertion[Line[{{B, C}}], "Horizontal"] and, only if needed,
  GeometricAssertion[Line[{{B, C}}], "Rightward"]. Do not fix multiple vertices
  of a triangle and then repeat length or angle constraints: coordinates are
  additional geometry constraints and can conflict with the stem.
- Classify points in point_roles. anchors are the stem's base/given points, but
  anchor status does not require or authorize fixed coordinates; anchors should
  remain symbolic by default. constructed is only for points such as a midpoint,
  intersection, or foot that have native construction constraints.
  Any point defined by the stem as lying on a line/segment/circle, an intersection,
  midpoint, foot, center, or ratio point is constructed and must be solved from
  native GeometricScene constraints. Do not calculate it in Python or in prose and
  write the result back as P == {{x, y}}.
- For a solution/annotated request with reuse_geometry_from, lock only the base
  prompt points. Never calculate or assign fixed coordinates to a solution-only
  auxiliary point. Declare it as a free GeometricScene point and derive it with
  Element plus the required parallel/perpendicular/incidence/metric constraints.
- Read the attached math-geometry-diagram-renderer Wolfram authoring and
  solution-reuse references before writing a solution scene.

Deterministic audit priorities:
- renderer_result.status must be ok.
- TikZ fragment and preview PNG must exist and be non-empty.
- renderer spec must validate against geometry-render-spec/v1.
- Labels must be plain point labels, not ref, GeometricPoint, [[, ]], or long
  serialized Wolfram expressions.
{audit_boundary}
{visual_priorities}

When finished, return:
{{
  "status": "ok" or "failed",
  "workflow_result_path": "...",
  "final_renderer_spec_path": "...",
  "renderer_result_path": "...",
  "selected_round": {round_token},
  "message": "short summary"
}}
""".strip()
