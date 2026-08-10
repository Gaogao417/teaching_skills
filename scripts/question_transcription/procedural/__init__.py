"""Legacy procedural ingestion pipeline.

These modules are the pre-LangGraph question-ingestion pipeline (observe → merge →
span-index → adapt-transcription → staging → review). The LangGraph workflow in
:mod:`..workflow` has replaced most of it via a single structured whole-paper
transcriber, but three gaps keep parts of this pipeline live:

- PDF figure attribution (``observe_pdf_pages`` figure bboxes) — the workflow's
  transcriber emits only page-number evidence, so PDF figures still need this path.
- Bank-regression diffing (``compare_existing_staging``) — the workflow never reads
  the existing ``artifacts/题库`` bank.
- The source-review machinery (``review_issue_engine`` / ``apply_review_resolutions``
  / ``build_review_staging``) — the workflow's source gate is wired but currently inert.

Once those gaps close in the workflow, this whole package is deletable.
"""
