# Diagram Human Review Test Contract v0.1

Status: revised after contract audit; approved working contract for the user-requested human-in-the-loop change.

## State model

`unreviewed -> accepted` does not run the Agent and is legal only when the current candidate Round has `audit_result.status == "pass"`. `unreviewed|revision_completed|revision_failed -> queued -> revision_running -> revision_completed|revision_failed` happens only after a human submits non-empty advice. A queued/running revision rejects a different second submission.

Current state is stored at `build/diagram/jobs/<job_id>/human_review.json`; every accepted or change-requested action is also stored immutably at `human_reviews/<review_id>.json`, and revision input at `<review_id>.request.json`. Writes use a temporary sibling followed by `Path.replace()`. A process-local job lock serializes round allocation and writes. On server restart, a persisted `queued`/`revision_running` state without a live local task becomes `revision_failed` with an interruption message rather than being silently relaunched.

```json
{
  "schema_version": "diagram-human-review/v1",
  "action_id": "client-stable-id",
  "review_id": "review_0001",
  "job_id": "q2-solution",
  "decision": "accepted | changes_requested",
  "status": "accepted | queued | revision_running | revision_completed | revision_failed",
  "feedback": "human-authored text",
  "base_round": 0,
  "requested_round": 1,
  "deterministic_audit": "pass | block | missing",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601",
  "message": ""
}
```

The same `action_id` is idempotent and returns its original record without a second runner call. A newly allocated revision round is always `max(existing round directories) + 1`. Human feedback is JSON input only: it must never be interpolated into shell commands, paths, or tool arguments. Agent writes remain restricted to the target job directory.

| ID | Behavior contract | Test expectation | Initial state |
|---|---|---|---|
| DHR-01 | `DiagramEngineOptions.max_retries` defaults to `0`; an explicit positive value remains opt-in. | Contract test checks default 0 and explicit 1. | RED |
| DHR-02 | With zero retries the Agent generates one named round, runs deterministic audit, never opens the new preview for self-review, and either finalizes or fails. | Prompt test asserts one attempt, fixed start index, no visual-review instruction, and no repair instruction. | RED |
| DHR-03 | A human revision carries feedback, `base_round`, and `requested_round`; it also forces `max_retries=0`. | Request/prompt test validates typed round fields and feedback rendering. | RED |
| DHR-04 | Accepting a machine-audit-passed candidate persists immutable/current `accepted` records and never invokes the runner; blocked/missing audit cannot be accepted. | API test checks accepted, conflict, history, and zero calls. | RED |
| DHR-05 | Empty advice is rejected; valid advice atomically allocates `max(rounds)+1`, persists before one background call, and forces no retries. | API test checks validation, record/request fields, and exactly one call. | RED |
| DHR-06 | Repeating an `action_id` is idempotent; a different action while queued/running conflicts even under concurrent submission. | Store/API test checks one history record, one round allocation, and one runner call. | RED |
| DHR-07 | Completion/failure updates current and immutable records; job detail exposes review state; stale running state recovers as interrupted failure after restart. | Service/scanner test checks all three transitions. | RED |
| DHR-08 | Folder/job traversal is rejected and feedback never participates in commands or paths. | API escape test plus injected-runner argument assertion. | RED |

## Source alignment

- Retry default: `scripts/diagram_workflow/diagram_contracts.py:854`.
- Runtime fallback: `scripts/diagram_workflow/geometry_diagram_workflow/core/tools.py:195`.
- Agent visual review/repair loop: `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_prompt.py:53`.
- Finalize audit gate: `scripts/diagram_workflow/geometry_diagram_workflow/core/tools.py:978`.
- Existing monitor GET boundary: `scripts/diagram_monitor/server.py:41`.
- Existing safe path resolver: `scripts/diagram_monitor/scanner.py:31`.

## Mock policy

- Unit/API tests inject a revision runner; they do not start Codex or Wolfram.
- A focused prompt test protects the one-round semantics.
- Live Agent/Wolfram execution remains an explicit manual smoke because it is slow and externally dependent.
