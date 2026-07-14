# Diagram Human Review Persistent Codex Thread Test Contract v0.1

Status: revised after auditor `REQUEST_CHANGES`; ready for contract re-audit. This archived contract covers exactly one step and does not authorize test or production edits.

## Scope and outcome

When a human clicks `提交给 Agent` with non-empty revision feedback, that explicitly requested diagram revision runs as one persistent, user-source Codex thread in the user's real `CODEX_HOME`. The thread therefore participates in Codex's normal persisted task index and can appear as a normal task in the Codex app after the app refreshes its task list.

This step does not change the `接受当前图` path, ordinary initial/batch diagram generation, the monitor's visual design, or the revision algorithm. One submission still authorizes exactly one new Round and one Agent turn. The Agent does not review its own output, resume itself, create follow-up turns, or retry autonomously.

## State and persistence contract

The existing review transition remains:

`unreviewed | revision_completed | revision_failed -> queued -> revision_running -> revision_completed | revision_failed`

For `decision == "changes_requested"`, the canonical `diagram_request.human_revision` marker selects persistent-thread execution. That execution must:

1. resolve the real Codex home from the inherited `CODEX_HOME`, falling back to `Path.home() / ".codex"` when unset;
2. pass that same home to the Codex SDK without creating, copying into, or deleting a temporary Codex home;
3. start the thread with `ephemeral=False` and `thread_source=ThreadSource.user`;
4. call `thread.set_name(...)` exactly once with a concise deterministic name such as `几何图修订 · <job_id> · Round <requested_round>` before starting the turn, so the app task is recognizable; the name is length-bounded and never contains human feedback;
5. retain the existing approval, sandbox, cwd, model, skill inputs, output schema, and single-turn behavior; and
6. let the Codex SDK own all session/index writes. Repository code must never insert into or update Codex's SQLite databases, `session_index.jsonl`, or rollout files directly.

Ordinary diagram generation without `human_revision` remains isolated and ephemeral. This prevents a 60-image batch from adding 60 normal app tasks and keeps this behavior tied to the user's explicit button click.

Once the SDK has created a thread, its non-empty ID is invocation-owned output. `human_review.json` and `human_reviews/<review_id>.json` must both carry:

```json
{
  "agent_thread_id": "019f..."
}
```

The field is optional only before the SDK reports a thread ID or when thread creation itself fails. If a thread was created, its ID must remain on the review record whether the diagram revision later completes or fails. A stale `agent_result.json`, `workflow_result.json`, or earlier review's thread ID is never valid evidence for the current invocation. Replaying the same `action_id` returns the same record and thread ID without opening another thread.

Persistence of `agent_thread_id` is metadata only. It does not authorize resuming the thread, posting a second turn, changing Round allocation, or treating thread creation as diagram success.

## Invocation-owned metadata propagation

Thread identity must travel through an explicit machine-readable sidecar, not through exception text, “latest thread” lookup, an unkeyed event scan, or an arbitrary pre-existing result file. The authoritative sidecar is written at `human_reviews/<review_id>.codex-task.json`:

```json
{
  "schema_version": "diagram-codex-task/v1",
  "review_id": "review_0001",
  "agent_thread_id": "019f...",
  "created_at": "ISO-8601"
}
```

For non-human initial/batch work, no sidecar is written. For a human revision, `review_id` comes only from the validated `DiagramHumanRevision`; it must equal the outer revision request, filename, sidecar payload, and current review record before the service accepts the metadata. Review history enumeration must explicitly distinguish `review_0001.json`, `review_0001.request.json`, and `review_0001.codex-task.json`; the sidecar is metadata, not another review action.

The propagation chain is mandatory:

1. **Agent worker:** receive the canonical job `out_dir` and validated `review_id`. Immediately after a successful `thread_start` and before `thread.set_name` or `thread.turn`, atomically write the sidecar with the non-empty returned ID. Therefore `set_name`, turn/stream, artifact-validation, and post-start timeout failures cannot erase the identity. SDK/config/thread-start failure writes no sidecar.
2. **Agent parent and core workflow:** keep using the same canonical `out_dir`. They are transport-transparent for the sidecar: they must not overwrite, delete, move, synthesize, or clean it on success, failure, timeout, artifact validation, or rollback. Successful result payloads may continue to carry `agent_thread_id`, but they are not authoritative for human-review persistence.
3. **Outer wrapper:** keep the same job `out_dir` through the child invocation and remain transport-transparent. It must not infer identity from `agent_result.json`, `workflow_result.json`, the latest global Codex task, or an unkeyed event. Existing fresh-result rules still govern diagram status and diagnostics independently of the sidecar.
4. **HumanReviewService:** after the runner returns or raises, read only `human_reviews/<current review_id>.codex-task.json`. Accept its ID only when the filename/payload/request/current-record review IDs all match, then persist it through the same atomic current/history path before the terminal status update. Diagram success/failure and Round mutation handling remain independent.

