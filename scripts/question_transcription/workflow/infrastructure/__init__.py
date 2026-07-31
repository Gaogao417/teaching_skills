"""Workflow infrastructure (architecture §3.7).

Technical implementations meaningful only to the question-ingestion workflow:
``RunLayout`` and :class:`~.artifact_store.ArtifactStore`, the LangGraph checkpoint
factory, and the ingestion trace sink / run manifest.

If an implementation here later becomes reusable across workflows, it is promoted to
:mod:`scripts.infrastructure` or :mod:`scripts.utilities`; we do not pre-abstract for
directory symmetry.
"""
