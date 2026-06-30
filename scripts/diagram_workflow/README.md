# Diagram Workflow Scripts

This directory contains the active diagram generation workflow used by
`math-geometry-diagram-renderer`.

Primary entry point:

```bash
python3 scripts/diagram_workflow/run_assignment_diagrams.py <plan.assignment.yaml>
```

By default the four stages run in-process through
`assignment_pipeline.run_assignment_diagram_pipeline`: one Python interpreter
drives collect → batch → gate → resolve by calling library functions directly,
and the per-job workflow/renderer stages stay inside the same process for the
deterministic routes. The on-disk artifacts are identical to the legacy
script-chained path.

Pipeline order (the same functions, in-process by default):

```text
collect_diagram_jobs.py
run_diagram_batch.py
check_diagram_gate.py
resolve_assignment_diagrams.py
```

`--process-isolation` restores the legacy four-subprocess chain (one Python
interpreter per stage) for debugging, localizing, or temporary rollback. The
single-stage CLIs above remain independently runnable for the same reason.

Per-job routing inside `run_diagram_batch.py`:

- `renderer_spec` and analytic (`coordinate_renderer` / `wolfram_client` /
  `wolfram_plot`) jobs run in-process.
- `geometric_scene` / synthetic geometry keeps subprocess isolation, so the
  GeometricScene LLM and Wolfram runtime cannot pollute the main process.
- The TikZ compiler (`render_geometry_spec`) runs in-process; it still shells
  out to the TeX/pdf toolchain only for diagnostic previews.

Supporting modules:

- `assignment_pipeline.py`: in-process orchestrator that drives the four
  stages via library calls; used by `run_assignment_diagrams.py` by default.
- `diagram_contracts.py`: Pydantic contracts for slots, jobs, renderer
  bindings, gates, requests, and renderer results.
- `renderer_bindings.py`: shared loader that reads `diagram_jobs.json` plus
  per-job `renderer_result.json` and produces the bindable TikZ facts consumed
  by gate and resolver.
- `diagram_gate/`: gate checks grouped by responsibility: artifact bindings,
  policy safety, layout floors, SVG preview readability, and analytic specs.
- `run_diagram_workflow.py`: single-job engine router (also exposes
  `run_renderer_spec_workflow` for the in-process batch path).
- `analytic_diagram_workflow.py`: coordinate/function diagram branch
  (`run_analytic_workflow` runs in-process from the batch runner).
- `render_geometry_spec.py`: deterministic TikZ compiler (`render_geometry_spec`
  runs in-process from the batch runner); writes the bindable
  `rendered/<variant>.fragment.tex` plus optional preview files.
- `tikz_renderer/`: typed compiler modules for synthetic geometry and
  coordinate/function render specs.
- `geometry_diagram_workflow/`: local GeometricScene workflow branch.
- `build_diagram_artifacts.py`: debug dump for renderer bindings; no longer a
  required production step.
