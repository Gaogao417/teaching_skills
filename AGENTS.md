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
