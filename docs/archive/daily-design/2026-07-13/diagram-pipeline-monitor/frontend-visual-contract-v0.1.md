# Diagram Pipeline Monitor Frontend Visual Contract v0.1

Status: approved from the user's accepted three-pane monitor design on 2026-07-13.

## Contract rows

| ID | User-visible contract | Automated acceptance | Manual acceptance |
|---|---|---|---|
| DPM-01 | A persistent toolbar contains keyword search, status filter, problem-only toggle, auto-refresh control, result count, and last refresh time. | DOM and computed layout tests confirm the controls are visible and do not wrap at 1280 px. | Search remains understandable without reading documentation. |
| DPM-02 | Matching folders appear newest-activity first and each card shows path, effective status, job counts, preview count, and latest activity. | API fixture verifies descendant mtime sorting; browser verifies card metadata. | The newest proportion-line folder is visibly first. |
| DPM-03 | Desktop simultaneously shows folder list, job board, and detail inspector as distinct bordered surfaces. | Computed grid has three columns at 1440 px and no pane overlaps. | A user can move folder -> job -> evidence without losing context. |
| DPM-04 | Every job card prioritizes its final preview and shows variant, engine/kind, current state, round count, last update, and an eight-stage rail. | Fixture states render success/failure/missing stage styles; preview well keeps 16:10 ratio. | Failed jobs identify the failing layer without opening raw JSON. |
| DPM-05 | Missing previews never render broken-image chrome; a clear status placeholder occupies the preview well. | Browser test verifies missing source uses placeholder content and no failed image element. | Pending and failed jobs remain scannable beside successful jobs. |
| DPM-06 | Detail tabs expose overview, round previews, event timeline, grouped intermediate artifacts, and performance. | Each tab updates the detail body and remains keyboard reachable. | All intermediate products are reachable within two clicks of a job card. |
| DPM-07 | Artifact viewer renders images inline and text/JSON/WL/TeX/log files in a readable monospaced viewer with path, size, and modified time. | API blocks paths outside artifact root; supported files return correct content metadata. | Long content scrolls inside the viewer without shifting the whole page. |
| DPM-08 | Current effective state and stale/contradictory summary evidence are visually separate: a complete job remains `成功` while carrying a `汇总不一致` warning. | Reconciliation fixture with dry-run batch plus successful job produces success state plus conflict metadata. | The warning explains which sources disagree without obscuring the usable result. |
| DPM-09 | Auto-refresh preserves selected folder, job, detail tab, and artifact where they still exist. | JS state test/manual browser refresh verifies stable selection. | Live monitoring does not repeatedly jump the user's viewport. |
| DPM-10 | Below 1100 px the detail pane moves to a full-width row; below 720 px all panes stack without horizontal overflow. | Computed layout and screenshot checks at 1024 px and 680 px. | Controls and text remain usable at both widths. |

## Styling rules

- Use the source-index tokens; do not introduce gradients, decorative shadows, or dashboard-style chart clutter.
- Color is redundant with text/icon state labels; success or failure is never encoded by color alone.
- Selected cards use accent border plus a pale accent surface.
- Raw filenames are secondary. Human-readable group labels and pipeline stages are primary.
- Animation is limited to the live-running dot and short selection transitions; respect `prefers-reduced-motion`.

## Screenshot targets

- `1440x1000`: populated three-pane desktop using `比例辅助线`.
- `1024x900`: folder/job row plus full-width detail pane.
- `680x900`: stacked mobile layout with no horizontal overflow.
