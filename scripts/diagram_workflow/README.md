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
build_diagram_artifacts.py
check_diagram_gate.py
resolve_assignment_diagrams.py
```

Supporting modules:

- `diagram_contracts.py`: Pydantic contracts for slots, jobs, artifacts, gates,
  requests, and renderer results.
- `run_diagram_workflow.py`: single-job engine router.
- `analytic_diagram_workflow.py`: coordinate/function diagram branch.
- `render_geometry_spec.py`: deterministic SVG/PNG renderer.
- `geometry_diagram_workflow/`: local GeometricScene workflow branch.

