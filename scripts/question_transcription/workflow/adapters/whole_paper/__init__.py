"""Whole-paper transcriber adapters (ports-design §7).

Both implement :class:`WholePaperTranscriber`:

- :mod:`.opencode`    — OpenCode server glm-5.2 (model bound server-side, the default)
- :mod:`.claude_code` — Claude Code runner (port stub for this milestone)

Bound by the composition root; the node never sees which host is in use.
"""
