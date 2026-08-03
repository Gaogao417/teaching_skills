"""Langfuse observability wrapper for the question-ingestion workflow.

Business code imports :mod:`.langfuse` only — never ``langfuse`` or
``opentelemetry`` directly. The wrapper centralizes client configuration,
attribute masking/redaction, and the offline no-op path.
"""
