# MathJax Addendum

Status: approved by explicit user request on 2026-07-17.

The user expanded the prior visual contract to require rendered LaTeX. This addendum supersedes only the previous MathJax deferral and no-CDN constraint.

Acceptance:

1. Load the official MathJax 4 `tex-mml-chtml` combined component from jsDelivr and configure `$...$`, `\\(...\\)`, `\\[...\\]`, and `$$...$$` delimiters.
2. Assignment strings continue to enter the DOM through `textContent`; MathJax processes only the reader after insertion.
3. Before replacing previously typeset reader content, call `MathJax.typesetClear([reader])`; after replacement, call `MathJax.typesetPromise([reader])`.
4. A missing or failed CDN leaves readable raw LaTeX and reports a non-blocking status; question navigation remains usable.
5. Dynamic bank/item changes cannot start overlapping typeset operations or allow an older render to overwrite newer content.

Source: MathJax 4 official dynamic-content documentation recommends `typesetClear()` before removing processed content and `typesetPromise()` after inserting replacement content.
