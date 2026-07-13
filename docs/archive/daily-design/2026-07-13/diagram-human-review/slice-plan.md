# Diagram Human Review Slice Plan

## Source truth

- `scripts/diagram_workflow/diagram_contracts.py`: job request and retry defaults.
- `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_prompt.py`: Agent round and review behavior.
- `scripts/diagram_monitor/server.py`: local monitor API boundary.
- `scripts/diagram_monitor/scanner.py`: job detail evidence returned to the UI.
- `scripts/diagram_monitor/static/monitor.js`: existing job-detail interaction surface.

## Current gaps

- `max_retries` defaults to 3 and the prompt asks the Agent to visually review every candidate.
- The monitor is read-only, so a human cannot accept a diagram or send concrete revision advice.
- A revision has no typed way to name its base round or force exactly one new round.

## Out of scope

- Automatic approval, automatic repeated revision, editing TikZ by hand, or mutating assignment YAML.
- Human review for non-`geometric_scene` routes in this slice.
- Replacing deterministic audit or preview generation.

| Step | Do | Mode | Depends on | Can run with | Locks / owner | Next role |
|---|---|---|---|---|---|---|
| step1 | Freeze retry, human-review, and revision request contracts | serial | none | none | design docs | test writer |
| step2.1 | Write diagram request/prompt behavior tests | parallel | step1 | step2.2 | diagram workflow tests | implementation |
| step2.2 | Write review API and visible-state tests | parallel | step1 | step2.1 | monitor tests | implementation |
| step3 | Implement typed one-round revision and review persistence/API | serial | step2.1, step2.2 | none | Python workflow/server | frontend implementation |
| step4 | Add review panel to existing Job overview | serial | step3 | none | monitor JS/CSS | verification |
| step5 | Run focused regressions and browser acceptance | serial | step4 | none | verification only | handoff |

## Gate ledger seed

- Omitted `max_retries` means zero Agent self-review/repair rounds.
- Deterministic audit remains mandatory before any generated round is finalized.
- Human advice names the selected base round and exactly one requested next round.
- `accepted` never starts an Agent; `changes_requested` starts only after an explicit button action.
- Review files remain inside the selected job directory and all folder/job paths are validated.
- The existing preview remains visible while revision status updates through auto-refresh.
