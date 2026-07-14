# Diagram Pipeline Monitor Job Grid Visual Contract v0.2

Status: approved by the user on 2026-07-14.

## Source evidence

- Existing contract: `docs/archive/daily-design/2026-07-13/diagram-pipeline-monitor/frontend-visual-contract-v0.1.md`, especially DPM-04 and DPM-10.
- Current implementation: `scripts/diagram_monitor/static/monitor.css` (`.pane`, `.job-grid`, `.job-card`, `.preview-well`).
- Reproduction: `http://127.0.0.1:8790/?q=2026-07-12` at a 919 x 849 viewport with a 60-job question bank.
- Failure evidence: 60 of 60 images load, but the two-column grid creates 30 rows of about 2.72 px while each preview is about 230 px high, so cards overlap.

## Contract rows

| ID | User-visible contract | Automated acceptance | Browser acceptance |
|---|---|---|---|
| DPM-11 | The job board scrolls inside its pane and does not shrink its rows to fit all jobs. | CSS contract keeps the grid as the pane's flexible scroll region and sizes implicit rows from content. | With 60 jobs at 919 px width, every card is at least 180 px high and adjacent rows do not overlap. |
| DPM-12 | Every loaded preview remains fully contained in its own 16:10 preview well. | Existing `aspect-ratio: 16 / 10` and `object-fit: contain` rules remain unchanged. | All 60 images load, have non-zero rectangles, and no image extends into the next card. |
| DPM-13 | Responsive behavior from DPM-10 remains intact. | Existing 1100 px and 720 px media rules remain present. | The 919 px two-column workspace has no horizontal page overflow; the job pane scrolls vertically. |

## Allowed write scope

- `scripts/diagram_monitor/static/monitor.css`
- `scripts/diagram_monitor/templates/index.html` (stylesheet cache key only)
- `tests/test_diagram_monitor.py`

No scanner, API, renderer, assignment, or diagram artifact changes are allowed.
