"""Application layer (architecture §3.4).

Business ports and framework-agnostic stages. An application stage owns business
preconditions, port calls, contract validation and business-failure mapping; it does
not know whether the caller is LangGraph. LangGraph nodes (in
:mod:`..orchestration.langgraph`) are thin wrappers that read graph state, call a
stage, and project the result back into state.

Submodules:
- :mod:`.stages` — framework-agnostic stage helpers (pure decisions / validation).
"""
