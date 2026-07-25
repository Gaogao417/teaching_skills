# Question Bank Review UI Slice Plan

## Source truth

- User request: select any existing question bank, preview each question and its solution, and navigate between question-bank review and the training-number database review.
- `.codex/skills/math-topic-question-bank/references/question-bank-schema.md`
- `.codex/skills/math-topic-question-bank/scripts/training_number_review_server.py`
- `.codex/skills/math-topic-question-bank/templates/training-number-review.html`
- `.codex/skills/math-topic-question-bank/static/training-number-review.css`
- `artifacts/题库/*/question-bank.yaml`

## Current state / gaps

- Eight discoverable question-bank manifests exist under `artifacts/题库`.
- The training-number review already establishes the visual language and default port `8876`.
- There is no question-bank discovery/detail API, question/solution preview page, or launcher.
- The number-review page does not link to a question-bank review service.

## Out of scope

- Editing question content or enabled state.
- Rendering missing TikZ/PDF assets.
- Replacing assignment or diagram review workflows.

| Step | Do | Mode | Depends on | Can run with | Locks / owner | Next role |
|---|---|---|---|---|---|---|
| step1 | Lock discovery, safe file serving, assignment extraction, and cross-service navigation behavior | serial | none | none | question-bank review server | contract designer |
| step2 | Add API and launcher tests for bank/item discovery, extracted question/solution content, preview files, and traversal rejection | serial | step1 | none | `tests/test_question_bank_review.py` | test writer |
| step3 | Implement the question-bank review server and launcher | serial | step2 | none | question-bank review Python files | implementation agent |
| step4 | Implement responsive HTML/CSS/JS and add the reciprocal number-review link | serial | step3 | none | question-bank UI assets plus number-review template | frontend implementation agent |
| step5 | Run focused tests and browser verification | serial | step4 | none | verification evidence | architecture + visual review |

## Gate ledger seed

- Contract: pending
- Contract audit: pending
- Tests: blocked on approved contract
- Production: blocked on approved tests
- Final review: pending

