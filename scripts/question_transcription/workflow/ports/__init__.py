"""Business ports — provider-agnostic ``Protocol`` interfaces (architecture §3.4).

INVARIANT (design §16.13): no port carries a ``Host`` property or a
``UseOpenCode / UseClaudeCode`` parameter. Business nodes can only *call*
the port; they cannot ask or match the host type. The composition root
(:mod:`.composition`) is the sole place that selects and decorates a concrete
adapter.

Submodules:

- :mod:`.source`          — :class:`SourceExtractor` (DOCX/PDF/pages)
- :mod:`.page_text`       — :class:`PageTextExtractor` (qwen/MiMo)
- :mod:`.whole_paper`     — :class:`WholePaperTranscriber` (OpenCode/Claude Code/API)
- :mod:`.source_build`    — :class:`SourcePaperBuilder`
- :mod:`.downstream`      — projector/evidence/expand/materialize/audit/notify
- :mod:`.review`          — :class:`FinalReviewReader`
"""