If any key comparison fails, the service discards the sidecar and records the current diagnostic without an `agent_thread_id`. A missing/empty sidecar never falls back to an earlier file. Once a matching ID is persisted, later status updates and rollback cannot clear or replace it. Sidecars are append-once identity evidence: an existing same-review sidecar with different content is a conflict, not an overwrite opportunity.

## Test rows

| ID | Behavior under test | Required observable assertion | Initial state |
|---|---|---|---|
| DHRCT-01 | A typed human revision selects a normal persisted Codex task. | The worker policy uses inherited/fallback real `CODEX_HOME`, `ephemeral=False`, and `ThreadSource.user`; no temporary Codex home is created, copied into, or removed. | RED |
| DHRCT-02 | Ordinary initial/batch generation remains isolated. | A request without `human_revision` retains the existing temporary-home and ephemeral-thread policy; persistent behavior is not a global default. | GREEN, with new regression coverage required |
| DHRCT-03 | Persistent execution preserves the established Agent turn contract and gives the app task a stable name. | Fake-SDK assertions retain `ApprovalMode.deny_all`, `Sandbox.full_access`, repository cwd, configured model, supplied skills, output schema, and exactly one `thread_start`, one bounded `set_name`, plus one `turn`; the name identifies job/requested Round and excludes feedback; no resume/follow-up API is called. | RED |
| DHRCT-04 | A successful revision persists its invocation-owned thread ID only from the keyed sidecar. | A runner fixture atomically creates `human_reviews/<current review_id>.codex-task.json` with `thread-current`, creates the requested Round, and returns a successful result with no `agent_thread_id` (or a deliberately different ignored value). The service produces `revision_completed`; current and matching history records both contain exactly the sidecar's `thread-current`. | RED |
| DHRCT-05 | A created thread remains traceable through every post-thread failure boundary. | Call the real `_codex_agent_worker` in process with a fake SDK and canonical out-dir/review ID; force `thread.set_name` and turn failures and assert the keyed sidecar already contains `thread-current`. Then exercise real `HumanReviewService.run_revision` terminal handling for raised timeout/failure and failed result/artifact-validation shapes without injecting an `agent_thread_id`; both review records end failed with exactly the sidecar ID. | RED |
| DHRCT-06 | Pre-thread and stale metadata never acquire a thread ID. | Call the real worker in process with fake SDK/config and `thread_start` failures and assert no current sidecar. Preseed `review-old.codex-task.json` with `thread-old`, plus stale agent/workflow results; exercise real service terminal handling for `review-current`. Both new review records omit `agent_thread_id`. A current filename with a mismatched payload `review_id` is rejected. | RED |
| DHRCT-07 | Idempotency prevents duplicate visible tasks. | Replaying the same `action_id` returns its original `review_id` and `agent_thread_id`; runner and fake SDK observe one invocation/thread only. A different action while queued/running still conflicts. | GREEN for submission conflict; RED for thread-ID assertion |
| DHRCT-08 | Acceptance never starts a Codex task. | `accepted` persists as before and runner/fake SDK calls remain zero. | GREEN |
| DHRCT-09 | Existing revision authorization remains intact. | Existing tests continue to enforce `max_retries == 0`, exactly `{requested_round}` as the only new Round, historical fingerprint rollback, partial requested-Round visibility, and ghost-Round fallback. | GREEN |
| DHRCT-10 | The persisted task is visible to the actual Codex app. | Manual smoke: click once, observe one new unarchived normal task in the app, and confirm its thread ID equals both review records; no second task appears after monitor refresh or action replay. | DEFERRED live smoke |

## RED / GREEN / DEFERRED ledger

