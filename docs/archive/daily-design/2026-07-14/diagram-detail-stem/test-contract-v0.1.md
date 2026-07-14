# Diagram detail stem data contract v0.1

Status: `pending-audit`. This contract covers one backend data step only. It does not authorize test or production edits.

## Scope and outcome

`GET /api/job?folder=<folder>&job_id=<job_id>` must always return a top-level `stem_latex` string for the selected job. Its only source is that exact job directory's `request.json.problem_context.stem_latex`.

If the source is absent, unreadable, malformed, structurally invalid, or not a string, the API returns `"stem_latex": ""` and continues returning the rest of the job detail normally. The scanner must not infer, reconstruct, or copy a stem from an assignment YAML, manifest, batch report, `teaching_request.json`, another job, another variant, or any generated result file.

This step does not define visual placement, LaTeX rendering, MathJax behavior, or an empty-state message. Those belong to the separate frontend step.

## Data contract

For the selected job directory:

```text
<artifact>/build/diagram/jobs/<job_id>/request.json
  -> problem_context (must be an object)
    -> stem_latex (must be a string)
```

The job-detail response adds:

```json
{
  "stem_latex": "如图，在 $\\triangle ABC$ 中……"
}
```

Rules:

1. A valid string is returned verbatim, including LaTeX backslashes, newlines, punctuation, and intentional leading/trailing whitespace. The backend does not render, sanitize, trim, or normalize it.
2. Missing `request.json`, file read/UTF-8/JSON failure, a non-object JSON root, missing or non-object `problem_context`, missing `stem_latex`, or a non-string `stem_latex` all map to the stable empty string `""`.
3. These source-content failures are data absence, not endpoint failures: an otherwise valid folder/job still returns HTTP 200 and its existing detail fields.
4. Existing folder/job path validation and 404/400 behavior remain unchanged. An unknown job is not converted into an empty-stem success.
5. The response field is always present for a successfully resolved job detail, including manifest-only jobs whose job directory is absent.

## Test rows

| ID | Behavior under test | Required observable assertion | Initial state |
|---|---|---|---|
| DDS-01 | Valid stem is exposed by scanner and API. | Seed the selected job's `request.json.problem_context.stem_latex` with multiline LaTeX and assert `scanner.job_detail(...)["stem_latex"]` and `/api/job` return the exact string verbatim. | RED |
| DDS-02 | Source identity is exact-job and exact-file. | Give the selected job a unique stem while assignment YAML, `teaching_request.json`, and a sibling prompt/solution job contain different decoy stems; assert only the selected job's `request.json` value is returned. | RED |
| DDS-03 | Missing source shapes have a stable empty value. | Cover missing `request.json`, missing `problem_context`, and missing `stem_latex`; each successful detail response includes `"stem_latex": ""`. | RED |
| DDS-04 | Wrong JSON types never leak or stringify. | Cover non-object JSON root, non-object `problem_context`, and number/list/object/bool/null `stem_latex`; each returns the empty string, never `str(value)`. | RED |
| DDS-05 | Malformed/unreadable request content is non-fatal. | Invalid JSON and invalid UTF-8 produce HTTP 200 with `stem_latex == ""`; existing job metadata remains available. | RED for stable field; GREEN for non-throwing `_read_json` behavior |
| DDS-06 | Existing lookup/error semantics remain intact. | Existing rounds/events/artifact groups remain unchanged; unknown job and path escape retain their existing 404/400 behavior. | GREEN |
| DDS-07 | Detail pane presents the returned stem. | Separate frontend tests/browser smoke verify visible placement and readable LaTeX treatment; no backend fallback is introduced to compensate for UI behavior. | DEFERRED to frontend step |

## RED / GREEN / DEFERRED ledger

| State | Rows | Meaning for this step |
|---|---|---|
| RED | DDS-01 through DDS-04; stable-field portion of DDS-05 | The scanner currently reads `request.json` for summary metadata but does not expose a `stem_latex` field in job detail. |
| GREEN | Existing safe-read portion of DDS-05; DDS-06 | `_read_json` already converts missing/read/decode/JSON/non-object-root failures to `{}`, and existing detail/error behavior is protected. |
| DEFERRED | DDS-07 | This backend step supplies data only. Detail-pane markup, rendering, and responsive visual verification require the frontend contract and its own allowed scopes. |

