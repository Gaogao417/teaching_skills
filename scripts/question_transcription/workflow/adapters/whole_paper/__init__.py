"""Current whole-paper transcriber adapters (architecture §3.6 and §7).

Both implement :class:`WholePaperTranscriber`:

- :mod:`.opencode`    — OpenCode server glm-5.2 (model bound server-side, the default)
- :mod:`.claude_code` — Claude Code via ``claude-agent-sdk`` (model/permission bound per request)

Bound by the composition root; the node never sees which host is in use.
"""
