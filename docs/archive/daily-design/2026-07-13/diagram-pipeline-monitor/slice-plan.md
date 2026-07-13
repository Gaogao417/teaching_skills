# Diagram Pipeline Monitor Slice Plan

## Source truth

- `artifacts/**/build/diagram/diagram_jobs.json`: assignment job manifest.
- `artifacts/**/build/diagram/diagram_batch_report.json`: batch summary, treated as advisory because it can be stale.
- `artifacts/**/build/diagram/jobs/<job_id>/workflow_events.jsonl`: live event stream.
- `artifacts/**/build/diagram/jobs/<job_id>/workflow_result.json`: finalized workflow state and Wolfram result.
- `artifacts/**/build/diagram/jobs/<job_id>/renderer_result.json`: TikZ and preview output state.
- `artifacts/**/build/diagram/jobs/<job_id>/rounds/round_*`: per-round inputs, previews, audits, and logs.
- `artifacts/**/build/diagram/pipeline_performance.json` and per-job `performance_profile.json`: timing data.

## Current state and gaps

- Diagram artifacts are inspectable on disk but there is no searchable monitor UI.
- Batch reports can disagree with finalized job outputs, so effective status must be derived from multiple files.
- Intermediate rounds and preview images exist but are difficult to compare while a pipeline is running.
- Existing review UIs establish a local FastAPI plus plain HTML/CSS/JS pattern that can be reused without changing the diagram pipeline.

## Out of scope

- Starting, stopping, retrying, deleting, or editing pipeline jobs.
- Mutating assignment YAML or generated diagram artifacts.
- Replacing existing pipeline status contracts.
- Remote hosting or access outside the local repository.

## Steps

| Step | Do | Mode | Depends on | Can run with | Locks / owner | Next role |
|---|---|---|---|---|---|---|
| step1 | Freeze source index, effective-status rules, and visual contract | serial | none | none | design docs / contract designer | visual-test-writer |
| step2 | Write backend behavior and visible-layout tests | serial | step1 | none | monitor tests / visual-test-writer | implementation-agent |
| step3 | Implement read-only scanner and API | serial | step2 | none | monitor Python package / implementation-agent | implementation-agent |
| step4 | Implement three-pane UI, refresh, previews, timeline, and artifact viewer | serial | step3 | none | monitor static files / implementation-agent | visual reviewer |
| step5 | Run tests and inspect the live page against proportion-line artifacts | serial | step4 | none | verification only / visual reviewer | final handoff |

## Gate ledger seed

- Search matches artifact directory names and sorts by newest descendant activity time.
- Effective job status detects pending, running, stalled, failed, incomplete, succeeded, and conflict states.
- A successful job requires workflow, Wolfram, renderer, audit, and preview evidence rather than a single report value.
- The desktop layout exposes folder list, job board, and job detail simultaneously.
- Round previews, event history, intermediate artifacts, and errors remain reachable without filesystem navigation.
- The server is read-only and rejects paths outside configured artifact roots.

