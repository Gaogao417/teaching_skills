"""Whole-paper transcriber adapters (ports-design §7).

All three implement :class:`WholePaperTranscriber`:

- :mod:`.glm_api`     — direct GLM-5.2 API (ZHIPUAI_API_KEY), immediate & route-clean
- :mod:`.opencode`    — OpenCode server glm-5.2 (model bound server-side)
- :mod:`.claude_code` — Claude Code runner (port stub for this milestone)

Bound by the composition root; the node never sees which host is in use.
"""
