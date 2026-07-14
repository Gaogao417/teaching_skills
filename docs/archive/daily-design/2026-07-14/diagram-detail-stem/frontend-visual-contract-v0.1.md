# Diagram Detail Problem Stem — Frontend Visual Contract v0.1

Status: pending re-review after field-name correction.

## Step scope

- In the selected Job detail pane's `概览` tab, show the non-empty question stem supplied as `jobDetail.stem_latex` from that Job's `request.json`.
- Preserve the current candidate label, candidate preview, human-review panel, run summary, evidence sections, five tabs, and three-pane information architecture.
- Display the LaTeX-bearing stem as readable source text. This step does not add a math renderer, interpret arbitrary HTML, or change the diagram artifact.
- Allowed production scope: `scripts/diagram_monitor/static/monitor.js`, `scripts/diagram_monitor/static/monitor.css`, and `scripts/diagram_monitor/templates/index.html` only if cache busting is required. Allowed test scope: `tests/test_diagram_monitor.py`.

## Visual source index

| Source | Existing visible contract | Required extension / current gap |
|---|---|---|
| `request.json` → `problem_context.stem_latex` | The source preserves Chinese prose, `$...$` math delimiters, LaTeX commands such as `\\parallel`, and authored blank lines. | Backend exposes this exact question-facing value as `jobDetail.stem_latex`; the detail pane currently does not display it. Do not substitute `source_problem_text`, which is diagram-generation guidance rather than the student question. |
| `scripts/diagram_monitor/static/monitor.js:202-225` | `renderDetail` routes the active `概览` tab to `renderOverview`; Overview currently orders candidate label, preview, human review, then execution evidence. | Add the non-empty stem immediately before the candidate label. Escape it before insertion into the existing `innerHTML` render path; do not create markup from stem contents. |
| `scripts/diagram_monitor/static/monitor.css:1-20` | The monitor uses a white panel, quiet inset surfaces, teal accent, 10 px radius, system text, and a monospace face for technical identifiers. | Reuse the existing palette and border/radius language. The question is content evidence, not an alert or editable field, so it needs no warning color, elevation, or input styling. |
| `scripts/diagram_monitor/static/monitor.css:176-187` | The detail body scrolls independently; candidate metadata is a compact row and the preview is a bordered, contained image well. | The stem becomes a compact bordered block before this pair. It must not change `.detail-preview` sizing, containment, or image fit. |
| `scripts/diagram_monitor/static/monitor.css:286-310` | Below 1100 px the detail pane moves to a full-width row; below 720 px all panes stack. | The stem remains one fluid-width block with wrapping at 1440, 1024, and 680 px; it must not introduce page or pane horizontal overflow. |
| `docs/archive/daily-design/2026-07-13/diagram-pipeline-monitor/frontend-visual-contract-v0.1.md` | DPM-06 keeps Job evidence in five detail tabs; DPM-09 preserves the selected Job/tab on refresh; DPM-10 fixes responsive behavior. | Show the stem in the existing Overview only, preserve it through rerenders from Job data, and add neither a tab nor a modal. |
| `docs/archive/daily-design/2026-07-14/diagram-monitor-detail-preview/frontend-visual-contract-v0.3.md` | The candidate preview stays uncropped and the detail body owns vertical scrolling. | The new content may push the preview downward within the same scroll container, but may not cover, crop, resize, or replace it. |
| `docs/archive/daily-design/2026-07-14/diagram-human-review-codex-thread/frontend-visual-contract-v0.1.md` | The human-review panel remains below the candidate preview and its task binding remains subordinate to the review actions. | Keep that complete panel and its ordering unchanged after adding the stem above the candidate evidence. |

## Visible hierarchy

When `stem_latex` contains non-whitespace text, the top of Job Overview follows this order:

1. One question-stem block labelled `题干`.
2. Existing `当前候选 Round N` label and deterministic audit text.
3. Existing candidate image preview or preview placeholder.
4. Existing human-review panel.
5. Existing run summary, status explanations, warnings, and stage evidence.

The question-stem block contains exactly two visible levels:

- Heading: `题干`, visually consistent with existing 12 px detail-section headings.
- Body: the complete `stem_latex` value, rendered as text with source line breaks preserved.

Representative display:

```text
题干
如图，直线 $AC$ 与 $BD$ 相交于点 $P$，点序分别为 $P-A-C$、$P-B-D$，且 $AB\parallel CD$。

已知 $PA:PC=2:5$，求 $PB:PD$。
```

The heading and body form one semantic section. The stem is not a textarea, code editor, collapsible artifact, tooltip-only value, modal, or floating overlay.

## Visible states

| State | Required display | Prohibited display |
|---|---|---|
| Non-empty stem | Render exactly one `题干` block before the candidate label. Preserve authored newlines and visible LaTeX delimiters/backslashes. | No HTML interpretation, Markdown conversion, MathJax dependency, truncation, ellipsis, or duplicate block. |
| Missing, `null`, empty, or whitespace-only stem | Omit the entire block, including its heading, border, padding, and spacing. Candidate label remains the first Overview content. | No empty card, `题干 —`, `暂无题干`, or unexplained blank gap. |
| HTML-like source | Show characters such as `<script>`, `<b>`, `&`, quotes, and angle brackets as inert readable text. | No executable element, styled injected element, event handler, external resource, or DOM node created from stem content. |
| Long stem / long LaTeX token | Wrap within the detail pane. Preserve all text and use the detail body's existing vertical scroll when content exceeds the viewport. | No horizontal page/pane scroll, clipped suffix, fixed-height inner scroller, or preview overlap. |
| Job/tab refresh | Render the stem belonging to the currently selected `jobDetail`; switching Jobs replaces it and returning to Overview restores it from Job data. | No stale stem from the previous Job and no loss caused solely by auto-refresh/rerender. |

