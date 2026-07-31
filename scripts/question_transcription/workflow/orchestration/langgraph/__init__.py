"""LangGraph orchestration (architecture §3.5).

- :mod:`.state` — the ``WorkflowState`` TypedDict + reducers + dump/load/outcome;
- :mod:`.reducers` — page-text extract/failure reducers;
- :mod:`.routing` — pure graph-edge routing functions (branch on business state only);
- :mod:`.graph` — the compiled ``StateGraph`` from bound dependencies.
"""
