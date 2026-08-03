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

## Shell Environment / API Keys

The agent's Bash tool runs a **non-interactive** shell, which does NOT load
`~/.zshrc`. API keys (`MIMO_API_KEY`, `DASHSCOPE_API_KEY`, `ZHIPUAI_API_KEY`,
etc.) are defined there and will be **missing** unless explicitly loaded.

- Before running any script that calls MiMo / BaiLian / GLM APIs, prefix the
  command with `source ~/.zshrc 2>/dev/null` in the same shell invocation:
  ```bash
  source ~/.zshrc 2>/dev/null
  ./.venv/bin/python scripts/question_transcription/observe_docx_pages.py ...
  ```
- For a one-liner: `source ~/.zshrc 2>/dev/null && ./.venv/bin/python <script>`.
- Verify a key is present before a long batch run:
  `[ -n "$MIMO_API_KEY" ] && echo OK || echo MISSING`.
- Never ask the user for an API key value. Never print or log key contents.
- If a key is genuinely unset (not just unloaded), stop and report it; do not
  invent fallbacks.

## Langfuse Tracing (question-ingestion workflow)

The LangGraph question-ingestion workflow (`run_live_paper.py` and the page-text
/ whole-paper adapters) is observable in a self-hosted Langfuse via the official
Langfuse Python SDK v4. A local Langfuse stack runs in Docker (web on
`http://localhost:3000`; see `tmp/langfuse/docker-compose.yml`).

- **Configuration is environment-only** (no CLI flags). Three variables, all
  required to enable tracing; absent any one and the run is untraced:
  ```bash
  export LANGFUSE_BASE_URL="http://localhost:3000"
  export LANGFUSE_PUBLIC_KEY="pk-lf-..."
  export LANGFUSE_SECRET_KEY="sk-lf-..."
  ```
  Put them in `~/.zshrc` alongside the model API keys and load with
  `source ~/.zshrc 2>/dev/null`. `LANGFUSE_HOST` is accepted as a legacy
  fallback for `LANGFUSE_BASE_URL` at read time, but `LANGFUSE_BASE_URL` is the
  standard.
- **Three-state gating**: all three unset → tracing silently off; only some set
  → off with a warning that config is incomplete; all three set but the
  `langfuse` package import fails → hard `RuntimeError` (never silent — a broken
  install must surface, not produce a silent no-trace run).
- **What is traced automatically**: each LangGraph node (via the Langfuse
  LangChain `CallbackHandler` injected through `config["callbacks"]`), wrapped
  in one root `paper-ingestion` span per run. Native model calls are traced as
  nested `generation` observations: `qwen-ocr` / `mimo-ocr` (page text) and
  `whole-paper-transcribe` (the only one carrying real token `usage_details`,
  from pydantic-ai).
- **What is NOT uploaded**: the wrapper's `mask_otel_spans` hook truncates and
  redacts the large `input`/`output` and `gen_ai.*` attributes; bare base64
  blobs are replaced with `<base64 blob redacted>`. Note: true
  `data:<ct>;base64,...` URIs are converted by Langfuse to media references, so
  page images may still be stored in Langfuse's media backend (acceptable for
  self-hosted; if images must never leave the host, replace them with
  placeholders before entering the callback path).
- **Flushing**: `run_live_paper` calls `lf.flush()` in a `finally` block so a
  short-lived CLI process drains its trace queue before exit. Flush failures are
  logged, never raised over a real workflow/model error.
- Business code imports `scripts.question_transcription.workflow.observability.langfuse`
  only — never `langfuse` or `opentelemetry` directly.

## Diagram Workflow Rules

- Do not tell math YAML writers to avoid `diagram_slot` when a geometry problem needs a figure. If the stem says “如图/图中/下图”, or if a geometry condition would be hard to parse without a figure, the writer must declare a `diagram_slot`.
- Adding or repairing diagrams means returning to the relevant latex-data writer and regenerating `*.plan.assignment.yaml`. Do not mechanically convert ordinary `*.assignment.yaml` into plan YAML with inline scripts.
- Plan YAML must contain only `diagram_slot` declarations for figures. It must not contain final `image_path`, `diagram_col`, `diagram_row`, `diagram_job_id`, or hand-written TikZ payloads.
- Ordinary Euclidean geometry, including triangles, parallel lines, similarity, and collinear segment ratios, defaults to `engine: geometric_scene` with `diagram_kind: synthetic_geometry`.
- Use `diagram_kind: coordinate_geometry` only for coordinate planes, axes/ticks, function graphs, explicit coordinate or analytic geometry, or graph-reading tasks.
- Solid geometry involving spatial point-line-plane relations, polyhedra, dihedral angles, skew lines, sections, or spatial distances uses `engine: spatial_renderer` with `diagram_kind: spatial_geometry`.
- Spatial plan specs keep `points3d` through the final renderer spec. Do not pre-project them into 2D `points`; the TikZ compiler selects `textbook_oblique`, `hinge_planes`, `orthographic_3d`, or `axial_solid`.
- Spatial prompt diagrams may use `main`, `secondary`, `intersection`, and `hidden` roles, but not `auxiliary`. Solution spatial diagrams must reuse the prompt geometry before adding auxiliary objects.
