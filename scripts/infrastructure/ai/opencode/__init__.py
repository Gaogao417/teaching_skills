"""OpenCode shared infrastructure (architecture §3.2).

- :mod:`.client` — self-contained HTTP transport for the OpenCode server's
  session/message API (no ``opencode-agent`` dependency).
- :mod:`.pydantic_model` — PydanticAI ``Model`` bridge backed by the client.
"""
