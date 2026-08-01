"""Whole-paper transcriber adapter (architecture §3.6 and §7).

A single provider-neutral :class:`StructuredWholePaperTranscriber` implements
:class:`WholePaperTranscriber`. The composition root binds either an OpenCode or a
Claude Code infrastructure ``Model`` (a providerless PydanticAI ``Model``) and hands
it to this transcriber; the node never sees which host is in use. Structured-output
validation and ``Agent(output_type=QuestionTranscriptionBundle)`` retry are identical
across providers.
"""
