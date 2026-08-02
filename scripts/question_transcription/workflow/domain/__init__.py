"""Question-ingestion workflow domain (architecture §3.3).

Stable lifecycle types and value objects for the question-ingestion workflow. The
domain layer expresses the ingestion lifecycle and stable references without depending
on LangGraph, provider SDKs, the file system or subprocess.

The authoritative Pydantic schemas (``SourcePaper``, ``QuestionTranscriptionBundle``,
``ImageAttributionBundle``, ``ReviewIssuesBundle`` / ``ReviewResolutionsBundle``)
remain in :mod:`scripts.question_transcription.{source_contracts,contracts,
review_issue_contracts}`; the domain layer does NOT re-export them, to avoid creating a
second authoritative entry point.

Submodules:
- :mod:`.lifecycle` — review / outcome state discriminators;
- :mod:`.artifacts` — the ``ArtifactRef`` value object.
"""
