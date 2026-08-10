"""Fake adapters for offline graph lifecycle tests (E1-E7 must be fully offline).

These implement the real ports (:class:`PageTextExtractor`,
:class:`WholePaperTranscriber`, the deterministic ports) but never touch the network.
They are the test doubles that let the graph's interrupt/resume lifecycle, fan-out
reducer, and barrier logic be exercised without API keys. Real adapters
(qwen3.5-ocr / MiMo / GLM-5.2) live under :mod:`..adapters` and are bound by the
composition root for live runs.
"""
