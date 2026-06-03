# Repository Agent Notes

## Git Commit Message Rules

Commit messages must start with a square-bracket category tag:

```text
[artifacts] <student>/<topic>: <summary>
[documents] <scope>: <summary>
[workflow] <scope>: <summary>
```

Use the categories this way:

- `[artifacts]` for generated student-facing homework/lesson artifacts under `artifacts/`.
- `[documents]` for source-document collection under `documents/`: downloaded article assets, OCR inputs/outputs, WeChat archives, topic extracts.
- `[workflow]` for skills, scripts, templates, tests, validators, renderers, engineering design docs (e.g. `docs/diagram-*.md`), Pydantic contracts, and repository tooling.

Keep different categories in separate commits. For example, do not mix a generated homework artifact with a renderer or skill change in the same commit.

## Diagram Workflow Closeout Rules

When working on the synthetic geometry diagram workflow, the most important
acceptance rule is: do not prove the workflow by mocks alone. The implementation
must run the real chain and produce real image files.

Required checks before calling the workflow closed:

- Run the real S2.5-S2.9 chain: `collect_diagram_jobs.py -> run_diagram_batch.py -> build_diagram_artifacts.py -> check_diagram_gate.py -> resolve_assignment_diagrams.py`.
- Confirm `run_diagram_batch.py` actually invokes the local geometry workflow and renderer, not only dry-run/request generation.
- Confirm each successful job has:
  - `workflow_result.json` with `status: ok`
  - `final_renderer_spec.json`
  - `renderer_result.json` with `status: ok`
  - a non-empty PNG under `rendered/`
  - a bindable artifact with a `sha256:` hash in `diagram_artifacts.json`
- Do not mark the work complete if the e2e path only uses fake artifacts, mocked renderer output, or manually inserted `image_path` values.
- Verify that production code only uses the v2 request path:
  - `DiagramJobRequest v2` should be the production input to the workflow.
  - `run_diagram_batch.py` should write and call only per-job `request.json`.
- Keep analytic geometry/function graph work out of this closeout unless the task explicitly targets that branch. Synthetic geometry closeout should stay focused on `engine: geometric_scene` and `diagram_kind: synthetic_geometry`.