| State | Rows | Meaning for this step |
|---|---|---|
| RED | DHRCT-01, DHRCT-03 through DHRCT-06, thread-ID part of DHRCT-07 | These fail against the current implementation because it forces a temporary `CODEX_HOME`, starts `ephemeral=True`, and does not propagate `agent_thread_id` into human-review records. |
| GREEN | DHRCT-02, acceptance part of DHRCT-08, DHRCT-09, existing conflict part of DHRCT-07 | These are retained protections. Add only the focused regression needed to prove persistent mode did not broaden into batch generation or weaken review gates. |
| DEFERRED | DHRCT-10 | Actual Codex app discovery depends on a live installed app/SDK and the user's real home. It is required manual acceptance evidence after deterministic tests pass, not a unit-test dependency. |

## Mock policy

- Unit tests must not write to the user's actual `~/.codex`, start a real Codex process, call Wolfram, open the app, or access the network.
- Test the runner policy through a pure policy helper or an in-process fake `openai_codex` module. The fake must capture `CodexConfig.env`, `thread_start` arguments, call counts, and a deterministic thread ID; it must not imitate Codex persistence by writing SQLite files.
- A temporary path may stand in for the inherited real `CODEX_HOME` in tests. The assertion is identity and non-deletion: persistent mode passes the exact supplied path through and leaves it intact.
- Human-review persistence tests use temporary artifact/job trees. DHRCT-04 may retain the injected runner seam only to create the matching sidecar and requested Round; its returned result must omit `agent_thread_id` or provide a deliberately different value that the service ignores. DHRCT-05/06 must call the real worker in process with a fake SDK and then exercise real `HumanReviewService.run_revision` sidecar consumption. Do not satisfy any persistence row by injecting a final runner dictionary containing the accepted `agent_thread_id`.
- The post-thread fixture must cover at least `set_name` failure, turn failure, raised timeout after sidecar creation, and failed result/artifact-validation shape after sidecar creation. The pre-thread fixture must cover SDK/config/thread-start failure before sidecar creation. These may be separate focused tests, but together they must prove the keyed sidecar survives or is absent across the real boundaries.
- Success, post-thread failure, and pre-thread failure fixtures use distinct IDs/messages (`thread-current`, `thread-old`, `current-turn-failed`) so stale attribution cannot pass via generic assertions.
- Keep the real `DiagramJobRequest`/`DiagramHumanRevision` validation in request tests; do not replace typed human-revision detection with a truthy arbitrary dictionary in production.
- The live acceptance smoke may read normal Codex app state to compare IDs, but it must not repair visibility by editing Codex databases or index files.

## Source alignment

- `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_runner.py:133-172`: the worker currently always creates a temporary Codex home, copies only auth/config into it, and overrides `CODEX_HOME`; this is the storage boundary that makes the resulting session unavailable to the user's normal task index.
- `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_runner.py:179-201`: the SDK thread is currently started with `ephemeral=True`; approval, cwd, model, sandbox, skills, output schema, and one-turn execution are retained source truth.
- `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_runner.py:248-270`: success returns a thread ID, while failure currently drops it and the temporary home is always deleted; this is the thread-ID durability boundary.
- `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_runner.py:273-380`: progress already emits `agent.thread.started`, and successful payloads already expose `agent_thread_id`; invocation-owned propagation should reuse these facts rather than discover an arbitrary latest task.
- `scripts/diagram_workflow/geometry_diagram_workflow/core/workflow.py:32-79`: core success/failure and artifact validation share the job `out_dir`; they must remain transport-transparent for the worker-written sidecar.
- `scripts/diagram_workflow/run_diagram_workflow.py:432-483`: the outer wrapper launches the core workflow against the same job `out_dir`; it remains transport-transparent while fresh-result handling independently controls status/diagnostics.
- Installed `openai_codex` SDK (`Codex.thread_start`, `Thread.set_name`): the verified local API supports `ephemeral`, `thread_source`, and explicit persisted task naming; `ThreadSource.user` is available in `openai_codex.generated.v2_all`.
- `scripts/diagram_monitor/human_review.py:42-113`: action-id idempotency, conflict checks, review allocation, queued persistence, and typed revision-envelope creation remain the authorization boundary.
- `scripts/diagram_monitor/human_review.py:115-171`: runner completion/failure currently updates status but does not persist runner metadata; this is the review-record propagation boundary.
- `scripts/diagram_monitor/human_review.py:189-199` and `395-402`: current/history records are updated together through atomic writes; `agent_thread_id` must use that same path.
- `scripts/diagram_monitor/human_review.py:271-315`: human revision forces `max_retries=0`, and exact-one-new-Round plus historical fingerprint validation remain mandatory.
- `scripts/diagram_workflow/diagram_contracts.py:1088-1150`: `DiagramHumanRevision` and `DiagramJobRequest` v2 are the typed source of truth for detecting a human-authorized revision.
- `tests/test_diagram_agent_progress.py:32-134`: nearest deterministic Agent-runner unit seam; it currently covers safe progress/heartbeat handling without live Codex.
- `tests/test_diagram_monitor.py:184-291`: nearest submission, idempotency, and concurrent-conflict seam.
- `tests/test_diagram_monitor.py:313-447`: nearest terminal-state, extra-Round, partial-failure, and ghost-Round regression seam.

