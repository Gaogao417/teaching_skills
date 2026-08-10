"""Framework-agnostic application stage helpers (architecture §3.4, M4).

These are the pure decision/validation helpers that application stages use. They do
not import LangGraph and can be unit-tested in isolation. The LangGraph node wrappers
in :mod:`..orchestration` (currently :mod:`....nodes` until the node move) call these
and project the results into graph state.

Submodules:
- :mod:`.page_text` — page-barrier decision and coverage validation;
- :mod:`.source` — source-ready gate decision;
- :mod:`.whole_paper` — whole-paper page-coverage validation.
"""
