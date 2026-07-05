---
name: math-skill-trace-ingestion
description: Generate reviewable SkillTraceDraft JSON for math problems when the user provides a problem, solution, expected thinking, wants skill nodes, a skill graph, trace ingestion, or human review. Skip when the user only asks to render PDFs, solve normally, generate ordinary exercises, or continue the standard assignment pipeline without trace review.
---

# Math Skill Trace Ingestion

Use this skill to turn one math problem and its intended thinking path into a small, reviewable Skill Trace draft. The draft is not a student explanation and is not a practice sheet.

## Workflow

1. Read the user-provided problem, solution, expected thinking, and any visible student mistake evidence.
2. Read `docs/skill-graph-conceptual-model.md` before assigning `cognitive_layer` or `reuse_level`.
3. Use `prompts/skill_trace_draft_prompt.md` as the draft-generation contract.
4. Generate one `SkillTraceDraft` JSON object matching `scripts/skill_trace/contracts.py`.
5. Keep each step to one student action. Split strategy, structure recognition, encoding, and execution into separate steps when needed.
6. Save the JSON to `artifacts/skill-trace-drafts/<draft_id>.json`.
7. Run `./.venv/bin/python scripts/skill_trace/open_review.py --draft artifacts/skill-trace-drafts/<draft_id>.json --codex-thread-id <thread_id>`.
8. Return the `codex_thread_id` and review URL from the command output.

## Thread Id Rules

- Prefer the real Codex SDK thread id when a wrapper provides it.
- In CLI use, pass `--codex-thread-id` when the user or wrapper supplies one.
- If no real id is available, let `open_review.py` generate `manual_<uuid>` and tell the user it is not a real Codex thread id.

## Boundaries

- Do not write the student-facing explanation in this step.
- Do not create practice problems in this step.
- Do not create a large canonical graph. This MVP stores the reviewed problem-level trace only.
- Do not automatically merge reviewed steps into canonical skill nodes.