## Layout and styling contract

- The block is full width of the existing `.detail-body` content box and has `min-width: 0`.
- Use one 1 px `--line` border, a 7–8 px radius consistent with `.detail-preview` and `.key-item`, and a quiet `#fbfcfd`/existing neutral inset background. No shadow or new palette token.
- Suggested spacing: 9–11 px internal padding; 10–12 px below the block before the candidate label. The block itself starts at the top of Overview, so it adds no arbitrary top margin.
- Heading: margin `0 0 6–7px`, 12 px, bold, `--ink`.
- Body: margin `0`, 11–12 px text with approximately 1.6 line height and `--ink`. Chinese prose remains primary; source syntax is preserved rather than syntax-highlighted.
- Body wrapping must combine `white-space: pre-wrap`, `overflow-wrap: anywhere`, and `min-width: 0` (or an equivalent computed result). This retains blank lines while allowing long commands/identifiers to wrap.
- Do not use `white-space: pre`, a fixed width, a fixed/max height, horizontal scrolling, or `word-break: keep-all`.
- Do not alter `.detail-body` scroll ownership, `.detail-preview` minimum height/image containment, `.human-review-panel` spacing, or any review control dimensions.
- Stem text is selectable with normal browser selection. It is not editable and receives no focus ring or click affordance.

## Acceptance rows

| ID | User-visible contract | Automated acceptance target | Manual acceptance |
|---|---|---|---|
| DDS-V01 | A selected Job with a stem shows exactly one clearly labelled `题干` block in Overview before the candidate label and preview. | A fixture with `stem_latex` renders one stem section; DOM order is stem → candidate label → `.detail-preview` → `.human-review-panel`. | The user sees what problem the image belongs to before judging the image. |
| DDS-V02 | The complete source string remains readable, including blank lines, `$...$`, backslashes, ratios, and Chinese punctuation. | Text-content assertion matches the fixture value; computed style preserves newlines and permits wrapping. | A two-paragraph sample reads as two paragraphs and `$AB\\parallel CD$` remains visibly recognizable. |
| DDS-V03 | Stem contents are inert text, never arbitrary HTML. | An HTML-like malicious fixture produces no `script`, injected image/link/button, event handler, or extra styled element; its literal characters remain in stem text. | Viewing a stem with angle brackets does not change layout or execute content. |
| DDS-V04 | Jobs without a meaningful stem retain the current Overview without an empty card or extra gap. | Fixtures for absent, `null`, empty, and whitespace-only values contain no `题干` region; candidate label remains first. | Jobs generated before stem support look unchanged rather than broken. |
| DDS-V05 | Long stems wrap within the pane at desktop, tablet, and mobile widths without hiding or changing the preview. | Layout checks at 1440×1000, 1024×900, and 680×900 assert stem bounds are within `.detail-body`, document/pane `scrollWidth <= clientWidth`, and preview follows without overlap. | No horizontal scrollbar; scrolling the existing detail body reaches the full stem, preview, and review controls. |
| DDS-V06 | Job selection, Overview tab return, and refresh always show the current Job's stem once. | Render Job A, Job B, switch tabs, and rerender/refresh; assert correct text and a single stem block each time. | No stale or duplicated question appears during monitoring. |
| DDS-V07 | Existing candidate and review behavior remains visually intact. | Preview containment checks and human-review/Codex-binding checks continue to pass with short and long stem fixtures. | The new block does not cover the image, move controls outside the detail scroll region, or alter action usability. |

## Responsive and manual acceptance matrix

| Viewport | Required layout | Manual check |
|---|---|---|
| `1440 × 1000` | Stem fits the desktop detail column as one full-width inset block. Candidate label and preview remain directly below it. | Both question paragraphs, candidate header, and top of the preview are reachable in the normal detail scroll; no three-pane width shift. |
| `1024 × 900` | Detail pane remains full width below the folder/job row. Stem uses the available width and wraps long LaTeX naturally. | No horizontal page or detail-body scrollbar; candidate preview width and aspect treatment remain unchanged. |
| `680 × 900` | Stacked detail pane contains the stem in one column with 11–12 px readable text and wrapped long tokens. | No clipped right edge, overlapping heading/body, nested stem scrollbar, or interference with stacked human-review actions. |
| Long-content fixture | At least six lines plus one unbroken 120-character source token wrap inside the block. | The entire suffix is selectable/readable and the block grows vertically within `.detail-body`. |
| Missing-content fixture | No question block or reserved spacing appears. | Candidate label aligns at the same top position as the current implementation. |
| HTML-like fixture | Literal `<script>alert(1)</script>` and `<b>text</b>` remain visible text. | No alert, bold injected node, link, image request, or changed DOM hierarchy. |

## Implementation boundaries

- Treat `jobDetail.stem_latex` as the sole frontend source for this block; the browser must not fetch or parse `request.json` directly.
- Normalize only for presence detection: a whitespace-only string is absent. Do not trim, rewrite, join, typeset, or otherwise mutate the displayed non-empty source value.
- Use the monitor's existing escaping helper before interpolation into `innerHTML`, or create the body through `textContent`. A test that merely finds the word `题干` in JavaScript is auxiliary; primary tests must inspect visible text, order, computed wrapping, and overflow.
- `index.html` requires no new container, script dependency, dialog, or tab. Touch it only if the existing static asset cache-busting convention requires a version update after CSS/JS changes.
- Do not show `source_problem_text`, teacher solution, diagram instructions, prompt engineering fields, answers, or explanations in this block.
