"""Shared AI infrastructure (architecture §3.2).

Provider-neutral structured-model boundary plus per-provider transports and
PydanticAI ``Model`` bridges. This package is the only place that knows how to talk
to OpenCode / Claude Code transports and turn their responses into a PydanticAI
``ModelResponse``. It is deliberately domain-free: it does not know that the output
schema is a math question, a diagram spec, or anything else.

Layering:
- :mod:`.contracts` — provider-neutral ``ModelFailure`` kinds and the
  :class:`StructuredModel` concept.
- :mod:`.opencode.client` / :mod:`.opencode.pydantic_model` — OpenCode HTTP session
  transport + PydanticAI bridge.
- :mod:`.claude_code.client` / :mod:`.claude_code.pydantic_model` — Claude Agent SDK
  query boundary + PydanticAI bridge.
"""
