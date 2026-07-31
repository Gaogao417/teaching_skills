"""Workflow orchestration (architecture §3.5).

LangGraph is the orchestration adapter for the question-ingestion workflow. This
package contains only LangGraph-specific concerns: graph state, reducers, routing,
node wrappers, and the compiled graph. Business logic lives in
:mod:`..application.stages`; orchestration nodes are thin wrappers that read state,
call an application stage, and project the result back into state.

LangGraph nodes never instantiate a provider, build a provider payload, or run an
existing question-bank script directly (architecture §3.5).
"""
