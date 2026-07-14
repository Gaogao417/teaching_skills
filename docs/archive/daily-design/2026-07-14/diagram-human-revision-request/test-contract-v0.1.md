# Diagram Human Revision Request Test Contract v0.1

Status: approved with notes (`APPROVE_WITH_NOTES`). Alias note: the compatibility projection must preserve accepted validation aliases such as `diagram_job_id` when resolving canonical model fields, while the final `model_dump(mode="json")` remains canonical. This archived contract approves the test-writing gate only; it does not authorize production edits.

## Scope and outcome

Repair the boundary between the diagram monitor and `run_diagram_workflow.py` so a human revision starts from a canonical `DiagramJobRequest` v2 and a failed child process cannot be mistaken for an earlier successful workflow result.

The step is complete when all of the following are true:

1. The revision envelope's `diagram_request` is the JSON dump of a successfully validated `DiagramJobRequest` v2.
2. Legacy runtime compatibility fields are absent at the request's top level. Their canonical values, when supported, remain under `engine_options` or `reuse`.
3. A failed revision reports diagnostics produced by that invocation and never consumes an old `workflow_result.json` as its result.
4. The existing authorization boundary remains unchanged: one human request may add exactly its requested Round and may not alter historical Rounds.
5. No migration or mutation of the already-failed artifact is required by this step.

## Canonical request contract

`HumanReviewService._revision_envelope()` may read either `teaching_request.json` or the fallback `request.json`, including files written by an older workflow. Before Pydantic validation, a compatibility adapter projects the stored payload into the current v2 field set. The adapter starts from top-level keys named by `DiagramJobRequest.model_fields`, constructs canonical `engine_options` and `reuse` mappings, attaches `human_revision`, then calls `DiagramJobRequest.model_validate(...)` followed by `model_dump(mode="json")`. The dumped model is the persisted and executed `diagram_request`. It has `schema_version: diagram-job-request/v2` and forces `engine_options.max_retries` to `0`.

The following compatibility keys must not appear at the top level of the emitted `diagram_request`:

- `wolfram_render_image`
- `seed`
- `wolfram_timeout_s`
- `wolfram_hard_timeout_s`
- `reuse_geometry_from`
- `base_job_dir`

This is an envelope-boundary cleanup, not data loss. For `seed`, `wolfram_timeout_s`, and `wolfram_hard_timeout_s`, an existing value inside `engine_options` wins; the corresponding legacy top-level value only backfills that nested key when it is absent. For `reuse_geometry_from` and `base_job_dir`, an existing value inside `reuse` wins; the legacy top-level value only backfills a missing nested key. `wolfram_render_image` is always dropped because it has no `DiagramJobRequest` v2 field. Every other unknown top-level field is excluded by the positive `DiagramJobRequest.model_fields` projection before strict validation, not maintained through an ever-growing manual denylist and not allowed to relax `extra="forbid"`.

The outer `diagram-human-revision-request/v1` envelope remains the monitor's execution metadata. Its `existing_rounds`, `existing_round_fingerprints`, `base_round`, and `requested_round` are not fields of `DiagramJobRequest` and remain outside `diagram_request`.

## Fresh-result and failure contract

Each workflow invocation owns its result observation. A pre-existing `workflow_result.json` may be retained as historical disk state, removed before launch, or replaced by a fresh failure result, but it is never valid evidence for the current invocation unless the current invocation demonstrably produced it.

When the workflow child exits nonzero before producing a fresh result:

- the wrapper exits nonzero;
- its surfaced result is failure, not a prior `status: ok` payload;
- the current child's validation/error text is preserved in `stdout`, `stderr`, `error`, or the monitor review message;
- prior success-only fields such as `wolfram.success: true` must not be presented as the current revision result; and
- `human_review.json` and its immutable history record end at `revision_failed` with the fresh diagnostic.

Freshness must be established by invocation ownership, not by comparing only coarse filesystem modification times. Tests may accept either deleting/isolating the old result before launch or recording a pre-run identity and requiring a newly written result, provided same-path stale reuse is impossible.

