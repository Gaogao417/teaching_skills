"""Provider/script adapters implementing the workflow ports.

Submodules are imported LAZILY by :mod:`..composition` only when ``mode="live"``,
so the offline test suite never loads model SDKs. Each adapter implements the same
Protocol as the offline fakes; the composition root wraps them in retry/cache/rate-
limit decorators before injecting into the graph.

Layout (M5 — stable capability-based names):

- :mod:`.page_text.{qwen,mimo}`   — page-text OCR adapters
- :mod:`.whole_paper.structured_transcriber` — unified whole-paper transcriber
- :mod:`.source.{extraction,image_attribution,source_paper}` — source deterministic wrappers
- :mod:`.staging.existing_pipeline` — staging pipeline deterministic wrappers
- :mod:`.review.filesystem`       — final-review reader
- :mod:`.decorators`              — retry/cache/rate-limit decorator factories

The historical flat modules (``docx_or_pdf``, ``source_build``, ``downstream``,
``review``) are re-export shims retained for compatibility until M8.
"""