## Mock policy

- Use temporary artifact trees and real `DiagramArtifactScanner` / FastAPI `TestClient`; do not mock `_read_json`, filesystem reads, or the `/api/job` pass-through.
- Fixtures may write exact bytes for malformed JSON and invalid UTF-8. No network, Codex SDK, Wolfram, renderer, or real user artifacts are needed.
- Decoy-source coverage must use clearly distinct sentinel strings so accidental fallback cannot satisfy the assertion.
- Do not parse assignment YAML in production or tests to manufacture the expected API value.

## Source alignment

- `scripts/diagram_monitor/scanner.py:28-36`: `_read_json` already provides the required safe read boundary for missing files, I/O errors, invalid UTF-8, malformed JSON, and non-object roots.
- `scripts/diagram_monitor/scanner.py:178-216`: `job_detail` is the authoritative composition point for one selected job and already has the canonical `job_dir`; it is the narrow place to attach the stable top-level field.
- `scripts/diagram_monitor/scanner.py:302-315`: `_job_summary` currently reads the selected job's `request.json`, but only uses it for engine/variant/diagram metadata. It must not broaden source lookup to assignments or siblings.
- `scripts/diagram_monitor/server.py:77-86`: `/api/job` passes scanner detail through and only appends `human_review`; no server edit is required for the new field.
- `scripts/diagram_workflow/diagram_contracts.py:750-754` and `:893`: `DiagramProblemContext.stem_latex` is a string field nested under a diagram job request's `problem_context`, matching real generated request files.
- `scripts/diagram_workflow/run_diagram_batch.py:172-206` and `:216-231`: collect/batch constructs the request's problem context from the owning problem/block; monitor code should consume that persisted request rather than revisit upstream assignments.
- `tests/test_diagram_monitor.py:89-102`: nearest direct scanner job-detail seam for preserving rounds, events, and artifact groups.
- `tests/test_diagram_monitor.py:112-138`: nearest real `/api/job` TestClient seam and existing path-safety assertions.
- `tests/test_diagram_monitor.py:1070-1154`: the common artifact fixture writes each job's `request.json` and can be extended locally with `problem_context.stem_latex` or specialized malformed-content cases.

## Downstream required constraints

`required_constraints`:

1. Contract audit approval is required before test edits; test audit approval is required before production edits.
2. Test edits are limited to `tests/test_diagram_monitor.py`.
3. Production edits are limited to `scripts/diagram_monitor/scanner.py`. `server.py`, assignment readers, diagram workflow code, artifacts, and frontend files are out of scope for this step.
4. Add a top-level `stem_latex` field to every successful `job_detail` result. Its value type is always `str`.
5. Read only `<selected job_dir>/request.json.problem_context.stem_latex`; do not search parents, siblings, rounds, prompt/solution counterparts, assignments, manifests, reports, `teaching_request.json`, or output/result files.
6. Preserve valid string content verbatim. Do not trim, normalize, concatenate `subquestion_latex`, render LaTeX, escape HTML, or stringify non-string values in the backend.
7. Map every missing/invalid source shape enumerated in the data contract to `""` without raising and without suppressing otherwise valid job detail.
8. Reuse the existing safe JSON read boundary or an equivalently narrow helper; do not introduce permissive YAML parsing, recursive lookup, or exception swallowing outside request extraction.
9. Preserve existing unknown-job/path-escape errors, folder summaries, status reconciliation, rounds/events/artifact groups, review metadata, and artifact enumeration behavior.
10. Tests must prove both direct scanner behavior and real `/api/job` pass-through with temporary files; do not satisfy the contract by mocking the scanner return or server endpoint.
11. Run `./.venv/bin/python -m pytest tests/test_diagram_monitor.py -q` after implementation and leave unrelated dirty changes untouched.
