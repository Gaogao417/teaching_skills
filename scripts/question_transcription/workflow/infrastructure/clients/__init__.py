"""Shared low-level provider clients for the question-ingestion workflow.

OpenAI-compatible HTTP clients (MiMo, BaiLian Qwen-OCR) with deterministic disk
caching. These are technical infrastructure shared by the page-text adapters and
the (legacy) observers; they carry no workflow state.
"""
