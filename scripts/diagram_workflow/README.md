# Diagram Workflow Scripts

This directory contains the active diagram generation workflow used by
`math-geometry-diagram-renderer`.

Primary entry point:

```bash
python3 scripts/diagram_workflow/run_assignment_diagrams.py <plan.assignment.yaml>
```

Pipeline order:

```text
collect_diagram_jobs.py
run_diagram_batch.py
check_diagram_gate.py
resolve_assignment_diagrams.py
```

Supporting modules:

- `diagram_contracts.py`: Pydantic contracts for slots, jobs, renderer
  bindings, gates, requests, and renderer results.
- `renderer_bindings.py`: shared loader that reads `diagram_jobs.json` plus
  per-job `renderer_result.json` and produces the bindable TikZ facts consumed
  by gate and resolver.
- `run_diagram_workflow.py`: single-job engine router.
- `analytic_diagram_workflow.py`: coordinate/function diagram branch.
- `render_geometry_spec.py`: deterministic TikZ compiler; writes the bindable
  `rendered/<variant>.fragment.tex` plus optional preview files.
- `tikz_renderer/`: typed compiler modules for synthetic geometry and
  coordinate/function render specs.
- `geometry_diagram_workflow/`: local GeometricScene workflow branch.
- `build_diagram_artifacts.py`: debug dump for renderer bindings; no longer a
  required production step.
