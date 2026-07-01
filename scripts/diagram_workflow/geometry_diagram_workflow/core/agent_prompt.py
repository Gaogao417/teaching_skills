from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

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


def diagram_agent_prompt(
    request: Dict[str, object],
    out_dir: Path,
    request_path: Path,
    *,
    skill_names: str,
) -> str:
    max_retries = int(request.get("max_retries", 3))
    attempts = max_retries + 1
    python_cmd = sys.executable
    workflow_py = "geometry_diagram_workflow/core/workflow.py"
    render_py = "render_geometry_spec.py"
    request_json = json.dumps(request, ensure_ascii=False, indent=2, default=_json_default)
    return f"""
You are the Codex diagram workflow subagent for synthetic geometry diagrams.

Your current working directory is scripts/diagram_workflow. Use the attached Codex
skills: {skill_names}.

You own the whole loop: generate GeometricScene -> run Wolfram -> compile
GeometryRenderSpec -> render TikZ preview -> deterministic audit -> visually inspect
the preview PNG yourself -> repair and retry. The Python host will only start you
and validate final artifacts.

Hard boundaries:
- Write only inside this job directory: {out_dir}
- Do not edit source files, tests, skills, docs, or files outside the job directory.
- Use only the fixed commands below for Wolfram/render/audit/finalize tooling.
- Total attempts: at most {attempts} (initial + {max_retries} repairs).
- Final response must be one JSON object matching the provided schema.

Input request path:
{request_path}

Normalized request JSON:
{request_json}

Required per-round workflow:
1. Create rounds/round_N/scene_payload.json yourself. It must contain:
   - scene_code: complete Wolfram GeometricScene expression.
   - points: point labels.
   - diagram_spec: visible segments, polygons, markers, labels if needed.
   - rationale: short reason.
2. Run Wolfram solve:
   "{python_cmd}" {workflow_py} --action render --request "{request_path}" --out "{out_dir}" --round-index N --scene-payload "{out_dir}/rounds/round_N/scene_payload.json"
3. Compile renderer spec:
   "{python_cmd}" {workflow_py} --action compile_spec --request "{request_path}" --out "{out_dir}" --round-index N --scene-payload "{out_dir}/rounds/round_N/scene_payload.json" --render-result "{out_dir}/rounds/round_N/render_result.json"
4. Render TikZ/preview:
   "{python_cmd}" {render_py} "{out_dir}/rounds/round_N/final_renderer_spec.json" --out-dir "{out_dir}/rounds/round_N" --variant prompt
5. Deterministic audit:
   "{python_cmd}" {workflow_py} --action audit --request "{request_path}" --out "{out_dir}" --round-index N --scene-payload "{out_dir}/rounds/round_N/scene_payload.json" --render-result "{out_dir}/rounds/round_N/render_result.json" --renderer-spec "{out_dir}/rounds/round_N/final_renderer_spec.json" --renderer-result "{out_dir}/rounds/round_N/renderer_result.json"
6. Read {out_dir}/rounds/round_N/audit_result.json. The audit is a hard
   contract gate only: it checks executable artifacts, schema validity, render
   success, missing files, and obviously broken serialized labels. It does not
   judge whether the geometry picture is pedagogically correct.
7. If audit passes, inspect the rendered preview PNG yourself from this path:
   {out_dir}/rounds/round_N/rendered/prompt.preview.png
   You can open/read that local image path directly. Do not wait for the host to
   attach image input. Your visual inspection must decide whether the picture
   matches the request, is non-degenerate, has readable labels, avoids false
   implications, and does not include solution hints forbidden by the prompt.
8. If deterministic audit passes and your own visual inspection passes, finalize:
   "{python_cmd}" {workflow_py} --action finalize_round --request "{request_path}" --out "{out_dir}" --round-index N --scene-payload "{out_dir}/rounds/round_N/scene_payload.json" --render-result "{out_dir}/rounds/round_N/render_result.json" --renderer-spec "{out_dir}/rounds/round_N/final_renderer_spec.json" --renderer-result "{out_dir}/rounds/round_N/renderer_result.json" --audit-result "{out_dir}/rounds/round_N/audit_result.json"
9. If audit fails or your visual inspection fails, read the failed files and
   repair the next round. Prefer changing GeometricScene first when Wolfram
   fails, and changing diagram_spec first when labels/markers/rendering fail.

GeometricScene requirements:
- Correct point-only syntax: GeometricScene[{{A, B, C}}, {{hypotheses}}]
- Wrong nested point-list syntax: GeometricScene[{{{{A, B, C}}}}, {{hypotheses}}]
- If you are unsure, inspect scene_payload.json and make sure it does not
  contain the substring "GeometricScene[{{{{". The workflow rejects nested point lists.
- Avoid scalar parameter forms in v1; use concrete point constraints instead.

Deterministic audit priorities:
- renderer_result.status must be ok.
- TikZ fragment and preview PNG must exist and be non-empty.
- renderer spec must validate against geometry-render-spec/v1.
- Labels must be plain point labels, not ref, GeometricPoint, [[, ]], or long
  serialized Wolfram expressions.
- Deterministic audit can block broken artifacts, but it cannot approve visual
  quality; you still must inspect the preview PNG path yourself before finalize.

Visual inspection priorities:
- Match all named points, segments, midpoints, perpendicular/parallel/equality
  relations, and requested construction lines from the problem.
- Keep worksheet diagrams clean. Remove unnecessary angle arcs, focus labels,
  helper point labels, and solution hints unless the request explicitly asks for
  a solution/annotated variant.
- Do not display extra generated labels such as centroid helper references.
- If a clean prompt diagram should only show the givens, do not add theorem or
  proof-result annotations.

When finished, return:
{{
  "status": "ok" or "failed",
  "workflow_result_path": "...",
  "final_renderer_spec_path": "...",
  "renderer_result_path": "...",
  "selected_round": N,
  "message": "short summary"
}}
""".strip()