## Round mutation invariants

The repair must retain the current host-side protection:

- `new_rounds == {requested_round}` is required, including on a runner exception;
- any extra new Round is removed during rollback;
- fingerprints of every Round listed in `existing_rounds` must remain unchanged;
- a changed historical Round is restored from the pre-run backup;
- a failed requested Round may remain as the visible candidate when it was the one authorized new Round; and
- failure before creating the requested Round leaves candidate selection on an actually existing historical Round.

Request canonicalization and stale-result handling must not weaken these checks or re-enable autonomous retries.

## Test rows

All new tests belong in `tests/test_diagram_monitor.py`. Temporary job trees must be used; the repository artifact under `artifacts/题库/2026-07-12-平行线对应边比例/` is evidence only and must not be edited by the test or implementation.

| ID | Behavior under test | Required observable assertion | Initial state |
|---|---|---|---|
| DHRR-01 | A legacy-shaped base request is canonicalized at revision-envelope creation. | `DiagramJobRequest.model_validate(envelope["diagram_request"])` succeeds; its `model_dump(mode="json")` equals the persisted `diagram_request`; none of the six legacy keys or an unrelated unknown key appears at top level. | RED |
| DHRR-02 | Canonicalization preserves supported runtime meaning and human authorization with deterministic precedence. | Nested `engine_options`/`reuse` values win conflicts; legacy top-level values backfill only absent nested values; `wolfram_render_image` is dropped; `max_retries == 0`; `human_revision` exactly carries action/review/feedback/base/requested values. | RED |
| DHRR-03 | A nonzero workflow child cannot reuse a pre-existing successful `workflow_result.json`. | With an old `status: ok`, `wolfram.success: true` result preseeded and the child returning fresh validation failure, the wrapper exits nonzero and surfaces the validation failure; its emitted/current result is not the old success payload. | RED |
| DHRR-04 | Monitor state reports the current subprocess failure. | The submitted review ends `revision_failed` in both current and history records; message contains a distinctive current validation error and excludes stale success JSON/success-only Wolfram evidence. | RED |
| DHRR-05 | Exactly one requested new Round remains the only authorized addition. | Existing regression continues to reject an extra Round, rolls the extra Round back, and retains only historical Rounds plus the requested Round. | GREEN |
| DHRR-06 | Historical Round mutation is rejected and restored. | Add regression coverage in which a runner modifies a file in Round 0 while creating the requested Round; revision ends failed, message names historical mutation/rollback, and Round 0 bytes match the pre-run bytes. | GREEN (new regression coverage for retained behavior) |
| DHRR-07 | Failure before requested-Round creation does not select a ghost Round. | Existing regression continues to expose only existing Round 0 and the next request again allocates Round 1. | GREEN |
| DHRR-08 | The reported production incident is not repaired by artifact migration. | No automated test writes the existing failed artifact; regression fixtures synthesize the six legacy keys and stale success result in a temporary directory. | DEFERRED (non-mutation constraint; verified by scope review) |

## RED / GREEN / DEFERRED ledger

| State | Meaning for this step |
|---|---|
| RED | DHRR-01 through DHRR-04 should fail against the pre-repair behavior for the stated reason, not because of Wolfram, network, timing, or missing repository artifacts. |
| GREEN | DHRR-05 and DHRR-07 describe existing passing protections; DHRR-06 adds regression coverage for already-implemented historical rollback behavior. After implementation, every non-deferred row and the related monitor suite must pass. |
| DEFERRED | A live Wolfram/Codex revision, UI wording polish, and mutation/retry of the existing failed artifact are outside this deterministic step. |

## Mock policy

