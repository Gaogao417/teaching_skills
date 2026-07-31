"""Compatibility shim — graph state moved to :mod:`.orchestration.langgraph.state`.

The canonical home for the LangGraph state contract is now
``workflow/orchestration/langgraph/state.py`` (architecture §3.5). This module
re-exports the public symbols (including the page-text reducers) so existing imports
keep working until M8 removes the shim.
"""

from __future__ import annotations

from .orchestration.langgraph.reducers import (  # noqa: F401  (canonical re-export)
    PageTextExtractsReducer,
    PageTextFailuresReducer,
    add_page_extract,
    add_page_failure,
)
from .orchestration.langgraph.state import (  # noqa: F401  (canonical re-export)
    WorkflowState,
    WorkflowStateModel,
    dump_state,
    extract_outcome,
    initial_state,
    load_state,
)

__all__ = [
    "PageTextExtractsReducer",
    "add_page_extract",
    "PageTextFailuresReducer",
    "add_page_failure",
    "WorkflowState",
    "WorkflowStateModel",
    "initial_state",
    "dump_state",
    "load_state",
    "extract_outcome",
]
