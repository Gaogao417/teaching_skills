"""L0 Utilities (architecture §3.1).

Pure general-purpose capabilities with no domain coupling. These may depend only on
the Python standard library (or an explicit pure dependency).

INVARIANTS (architecture §12.1):
- utilities do not import ``question_transcription``;
- utilities do not import LangGraph, PydanticAI or a provider SDK;
- utilities do not read API keys or make network requests;
- utilities do not recognise ``QuestionTranscriptionBundle``, review issues or the
  ingestion run layout.

Submodules:
- :mod:`.files.hashing` — content-addressed SHA-256 helpers;
- :mod:`.files.atomic_write` — atomic file replacement helpers.
"""
