"""Workflow nodes package.

Each node module exposes ``build_node(deps)`` returning a callable with the LangGraph
node signature ``state -> partial_state`` (or ``state -> Command`` for fan-out).
Nodes only call business ports, verify post-conditions, and commit artifacts — they
never branch on adapter/host type (design §16.13).
"""