- Do not launch Codex, Wolfram, a browser, or network services.
- Use a temporary artifact/job tree for request and Round mutation tests.
- For envelope tests, call the service boundary directly and validate with the real `DiagramJobRequest` from the diagram workflow contracts.
- For subprocess failure tests, use either a tiny local child fixture or a patched `run_subprocess_streaming`/`subprocess.run` that returns a real `CompletedProcess` shape with a distinctive nonzero return code and validation diagnostic.
- Do not mock `DiagramJobRequest` validation, JSON persistence, fingerprint calculation, backup, or restore; those are the behaviors under contract.
- A stale result fixture must contain unmistakable success evidence and the current failure must contain a distinct marker, so assertions cannot pass by matching generic words such as `failed` or `error`.
- Avoid mtime-only mocks. The test must prove the old payload itself was not selected.

## Source alignment

- `scripts/diagram_monitor/human_review.py:271-297`: currently spreads the entire stored base request into `diagram_request`, which carries legacy top-level fields forward; this is the canonicalization boundary.
- `scripts/diagram_monitor/human_review.py:299-355`: current exactly-one-new-Round and historical fingerprint checks, plus their backup/restore support, are retained constraints.
- `scripts/diagram_monitor/human_review.py:358-398`: writes the runtime request, launches the wrapper, and maps subprocess/agent output into revision status; this is the monitor-side fresh-diagnostic boundary.
- `scripts/diagram_workflow/diagram_contracts.py:181-188`: strict models forbid unknown inputs; loose output models are not appropriate for the v2 job request.
- `scripts/diagram_workflow/diagram_contracts.py:831-871`: canonical locations for reuse, seed, retry, and Wolfram timeout configuration.
- `scripts/diagram_workflow/diagram_contracts.py:1088-1150`: typed human revision and `DiagramJobRequest` v2 policy; human revision forces zero autonomous retries.
- `scripts/diagram_workflow/run_diagram_workflow.py:385-395`: request/output setup currently persists input before the GeometricScene child launch.
- `scripts/diagram_workflow/run_diagram_workflow.py:452-483`: currently reads any same-path `workflow_result.json` after the child returns, even when the child returned nonzero; this is the stale-result boundary.
- `tests/test_diagram_monitor.py:184-224`: existing advice submission/envelope expectations are the nearest request regression seam.
- `tests/test_diagram_monitor.py:313-350`: existing terminal-state coverage is the nearest fresh-failure-message seam.
- `tests/test_diagram_monitor.py:352-447`: existing extra-Round, partial-failure, and ghost-Round regressions must remain intact.

## Downstream required constraints

`required_constraints`:

1. Test edits are limited to `tests/test_diagram_monitor.py` after contract audit approval.
2. Production edits are limited to `scripts/diagram_monitor/human_review.py` and, only as needed for invocation-owned result handling, `scripts/diagram_workflow/run_diagram_workflow.py`; `diagram_contracts.py` is source truth, not an authorized schema relaxation target.
3. Use `./.venv-diagram/bin/python` only for the diagram-environment Pydantic import/preflight. Run focused tests with `./.venv/bin/python -m pytest tests/test_diagram_monitor.py`.
4. Apply a pre-validation compatibility adapter: positively project top-level fields through `DiagramJobRequest.model_fields`, construct canonical nested `engine_options`/`reuse`, then use real `DiagramJobRequest.model_validate(...)` plus `model_dump(mode="json")`. Do not solve this only with a six-key `pop()` list, and do not change `extra="forbid"` to accept legacy top-level fields.
5. Existing nested runtime/reuse values take precedence; legacy top-level values only backfill missing nested keys; `wolfram_render_image` and all other unknown top-level fields are excluded. Preserve `human_revision` and `engine_options.max_retries == 0`.
6. A nonzero child return code takes precedence over every pre-existing result file. No old `status: ok`, selected Round, or Wolfram success may be attributed to the failed invocation.
7. Preserve exact-one-new-Round validation, historical fingerprints, backup/restore, partial requested-Round visibility, and ghost-Round fallback behavior.
8. Do not edit, delete, retry, or migrate the existing failed artifact as part of this step.
9. Leave unrelated dirty worktree changes untouched.
