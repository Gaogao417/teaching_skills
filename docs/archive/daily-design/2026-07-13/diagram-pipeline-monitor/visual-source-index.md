# Diagram Pipeline Monitor Visual Source Index

## User goal

Provide a local monitor where a keyword such as `比例辅助线` finds relevant artifact folders, sorts them by real latest activity, and exposes image generation plus every intermediate diagram artifact while the pipeline is working.

## Exact source references

| Source | Visible information |
|---|---|
| `diagram_jobs.json` | Assignment ID, source assignment, ordered jobs, slot ID, variant, engine, kind, required flag, content hash, reuse dependency |
| `diagram_batch_report.json` | Advisory totals and batch-reported workflow/renderer status |
| `workflow_events.jsonl` | Timestamped live events, stage status, selected round, agent thread, final message |
| `workflow_result.json` | Effective workflow result, fail type/message, Wolfram success/time, rounds, selected round, agent duration |
| `renderer_result.json` | Renderer status, preview paths, TikZ paths, dimensions, checks |
| `renderer_audit.json` | Preview size, readability warnings, artifact checks |
| `rounds/round_*` | Round scene payload, Wolfram result, renderer spec, TikZ IR, preview images, audit and logs |
| `performance_profile.json` | Renderer and preview stage timings |
| resolved assignment YAML / final PDFs | Assignment-level completion evidence |

## Existing visual language

- `math-assignment-latex/scripts/review_static/review.css` uses a restrained local-tool palette: cool gray canvas, white bordered panels, teal accent, compact chips, and three-pane desktop workspaces.
- Existing review services use FastAPI with static HTML/CSS/JS; the monitor should remain visually related but own its files and layout.

## Required layout

- Sticky top toolbar, minimum height 72 px.
- Desktop workspace: `300px minmax(420px, 1fr) minmax(420px, 0.95fr)`.
- Folder and job panes scroll independently beneath the toolbar.
- Job cards use a preview-first layout with a 16:10 preview well and a compact stage rail.
- Detail pane uses tabs for overview, rounds, events, artifacts, and performance.
- At widths below 1100 px, the detail pane moves below the folder/job pair.
- At widths below 720 px, all panes stack and no horizontal page scrolling is permitted.

## Required tokens

| Token | Value | Purpose |
|---|---|---|
| `--canvas` | `#f3f5f7` | App background |
| `--panel` | `#ffffff` | Primary surfaces |
| `--ink` | `#18232d` | Main text |
| `--muted` | `#667583` | Secondary text |
| `--line` | `#d8e0e6` | Borders and separators |
| `--accent` | `#176b87` | Selected and active state |
| `--success` | `#207a55` | Completed stages |
| `--warning` | `#a46310` | Stalled/incomplete states |
| `--danger` | `#a33737` | Failed/conflicting states |
| `--radius` | `10px` | Cards and panels |

## Copy and states

- Empty search: `输入关键词查找作业目录`.
- No match: `没有找到匹配的作业目录`.
- No jobs: `这个目录还没有 diagram job`.
- No preview: show stage/status instead of a broken image.
- Status labels: `等待中`, `运行中`, `疑似卡住`, `失败`, `产物不完整`, `成功`, `状态冲突`.
- Relative times are accompanied by exact local timestamps in a title or detail field.

## Current implementation gaps

- No monitor server, scanner, APIs, static UI, or monitor tests exist.
- No authoritative single status file exists; the UI needs an explicit reconciliation layer.
- Current events do not include a heartbeat/PID, so `疑似卡住` must be an inference based on the most recent unmatched start event and inactivity threshold.

