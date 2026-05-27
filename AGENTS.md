# Repository Agent Notes

## Geometry Diagram Workflow

Use the repository-local diagram virtual environment, not the system Python:

```bash
.venv-diagram/bin/python scripts/geometry_diagram_workflow/examples/verify_setup.py
.venv-diagram/bin/python scripts/build_diagram_request.py ...
.venv-diagram/bin/python scripts/run_diagram_workflow.py ... --python .venv-diagram/bin/python ...
.venv-diagram/bin/python scripts/render_geometry_spec.py ...
```

The system `python3` may not have `openai` or `wolframclient` installed. The checked workflow environment is:

```text
/Users/gaochong/develop/teaching_skills/.venv-diagram/bin/python
```

Before inserting geometry `diagram_col`, `diagram_row`, or `answer_space.diagram_col` fields into assignment YAML, verify the workflow with:

```bash
.venv-diagram/bin/python scripts/geometry_diagram_workflow/examples/verify_setup.py
```

For function graphs, do not force the geometry `GeometricScene` workflow unless a dedicated function-graph renderer exists. Use a deterministic graph-rendering path such as `wolframscript` and record the generation script in the artifact directory.
