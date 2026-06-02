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
