# Question Bank Review UI Visual Source Index

## Existing visual source

- Header, colors, typography, pills, controls, card treatment, and mobile breakpoint: `.codex/skills/math-topic-question-bank/static/training-number-review.css`.
- Header copy structure and summary/navigation placement: `.codex/skills/math-topic-question-bank/templates/training-number-review.html`.
- Existing interaction implementation uses native HTML and JavaScript with a local FastAPI server; no frontend framework is present.

## Required visible behavior

- A sticky editorial-style header with eyebrow, Chinese page title, short help copy, one compact link to the number database, and selected-bank summary pills.
- A toolbar with a labeled bank `<select>` populated from all discovered `question-bank.yaml` manifests.
- After selection, a desktop two-pane layout: a scrollable question list on the left and a reading panel on the right.
- Every list row exposes item id, title, difficulty, and a small set of skill tags; selection is visibly persistent.
- The reading panel shows item metadata, the full question stem, prompt diagram preview when available, answer, explanation, ordered solution steps, and solution diagram preview when available.
- Mathematical source text remains selectable and preserves line breaks. Missing optional diagrams produce a quiet empty state, not an error.
- Previous/next controls and keyboard-friendly native controls allow reviewing every item without returning to the selector.
- At widths below 760px, panes stack vertically and the header/toolbar cease relying on horizontal space.

## Tokens and dimensions

- Reuse `--ink #20231f`, `--muted #70756d`, `--paper #f3f0e8`, `--panel #fbfaf6`, `--line #d8d2c5`, `--accent #23644d`, serif display heading, and existing shadow treatment.
- Main content remains capped at 1500px with 16px minimum viewport gutters.
- Toolbar/control minimum height: 42px. Panels use 16–18px radii and 1px token borders.
- Reading column should remain at least 0-width-safe; diagrams use `object-fit: contain` and must not crop.

## Current gaps

- No question-bank-specific page or assets exist.
- Number review has only a game link; there is no reciprocal question-bank navigation.
- Assignment data contains LaTeX-flavored strings and nested solution fields; the UI needs safe text rendering and diagram preview URLs supplied by the server.

## Manual acceptance

- At 1440px, bank selector, question list, and question/solution reader are simultaneously usable without horizontal overflow.
- At 390px, all controls, question text, solution steps, and diagrams remain readable with no clipped content.
- Selecting another bank resets to its first item and updates counts/metadata.
- The small “数库” and “题库” links point to the configured sibling service ports.
