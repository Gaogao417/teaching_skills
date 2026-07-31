"""Shared infrastructure package.

Cross-workflow technical capabilities (architecture §3.2). Subpackages here wrap
external technical systems (AI providers, HTTP transports) so that workflow code
depends on a stable boundary rather than a concrete SDK.

INVARIANT (architecture §12.2): nothing under this package may import
``scripts.question_transcription`` or otherwise depend on the question-ingestion
domain. It must not construct math-question prompts, write ingestion artifacts, or
recognise ``QuestionTranscriptionBundle`` / review / staging lifecycle types.
"""
