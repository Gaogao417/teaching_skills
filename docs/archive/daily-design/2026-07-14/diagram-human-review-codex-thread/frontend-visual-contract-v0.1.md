# Diagram Human Review Codex Task Binding — Frontend Visual Contract v0.1

Status: proposed focused extension of the approved Diagram Human Review panel.

## Step scope

- One click on `提交给 Agent` creates a persistent Codex app task, not an in-page temporary chat session.
- After creation starts, the existing `人工复核` panel shows one compact Codex task binding containing a text status and thread ID.
- The monitor does not render a chat transcript, composer, agent avatar, message bubbles, or a second conversation surface.
- The current candidate preview, feedback textarea, review lifecycle chip, actions, detail tabs, and three-pane layout remain in place.

## Visual source index

| Source | Existing visible contract | Required extension / current gap |
|---|---|---|
| `scripts/diagram_monitor/static/monitor.js:30-37` | The review heading already maps six revision lifecycle states to text labels. | Codex task creation/binding needs its own small text status; it must not replace or overload the revision-state chip. |
| `scripts/diagram_monitor/static/monitor.js:206-218` | Job Overview orders candidate label, preview, human-review panel, then run evidence. | Keep the task binding inside the existing human-review panel; do not add a detail tab, modal, or page-level panel. |
| `scripts/diagram_monitor/static/monitor.js:221-241` | The panel contains heading/status, rule, candidate, feedback, errors, and two actions. | Append the binding immediately after `.human-review-actions`, so it visibly confirms what `提交给 Agent` created without interrupting feedback entry. |
| `scripts/diagram_monitor/static/monitor.js:254-285` | Submission has local pending state, posts one explicit revision request, reloads the selected Job, and reports failures globally. | Preserve the task binding across reload/auto-refresh from persisted Job data; do not represent persistence with an ephemeral in-memory “chat”. |
| `scripts/diagram_monitor/static/monitor.css:1-20` | Light canvas, white/inset surfaces, teal accent, semantic success/warning/danger, 10 px radius, system + monospace fonts. | Reuse only these tokens and the monospace face for the ID. No new brand palette, gradient, shadow, or chat styling. |
| `scripts/diagram_monitor/static/monitor.css:187-209` | Human-review UI uses a compact bordered inset panel, 10–13 px text, 7 px controls, and a two-column action row. | The binding is a quieter nested evidence row, visually below the primary action and never taller than the feedback field. |
| `scripts/diagram_monitor/static/monitor.css:277-300` | Detail moves full width below 1100 px; below 720 px panes and review actions stack. | The binding wraps without horizontal overflow at both breakpoints; status remains readable and the ID may wrap anywhere. |
| `scripts/diagram_monitor/templates/index.html:66-72` | The detail body is the existing Job evidence surface. | No new root container, dialog, iframe, or embedded Codex web view. |
| `docs/archive/daily-design/2026-07-13/diagram-human-review/frontend-visual-contract-v0.1.md` | Human review stays below the candidate preview, preserves six state labels, and exposes two explicit actions. | This contract extends DHR-V03–V06 without changing those actions or the one-revision rule. |
| `docs/archive/daily-design/2026-07-13/diagram-pipeline-monitor/frontend-visual-contract-v0.1.md` | DPM-06 keeps Job evidence in the five detail tabs; DPM-09 preserves selection on refresh; DPM-10 fixes responsive breakpoints. | Binding persistence must respect the same Overview location, refresh stability, and responsive layout. |
| `docs/archive/daily-design/2026-07-14/diagram-monitor-detail-preview/frontend-visual-contract-v0.3.md` | The current candidate image remains visible and the detail body scrolls independently. | The binding must not resize, crop, replace, or cover the current candidate preview. |

## Visible hierarchy

Within the existing `人工复核` panel, preserve this order:

1. Human-review heading and current review-state chip.
2. One-revision rule and current candidate evidence.
3. `修改建议` textarea, audit/error explanation, and the two current actions.
4. One compact Codex task binding, when task creation has started or persisted task evidence exists.

The binding uses one bordered row with this content hierarchy:

- Leading label: `Codex 任务`.
- Text status: one of the states below; status is never conveyed by color alone.
- Identifier: label `Thread ID` plus the persisted ID in monospace.

Suggested populated copy:

```text
Codex 任务    已创建
Thread ID    019f…edff
```

The full thread ID remains available to assistive technology and through native text selection/title treatment even when the visible row uses compact truncation. The visual contract does not require an in-monitor conversation link or fake messages; navigation into the Codex app is a separate interaction contract if supported by the host.

## Visible states

