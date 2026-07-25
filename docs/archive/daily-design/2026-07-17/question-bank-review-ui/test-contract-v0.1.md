# Question Bank Review UI Test Contract v0.1

Status: approved for `step2` after conservative main-session audit on 2026-07-17 (the dedicated auditor was retried twice but its connection failed).

## Scope and API/state contract

This step adds a read-only local review service. The default question-bank URL is `http://127.0.0.1:8877/`; the existing number-review default remains `http://127.0.0.1:8876/`. Both sibling URLs are explicit launcher/server configuration, never inferred from an untrusted request `Host` header.

| ID | Contract | Test expectation | Initial state |
|---|---|---|---|
| QBR-01 | Discover direct-child `artifacts/题库/*/question-bank.yaml` manifests with schema `math_topic_question_bank/v1`, keyed by unique `bank.id`, in deterministic manifest-path order. `GET /api/banks` returns topic, grade, status, target/item/enabled counts and configured number-review URL without exposing absolute paths. | A temporary root with two valid banks, an unrelated YAML, and an invalid manifest returns exactly the two valid summaries in stable order; duplicate ids or invalid manifests are reported safely rather than ambiguously selected. | RED |
| QBR-02 | `GET /api/banks/{bank_id}` returns bank metadata and manifest-order items. Each item contains manifest metadata plus `stem_latex` from the matching student practice block and `answer`, `explanation`, ordered `{title, content}` solution steps from the matching teacher block. Missing optional prose becomes an empty string/list; a broken item is represented by an item-local `load_error` and does not hide the other items. | Fixture assignments prove exact extraction, newline preservation, step order, and isolation of one missing assignment. Unknown bank ids return 404. | RED |
| QBR-03 | Prompt preview is resolved from the student block's `diagram_col`; solution preview is resolved from the teacher solution/answer-space diagram. Direct supported `image_path` wins; a TikZ `*.fragment.tex` may resolve only to an existing sibling `*.preview.svg` then `*.preview.png`. Missing optional previews yield `null`, not a broken URL or server error. | Fixtures cover prompt-only, prompt-and-solution, and no-diagram items, including SVG/PNG preference. No renderer is invoked. | RED |
| QBR-04 | `GET /api/assets/{bank_id}/{item_id}/{role}` accepts only discovered bank ids, manifest item ids, and `prompt|solution`. The manifest assignment and resolved image must be regular files whose fully resolved paths remain under that bank directory; symlinks, `..`, encoded traversal, arbitrary absolute paths, and non-image targets are rejected with 404/400. | Temporary-tree traversal and symlink escapes never return bytes; a valid preview returns the correct image MIME type and bytes. | RED |
| QBR-05 | The browser state is `loading banks -> first bank + first item selected`; changing bank resets to its first item; selecting a row or previous/next changes only the current item. Empty/error states are explicit, endpoint failures retain recoverable controls, and a stale earlier response cannot replace a later selection. | Frontend state tests use delayed/failing fetch fixtures and assert selection, reset, end-control disabling, retry/empty copy, and stale-response suppression. | RED |
| QBR-06 | The launcher accepts `--bank-root`, `--host`, `--port` (default 8877), `--number-review-url`, and `--no-browser`, prints `QUESTION BANK REVIEW READY: <url>`, opens one browser tab unless suppressed, and passes resolved configuration to the app. Number review exposes the configured reciprocal question-bank URL, defaulting to 8877. | CLI tests patch uvicorn/browser only and assert defaults, overrides, one/no browser call, and reciprocal link configuration. | RED |
| QBR-07 | The service is read-only: no endpoint edits manifests, assignments, assets, enabled state, or number-review state. Question, answer, tags, captions, and errors are data, not HTML; the client renders them as inert selectable text. | Route inventory contains no mutation route; malicious HTML-like YAML remains literal text and creates no executable DOM. | RED |

## Source alignment

- Discovery/schema truth: `.codex/skills/math-topic-question-bank/references/question-bank-schema.md` and `artifacts/题库/*/question-bank.yaml` (eight current manifests).
- Assignment truth: each manifest item points to one student and one teacher single-question assignment; the matching block id equals the item id.
- Diagram truth: resolved assignments keep prompt `diagram_col` on the question block and may keep solution `diagram_col` under answer space; generated `*.preview.svg/png` files are evidence only.
- Sibling service/launcher truth: `.codex/skills/math-topic-question-bank/scripts/training_number_review_server.py` and `open_training_number_review.py` use port 8876.
- UI source truth: the existing number-review template/CSS supplies navigation and static-asset conventions; the new service must not alter number database behavior.

## RED / GREEN / DEFERRED ledger

| State | Meaning |
|---|---|
| RED | QBR-01 through QBR-07 lack the requested question-bank server/UI coverage and should fail for that absence before implementation. |
| GREEN | Existing number-review database, enable/disable, game, and history behavior must remain passing; the eight current manifests remain unmodified source fixtures. |
| DEFERRED | Editing questions/enabled state, rendering missing diagrams, MathJax/LaTeX interpretation, authentication for non-local deployment, and replacing other review workflows are outside this slice. |

## Mock policy

- Use temporary bank roots and tiny YAML/image fixtures; do not write under `artifacts/题库`.
- Use FastAPI's in-process test client and real YAML/path resolution. Do not start network listeners, render TikZ, or mock containment checks.
- Launcher tests may mock `uvicorn.run`, timers/browser opening, and CLI arguments only.
- Browser/state tests may fake fetch responses; security tests must exercise the real server resolver and real filesystem symlinks.

## Downstream required constraints

`required_constraints`:

1. Test edits are limited to `tests/test_question_bank_review.py` until test audit approval; production remains blocked.
2. Production must be new question-bank review server/launcher/template/static files plus the minimal reciprocal number-review link/configuration. Do not change question-bank YAML, assignments, diagram assets, number database state, or game/history semantics.
3. Use `yaml.safe_load`; map public bank/item/role identifiers through discovered records. Never concatenate a request value into a filesystem path.
4. Resolve and containment-check manifest assignment paths, image paths, derived preview paths, and symlinks before reading. Do not mount the artifact root as unrestricted static files and do not return absolute paths.
5. Extraction is read-only and item-local: student stem/prompt plus teacher answer/explanation/steps/solution. Preserve authored strings and ordering; never execute or render YAML content as HTML.
6. The UI must ignore stale async responses and retain accessible native controls and recoverable empty/error states.
7. Default ports are 8877 (题库) and 8876 (数库); reciprocal URLs are configurable and are not derived from request headers.
8. Run focused tests with `./.venv/bin/python -m pytest tests/test_question_bank_review.py`; leave unrelated dirty changes untouched.
