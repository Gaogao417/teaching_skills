# Diagram Workflow Scripts

This directory contains the active diagram generation workflow used by
`math-geometry-diagram-renderer`.

Primary entry point:

```bash
python3 scripts/diagram_workflow/run_assignment_diagrams.py <plan.assignment.yaml>
```

Live SDK assignment regression (opt-in only; requires Codex SDK credentials and
a working Wolfram kernel):

```bash
./.venv-diagram/bin/python scripts/diagram_workflow/live_assignment_diagram_e2e.py
```

This writes a small assignment under
`artifacts/杨茗贺/2026-07-07-线段比再练-出图回归/`, runs the real
Codex SDK + GeometricScene route, verifies Wolfram/TikZ evidence, and compiles a
PDF. It is intentionally excluded from default pytest.

By default the stages run in-process through
`assignment_pipeline.run_assignment_diagram_pipeline`: one Python interpreter
drives collect → batch/per-job gate → resolve → resolved-assignment gate by calling library functions directly,
and the per-job workflow/renderer stages stay inside the same process for the
deterministic routes. The on-disk artifacts are identical to the legacy
script-chained path.

Pipeline order (in-process by default):

```text
collect_diagram_jobs.py
run_diagram_batch.py + JobPackageGate per job
resolve_assignment_diagrams.py
ResolvedAssignmentGate
```

`--process-isolation` restores the legacy subprocess chain (one Python
interpreter per stage) for debugging, localizing, or temporary rollback. The
single-stage CLIs above remain independently runnable for the same reason.

Per-job routing inside `run_diagram_batch.py`:

- `renderer_spec`, `spatial_renderer`, and analytic (`coordinate_renderer` / `wolfram_client` /
  `wolfram_plot`) jobs run in-process.
- `geometric_scene` / synthetic geometry keeps subprocess isolation, so the
  GeometricScene LLM and Wolfram runtime cannot pollute the main process.
- `geometric_scene` owns its TikZ fragment and preview inside the Host lifecycle;
  Batch consumes that complete package and does not render it again.
- The TikZ compiler (`render_geometry_spec`) runs in-process for deterministic
  routes; it still shells out to the TeX/pdf toolchain only for diagnostic previews.
- After deterministic audit, opted-in synthetic jobs receive a bounded Agent
  visual-decision turn with the real preview image attached. The response can
  only accept or return a host-validated scene/spec patch.

Supporting modules:

- `assignment_pipeline.py`: in-process orchestrator that drives the assignment
  stages via library calls; used by `run_assignment_diagrams.py` by default.
- `diagram_contracts.py`: Pydantic contracts for slots, jobs, renderer
  bindings, gates, requests, and renderer results.
- `renderer_bindings.py`: shared loader that reads `diagram_jobs.json` plus
  per-job `renderer_result.json` and produces the bindable TikZ facts consumed
  by gate and resolver.
- `diagram_gate/`: per-job package and post-resolve checks grouped by responsibility: artifact bindings,
  policy safety, layout floors, SVG preview readability, analytic specs, and
  spatial projection readability.
- `run_diagram_workflow.py`: single-job engine router (also exposes
  `run_renderer_spec_workflow` for the in-process batch path).
- `analytic_diagram_workflow.py`: coordinate/function diagram branch
  (`run_analytic_workflow` runs in-process from the batch runner).
- `spatial_diagram_workflow.py`: solid-geometry branch that validates 3D
  conditions and preserves `points3d` for the TikZ compiler.
- `spatial_geometry.py`: deterministic plane/line geometry, plane-intersection
  derivation, projection profiles, and readability metrics.
- `render_geometry_spec.py`: deterministic TikZ compiler (`render_geometry_spec`
  runs in-process from the batch runner); writes the bindable
  `rendered/<variant>.fragment.tex` plus optional preview files.
- `tikz_renderer/`: typed compiler modules for synthetic, spatial, and
  coordinate/function render specs. Spatial output uses either a textbook
  oblique TikZ coordinate basis or `tikz-3dplot`.
- `geometry_diagram_workflow/`: local Codex SDK + Wolfram GeometricScene
  workflow branch for synthetic geometry.
- `build_diagram_artifacts.py`: debug dump for renderer bindings; no longer a
  required production step.

Synthetic geometry generation uses the local Codex SDK, started with
`geometry_diagram_workflow/` as its working directory. The Wolfram/GeometricScene
skills live under `geometry_diagram_workflow/.codex/skills`; the old
`geometry_diagram_workflow/.opencode` path and DashScope/OpenAI-compatible
provider path are not fallbacks for this branch. Install the workflow
dependencies from `geometry_diagram_workflow/requirements.txt`.
