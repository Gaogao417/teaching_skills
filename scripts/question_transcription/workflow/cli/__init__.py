"""Operator entry points for the question-ingestion workflow.

Batch driver (``batch_transcribe_papers``) and the recovery/resume trio
(``resume_from_barrier`` / ``recover_failed_runs`` / ``retry_page_text``) sit one
layer above the compiled graph: they shell out to or drive
:mod:`..run_live_paper` and operate on its run artifacts. They are the
human-facing CLIs documented in the operator runbook.
"""
