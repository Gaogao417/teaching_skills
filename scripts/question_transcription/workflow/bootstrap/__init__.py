"""Bootstrap / composition root (architecture §3.8, M6).

The SOLE layer that knows concrete provider/adapter implementations and selects them.
- :mod:`.config`        — ``RuntimeAdapterConfig`` (provider/host choice + retry/concurrency budgets);
- :mod:`.dependencies`  — the bound-ports ``WorkflowDependencies`` bundle handed to the graph;
- :mod:`.composition`   — ``bind(config, layout, *, mode)`` selecting and decorating adapters;
- :mod:`.cli`           — ``start`` / ``status`` / ``resume``.

Graph build and node execution never re-read provider choice after bootstrap.
"""
