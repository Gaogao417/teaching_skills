# Question Bank Review UI Frontend Visual Contract v0.1

Status: approved for `step2` after conservative main-session audit on 2026-07-17 (the dedicated auditor was retried twice but its connection failed). The source of truth is the existing training-number review page, not a new design system.

## Source alignment

| Source | Preserve | Required extension |
|---|---|---|
| `.codex/skills/math-topic-question-bank/static/training-number-review.css` | `--ink`, `--muted`, `--paper`, `--panel`, `--line`, `--accent`, existing shadow, serif display heading, 16–18 px panel radii, 42 px controls, 1500 px content cap, 760 px breakpoint. | Reuse these tokens for the selector, list, reader, pills, buttons, and responsive stack. |
| `.codex/skills/math-topic-question-bank/templates/training-number-review.html` | Sticky editorial header, eyebrow/title/help hierarchy, compact summary pills and accent navigation link. | Title becomes `专题题库审核`; add a compact `数库 →` link and selected-bank/item summary. The number page gains the reciprocal `题库 →` link without disturbing its game link. |
| `visual-source-index.md` | Desktop two-pane review, native controls, selectable source text, contained diagrams, quiet missing-diagram state. | Add bank selection and complete per-item question/solution reading states. |

## Visible acceptance rows

| ID | User-visible contract | Automated acceptance | Manual/browser acceptance | Initial state |
|---|---|---|---|---|
| QBR-V01 | The header shows eyebrow, Chinese title/help, compact `数库 →` link, and pills for selected topic and `当前/总题数`; the number-review header shows a matching small `题库 →` link. | DOM/link test protects visible copy and configured sibling hrefs. | Both services are reachable in one click and links do not dominate the title. | RED |
| QBR-V02 | A bordered toolbar contains a visible `选择题库` label and native `<select>` populated with every discovered bank; loading, no-bank, and fetch-error states are text-visible. | Interaction test verifies options and non-color-only state copy; controls remain at least 42 px high. | The current bank is unambiguous without inspecting the URL. | RED |
| QBR-V03 | At desktop width, a bordered scrollable question list sits left of a min-width-safe reading panel. Every row shows id, title, difficulty, and a compact subset of skill tags; selection persists with accent border/surface and `aria-current`. | At 1440×1000, computed layout has two non-overlapping columns and no horizontal overflow; selected row has semantic state. | Selector, list, stem, and answer are simultaneously usable. | RED |
| QBR-V04 | The reader orders metadata, `题目`, optional `题图`, `答案`, `解析`, ordered `解题步骤`, and optional `解答图`. Source text preserves authored line breaks, is selectable, wraps long LaTeX tokens, and is never truncated or interpreted as HTML. | DOM order/text-content and malicious-text tests; computed styles include pre-wrap/equivalent and overflow wrapping. | Chinese prose, `$...$`, backslashes, and blank lines remain readable. | RED |
| QBR-V05 | Preview images are centered in quiet wells, use `object-fit: contain`, keep natural aspect ratio, and never crop. A missing optional image shows understated `本题无题图/解答图` copy or omits the well consistently; it never shows broken-image chrome. | Image/missing fixtures assert loaded bounds, containment, and absence of failed `<img>`. | Both prompt and solution figures can be inspected at normal page zoom. | RED |
| QBR-V06 | `上一题` and `下一题` native buttons follow the reader, disable at ends, and row/select/button focus is keyboard visible. Changing banks selects its first item and updates pills; empty/error content remains recoverable. | Keyboard/state test checks order, disabled ends, reset, focus-visible styling, and retry/empty copy. | Every item can be reviewed without returning to the bank selector. | RED |
| QBR-V07 | Below 760 px the sticky header becomes static, header/toolbar contents stack, and list then reader form one column. All controls, tags, text, steps, and diagrams remain inside 16 px viewport gutters. | At 390×844, document and panels satisfy `scrollWidth <= clientWidth`; no clipped controls/images. | The full question and solution remain readable without horizontal scrolling. | RED |

## Layout and styling constraints

- Desktop content width is `min(1500px, calc(100% - 32px))`; use a roughly `minmax(260px, 0.34fr) minmax(0, 1fr)` review grid. The list may own vertical scrolling, but the full page remains normally scrollable.
- Use the existing paper radial background, panel/border/shadow language, accent `#23644d`, ink `#20231f`, muted `#70756d`, and line `#d8d2c5`. Add no gradient cards, modal, sidebar drawer, icon library, or dashboard chart.
- Difficulty and tags are text labels; meaning is never color-only. Selected state combines semantic state, border, and pale surface.
- Reader prose uses `white-space: pre-wrap`, `overflow-wrap: anywhere`, and `min-width: 0` or equivalent. Do not add MathJax in this slice.
- Images have `max-width: 100%`, `height: auto`, and `object-fit: contain`; preview wells have no fixed height that can crop tall geometry.
- Native select/buttons retain browser keyboard semantics and a visible accent focus ring. Respect reduced motion; animation is optional and never required for state comprehension.

## RED / GREEN / DEFERRED ledger

| State | Meaning |
|---|---|
| RED | QBR-V01 through QBR-V07 have no current question-bank page and must fail visibly before implementation. |
| GREEN | Existing training-number typography, token values, 1500 px cap, native control sizing, and 760 px mobile behavior remain the accepted visual baseline. |
| DEFERRED | In-browser LaTeX typesetting, editing/enabling questions, diagram generation, screenshots for every bank, and richer search/filter controls are outside this slice. |

## Mock and evidence policy

- Visual tests use a deterministic two-bank fixture with at least three items: prompt+solution diagrams, prompt-only, and no diagrams; include long multiline LaTeX-like and HTML-like text.
- Browser tests may intercept API responses but must use real DOM/CSS and tiny real SVG/PNG fixtures. No visual assertion may pass solely from class names or `data-testid` presence.
- Required screenshots/manual checks: populated desktop at 1440×1000 and stacked mobile at 390×844, plus one missing-diagram state.

## Downstream required constraints

`required_constraints`:

1. Preserve the existing number-review visual hierarchy and behavior; its only visible addition is the compact reciprocal `题库 →` navigation control.
2. New UI assets reuse existing tokens and native HTML/JavaScript; introduce no frontend framework or external CDN dependency.
3. Primary tests must assert user-visible text, semantic selection, computed layout, wrapping, image containment, and overflow—not implementation class strings alone.
4. Render all assignment-derived content as inert text. No `innerHTML` with server/YAML fields, Markdown-to-HTML conversion, or inline event handlers.
5. Bank change resets to item one; previous/next and selected-row state stay synchronized; stale responses cannot repaint the wrong bank.
6. Keep both 1440 px and 390 px acceptance targets passing, with at least 42 px controls and visible keyboard focus.
7. Missing diagrams are a normal quiet state; do not substitute unrelated assets or invoke rendering from the browser.
8. Leave question-bank artifacts and unrelated repository changes untouched.
