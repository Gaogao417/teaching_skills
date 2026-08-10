"""Page-text OCR adapters: qwen3.5-ocr (DashScope) and MiMo v2.5.

Both implement :class:`PageTextExtractor` and reuse the shared OCR-style prompt
(direction taken from ``prescan_pdf_pages.PRESCAN_PROMPT``: faithful per-page text +
LaTeX formulae, no question structure, no bbox, no JSON). Each wraps the existing
transport+cache client (``BailianOcrClient`` / ``MimoClient``) so content-addressed
caching and atomic writes come for free.

The OCR prompt version is shared so cache keys and provenance are comparable across
providers; the model id differs.
"""
