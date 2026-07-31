"""Provider/script adapters implementing the workflow ports.

Submodules are imported LAZILY by :mod:`..composition` only when ``mode="live"``,
so the offline test suite never loads model SDKs. Each adapter implements the same
Protocol as the offline fakes; the composition root wraps them in retry/cache/rate-
limit decorators before injecting into the graph.

Layout:

- :mod:`.page_text.{qwen,mimo}`   — page-text OCR adapters
- :mod:`.whole_paper.{opencode,glm_api,claude_code}` — whole-paper transcribers
- :mod:`.{docx_or_pdf,source_build,downstream,review}` — deterministic wrappers
- :mod:`.decorators`              — retry/cache/rate-limit decorator factories
"""