| Binding state | Required copy and treatment | Relationship to review state |
|---|---|---|
| Absent | Before the first Agent submission, render no empty task card and no placeholder ID. | Existing `未复核` panel remains unchanged. |
| Creating | Show `Codex 任务 · 正在创建…`; reserve the ID line but display `Thread ID —`. Use the accent-soft treatment and text, without an indefinite layout animation. | Submission controls remain disabled by the existing submitting behavior. |
| Bound | Show `Codex 任务 · 已创建` and the persisted thread ID. Use a neutral inset row with success-colored status text. | May coexist with `排队中`, `Agent 修订中`, `新版本待复核`, or `修订失败`; it is proof of task persistence, not proof that revision work succeeded. |
| Creation failed | Show `Codex 任务 · 创建失败` plus concise visible error text; do not invent a thread ID. Use danger text on the existing danger-soft semantic surface. | Existing review state and retry affordance remain authoritative; failure must not look like a completed Codex task. |
| Refreshed/revisited | Render the same `已创建` binding and identical full ID from persisted Job data after auto-refresh, manual refresh, folder/job reselection, or page reopen. | Never revert to `正在创建…` solely because the UI rerendered. |

## Acceptance rows

| ID | User-visible contract | Automated acceptance target | Manual acceptance |
|---|---|---|---|
| DHR-CT-V01 | Agent submission produces a persistent Codex task binding inside the existing human-review panel, immediately below the action row. | A bound fixture renders exactly one `Codex 任务` region after the two actions and within the selected Job Overview. | The result of clicking `提交给 Agent` is visible without leaving the selected Job. |
| DHR-CT-V02 | The binding always shows a text status and, once available, the exact persisted thread ID. | Creating, bound, failure, and refreshed fixtures verify visible copy and ID values; the bound ID survives rerender. | A user can distinguish “task exists” from “task is being created” and “creation failed”. |
| DHR-CT-V03 | Codex task binding and diagram revision state remain distinct. `已创建` does not replace `排队中`/`Agent 修订中`/completion/failure. | Bound + each review-state fixture renders both text labels simultaneously. | “Codex task created” is not mistaken for “diagram revision completed”. |
| DHR-CT-V04 | The monitor contains no fake chat transcript or temporary conversation UI. | Bound state contains no message list, chat composer, iframe, transcript container, or copied Agent-response bubbles. | The panel reads as a task reference, not a second chat client. |
| DHR-CT-V05 | Before submission there is no empty binding; after a creation failure there is visible failure copy and no fabricated ID. | Unsubmitted and failed fixtures assert absence/presence and prevent placeholder values from being treated as IDs. | Empty-state noise is avoided and failures remain actionable. |
| DHR-CT-V06 | The task binding does not hide, crop, or move the current preview out of its existing Overview order. | Layout test keeps preview before human review and confirms no overlap at desktop/tablet/mobile widths. | Candidate image remains the dominant review evidence. |
| DHR-CT-V07 | Auto-refresh and Job reload preserve the same binding and ID without duplicating rows. | Repeated render/refresh test has exactly one binding with the original ID. | Live monitoring does not flicker into a new task or multiply task references. |

## Responsive and manual acceptance matrix

| Viewport | Required layout | Manual check |
|---|---|---|
| `1440 × 1000` | Binding remains one compact nested row in the desktop detail pane. Label/status may share the first line; the ID occupies remaining width without widening the pane. | No overlap with action buttons or the following `运行摘要`; preview width is unchanged. |
| `1024 × 900` | Detail pane remains full width below folder/job panes. Binding may wrap to two lines inside the panel. | Status and `Thread ID` label are both visible; detail body keeps independent vertical scrolling. |
| `680 × 900` | Existing actions stack. Binding content stacks or wraps naturally into one column; ID uses `overflow-wrap: anywhere` rather than forcing page width. | No horizontal scrollbar on the pane/page; the full ID is still obtainable and status text is not clipped. |
| Long-ID fixture | A realistic full thread ID fits through wrapping/truncation plus full-value exposure. | No ellipsis-only identifier, collision, or clipped status. |
| Bound + failed revision fixture | `Codex 任务 · 已创建` and `修订失败` are visible together using separate semantic treatments. | The two states cannot be mistaken for one another. |

## Styling and interaction constraints

- Reuse `--line`, `--accent`, `--accent-soft`, `--success`, `--success-soft`, `--danger`, `--danger-soft`, `--muted`, `--radius`, and `--mono`; add no new raw color unless an existing browser default is unavoidable.
- The binding is visually subordinate to `.review-submit`: 10–11 px text, a 1 px border, 7–10 px internal spacing, and no elevation.
- Keep at least 8 px separation from the action row and following content. Do not add a third primary button to `.human-review-actions`.
- Thread ID is selectable text, rendered in monospace, and allowed to wrap anywhere. Do not place it only in a tooltip or encode it only in an icon.
- Status updates remain in the existing polite live region; do not announce the complete panel repeatedly during auto-refresh.
- Do not add a modal, new Overview tab, floating toast as the only success evidence, avatar, typing indicator, unread count, chat bubble, transcript, or message input.
- Do not change the existing 1100 px and 720 px responsive breakpoints, detail-pane scroll ownership, preview sizing, textarea minimum height, or action labels.
- A task-open affordance may be added only when a real Codex-app navigation contract exists. It must be a compact secondary text action and may not substitute for the visible status and thread ID.
