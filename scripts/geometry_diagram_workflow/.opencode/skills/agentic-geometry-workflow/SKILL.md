---
name: agentic-geometry-workflow
description: Use this skill when generating a single teaching-oriented geometry render spec through the lightweight agent/tool loop: create a candidate scene/spec, solve it, optionally render a debug image, evaluate when requested, revise from defects, and stop after the retry budget.
---

# Agentic Geometry Workflow

Use this skill for single-problem diagram generation. This is the Phase 1 workflow: it uses opencode agents, local skills, and custom tools first. LangGraph is not required.

## Goal

Produce a `DiagramPackage` for a teaching workflow:

```text
DiagramRequest
  -> candidate GeometricScene or coordinate diagram spec
  -> solved point coordinates
  -> final_renderer_spec.json
  -> optional debug image/VLM usability evaluation
  -> defect-driven revision, at most 3 revisions
  -> final renderer spec/logs for the teaching renderer
```

## Required Inputs

Use a `DiagramRequest` JSON with:

- `problem_text`: original geometry problem text.
- `teaching_focus`: what the diagram must make visible.
- `objects_hint`: points, segments, constraints, constructed objects, or coordinate objects.
- `diagram_type`: `auto`, `synthetic_geometry`, `coordinate_geometry`, `function_graph`, or `hybrid`.
- `max_retries`: default `3`.

Optional model overrides:

- `model_config.text_models`: comma-ordered or JSON-list text model pool.
- `model_config.vision_models`: comma-ordered or JSON-list vision model pool.
- Legacy single-model fields `text_model`, `model`, and `vision_model` are accepted and treated as first-choice models.
- If no model config is provided, the workflow uses the default DashScope/Qwen pools from `core/workflow.py` and `DASHSCOPE_API_KEY`.

## Tool Workflow

Preferred fast path:

1. Call `run_diagram_workflow(request_path, out_dir?)`.
2. Inspect `workflow_result.json`.
3. If `status=ok`, pass `final_renderer_spec.json` to the teaching renderer layer.
4. If `status=failed`, inspect `rounds/*/vision_result.json` and return the fallback reason.

Manual debug path:

1. Call `get_diagram_skill_context(out_dir?)` if you need to inspect the exact skills injected into prompts.
2. Call `generate_diagram_candidate(request_path, out_dir?, round_index=0)`.
3. Call `render_diagram_candidate(request_path, scene_payload_path, out_dir?, round_index=0)` to solve coordinates and optionally export a debug PNG if `wolfram_render_image=true`.
4. Call `evaluate_diagram_image(request_path, render_result_path, out_dir?, round_index=0)` only when a debug PNG was requested.
5. If `vision_result.usable` is false, use `vision_result.defects` and `suggested_constraint_feedback` as the next-round feedback.
6. Repeat steps 2-5 with `round_index += 1`, stopping after the configured retry budget.

## Retry Budget

Interpret `max_retries=3` as:

```text
initial attempt + at most 3 revised attempts = at most 4 total attempts
```

Never continue retrying once:

- `vision_result.usable == true`, or
- `round_index >= max_retries`, or
- render/evaluation failure is caused by missing credentials or missing runtime dependencies.

## Candidate Rules

For synthetic geometry:

- Generate a complete Wolfram `GeometricScene[...]` expression.
- Keep all point symbols declared in the first argument.
- Prefer non-degenerate, label-friendly layouts.
- Add weak layout constraints before strong metric constraints.
- Do not encode false special properties just to make the picture pretty.

For coordinate geometry:

- Prefer an analytic `geometry-render-spec/v1` and the teaching-side deterministic renderer.
- Use real coordinate values, viewport, axes, ticks, and grid settings.
- Do not force coordinate problems into random `GeometricScene` unless synthetic geometry is truly needed.

## Evaluation Rubric

The vision result must be JSON:

```json
{
  "usable": true,
  "score": 4,
  "defects": [],
  "suggested_constraint_feedback": ""
}
```

Score:

- `5`: ready for student-facing teaching.
- `4`: minor defects but usable.
- `3`: recognizable but needs human adjustment.
- `2`: misleading or hard to read.
- `1`: unusable or render failed.

Default usability threshold: `score >= 4`.

Check:

- Objects match the problem.
- No important point/segment/region is hidden.
- Shape is not degenerate.
- Labels can be placed/read.
- Coordinate axes and ticks are readable when present.
- Diagram does not imply properties not given by the problem.
- Teaching focus is visually supported.

## Artifacts

Each round must write:

```text
rounds/round_<n>/
  scene_payload.json
  scene.wl
  render_result.json
  vision_result.json
```

Final output must include:

```text
workflow_result.json
final_diagram_spec.json
final_renderer_spec.json
final_geometric_scene.wl
```

`workflow_result.json` must include:

- `status`
- `error`
- `out_dir`
- `skills_used`
- `rounds`
- `final_diagram_spec`
- `final_renderer_spec`
- `final_image_path` (optional debug image only)

## Failure Handling

Use structured failure categories:

- `generate_scene_failed`
- `render_exception`
- `host_watchdog_timeout`
- `worker_no_result`
- `vision_evaluation_failed`
- `max_retries_exhausted`

If the workflow fails, return a concise fallback:

```text
The diagram workflow failed after N attempts. Main defects: ...
Suggested fallback: use a textual diagram description or a simple hand-authored SVG.
```

## Related Skills

Load or rely on these skills when relevant:

- `wolfram-geometricscene-reference`
- `wolfram-schema-first-param-types`
- `dimensionless-constraints-library`
- `wolfram-python-integration-patterns`
- `human-rating-loop`
- `tool-output-standards`
- `agent-io-schema`
