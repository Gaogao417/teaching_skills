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
- `[workflow]` also covers skill-trace schema work, review UI, scripts, database migrations, and Codex skill integration.
- `[artifacts]` also covers generated reviewed traces and demo outputs.

Keep different categories in separate commits. For example, do not mix a generated homework artifact with a renderer or skill change in the same commit.

## Python Environment Rules

Use explicit virtualenv interpreters instead of the system `python3` when running repository scripts.

- General repository tooling, Pydantic contracts, model rule scripts, and skill-trace ingestion use `./.venv/bin/python`.
- Run Python tests through `./.venv/bin/python -m pytest ...`.
- Geometry diagram workflow and live renderer work use `./.venv-diagram/bin/python` unless the task explicitly targets non-diagram tooling.
- Before adding or changing Pydantic contracts, verify the selected environment can import Pydantic.

## Diagram Workflow Rules

- Do not tell math YAML writers to avoid `diagram_slot` when a geometry problem needs a figure. If the stem says “如图/图中/下图”, or if a geometry condition would be hard to parse without a figure, the writer must declare a `diagram_slot`.
- Adding or repairing diagrams means returning to the relevant latex-data writer and regenerating `*.plan.assignment.yaml`. Do not mechanically convert ordinary `*.assignment.yaml` into plan YAML with inline scripts.
- Plan YAML must contain only `diagram_slot` declarations for figures. It must not contain final `image_path`, `diagram_col`, `diagram_row`, `diagram_job_id`, or hand-written TikZ payloads.
- Ordinary Euclidean geometry, including triangles, parallel lines, similarity, and collinear segment ratios, defaults to `engine: geometric_scene` with `diagram_kind: synthetic_geometry`.
- Use `diagram_kind: coordinate_geometry` only for coordinate planes, axes/ticks, function graphs, explicit coordinate or analytic geometry, or graph-reading tasks.
- Solid geometry involving spatial point-line-plane relations, polyhedra, dihedral angles, skew lines, sections, or spatial distances uses `engine: spatial_renderer` with `diagram_kind: spatial_geometry`.
- Spatial plan specs keep `points3d` through the final renderer spec. Do not pre-project them into 2D `points`; the TikZ compiler selects `textbook_oblique`, `hinge_planes`, `orthographic_3d`, or `axial_solid`.
- Spatial prompt diagrams may use `main`, `secondary`, `intersection`, and `hidden` roles, but not `auxiliary`. Solution spatial diagrams must reuse the prompt geometry before adding auxiliary objects.