## Downstream required constraints

`required_constraints`:

1. Contract audit approval is required before test edits; test audit approval is required before production edits.
2. Test edits are limited to `tests/test_diagram_agent_progress.py` and `tests/test_diagram_monitor.py` unless the contract auditor explicitly narrows or extends the scope.
3. Production edits are limited to `scripts/diagram_workflow/geometry_diagram_workflow/core/agent_runner.py` and `scripts/diagram_monitor/human_review.py`. Core `workflow.py` and outer `run_diagram_workflow.py` are transport-transparent and need no edit unless a failing test proves either currently deletes, moves, overwrites, or synthesizes the keyed sidecar; any such expansion requires an auditor note before implementation.
4. Persistent mode is selected only by a successfully validated `DiagramJobRequest.human_revision`. Requests without it remain ephemeral and isolated.
5. Persistent mode must use the inherited `CODEX_HOME` or the user's `~/.codex` fallback, set `ephemeral=False`, and set `thread_source=ThreadSource.user`. Never derive `CODEX_HOME` from folder, job ID, feedback, request JSON, or artifact paths.
6. Do not directly write, patch, migrate, or delete Codex's SQLite databases, `session_index.jsonl`, rollout files, or global-state files. The Codex SDK is the sole persistence writer.
7. One human action creates at most one thread, calls `thread.set_name(...)` once, and starts one turn. Use a concise bounded name derived only from trusted fixed text, `job_id`, and `requested_round`; do not include feedback. Do not call resume, send a follow-up turn, create a self-review loop, or translate a failed diagram into another Codex attempt.
8. Preserve `ApprovalMode.deny_all`, `Sandbox.full_access`, repository cwd, model selection, skill inputs, output schema, progress redaction, heartbeat behavior, and timeout behavior unless a separately approved contract changes them.
9. The worker atomically writes `diagram-codex-task/v1` to `human_reviews/<review_id>.codex-task.json` immediately after `thread_start` and before name/turn work. Core and wrapper remain transport-transparent; HumanReviewService consumes only that exact keyed sidecar after runner return or exception.
10. Persist a non-empty invocation-owned `agent_thread_id` to both current and matching history records once known, including `set_name`, turn/stream, post-start timeout, and artifact-validation failure. Pre-thread SDK/config/thread-start failure creates no sidecar and carries no ID. Never reuse a stale on-disk ID or infer the ID by selecting the latest global Codex task.
11. Require equality of sidecar filename, sidecar payload, request, and current-record `review_id` before persistence. A mismatch or empty ID is discarded, never replaced with earlier job metadata. The sidecar is append-once; once the matching ID is stored, it survives all terminal status and rollback updates.
12. Preserve action-id idempotency, queued/running conflict, `max_retries=0`, exactly-one-new-Round validation, historical Round fingerprint/rollback, partial requested-Round visibility, and ghost-Round fallback.
13. `agent_thread_id` is trace metadata, not success evidence and not authorization to mutate or resume anything. Review status remains driven by workflow result plus Round validation.
14. DHRCT-05/06 must call the real `_codex_agent_worker` in process and the real HumanReviewService sidecar-consumption/terminal path; an injected final `RevisionRunner` result carrying `agent_thread_id` is insufficient. Fake only external SDK/process outcomes, not atomic sidecar writing, keyed validation, review persistence, fingerprinting, or rollback.
15. Use `./.venv-diagram/bin/python` for SDK/diagram-runner tests and `./.venv/bin/python -m pytest tests/test_diagram_monitor.py` for monitor tests. Tests must use temporary homes/artifacts and leave the user's real Codex home untouched.
16. After deterministic suites pass, perform DHRCT-10 once with a disposable review action and compare the app-visible task ID to the persisted review ID field. Do not repeat the action merely to refresh the app.
17. Leave unrelated dirty worktree changes and existing generated question-bank artifacts untouched.
