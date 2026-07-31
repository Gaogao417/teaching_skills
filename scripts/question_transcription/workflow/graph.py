"""Root graph — build the full ingestion StateGraph from bound dependencies.

Topology (design §3.1)::

    Start -> extract_source
       -> [plan_page_text (fan-out) -> extract_page_text xN]   (branch A, text)
       -> barrier -> transcribe_whole_paper
    extract_source -> attribute_images                          (branch B, images)
    transcribe_whole_paper + attribute_images -> build_source_paper
       -> check_source_ready:
            clean   -> build_draft -> complete_evidence -> split -> build_assets
                     -> audit_staging -> refresh_review_ui
            review  -> source_review_wait (interrupt) -> build_source_paper
       -> final_review_check:
            pending -> interrupt -> final_review_check
            rejected-> Failed
            approved-> approved_audit -> End

Edges that route on business state never branch on adapter/host type (design §16.13).
``build_graph`` takes the already-bound :class:`WorkflowDependencies`; the composition
root is the sole place that selected the concrete adapters.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from .orchestration.langgraph.routing import (
    route_after_audit_staging,
    route_after_build_source,
    route_after_final_review,
    route_after_page_barrier,
)
from .orchestration.langgraph.state import WorkflowState
from .dependencies import WorkflowDependencies
from .nodes.downstream import (
    make_audit_staging_node,
    make_build_assets_node,
    make_build_draft_node,
    make_complete_evidence_node,
    make_refresh_review_ui_node,
    make_split_into_questions_node,
)
from .nodes.page_text import make_extract_page_text_node, page_barrier, plan_page_text_dispatch
from .nodes.review import (
    make_approved_audit_node,
    make_final_review_check_node,
    make_source_review_wait_node,
)
from .nodes.source import (
    make_attribute_images_node,
    make_build_source_paper_node,
    make_extract_source_node,
)
from .nodes.whole_paper import make_transcribe_whole_paper_node


__all__ = ["build_graph", "NODE_NAMES"]


NODE_NAMES = [
    "extract_source",
    "attribute_images",
    "extract_page_text",
    "page_barrier",
    "transcribe_whole_paper",
    "build_source_paper",
    "source_review_wait",
    "build_draft",
    "complete_evidence",
    "split_into_questions",
    "build_assets",
    "audit_staging",
    "refresh_review_ui",
    "final_review_check",
    "approved_audit",
]


def build_graph(deps: WorkflowDependencies, checkpointer=None):
    """Compile the ingestion StateGraph from already-bound dependencies.

    Returns a compiled graph (call ``.invoke``/``.stream``/``.astream`` with a
    ``configurable.thread_id``). Pass a ``checkpointer`` (MemorySaver for tests,
    SqliteSaver for dev/recovery) to enable interrupt/resume and persistence.
    """

    graph = StateGraph(WorkflowState)

    # -- register nodes ---------------------------------------------------- #
    graph.add_node("extract_source", make_extract_source_node(deps))
    graph.add_node("attribute_images", make_attribute_images_node(deps))
    graph.add_node("extract_page_text", make_extract_page_text_node(deps))
    graph.add_node("page_barrier", page_barrier)
    graph.add_node("transcribe_whole_paper", make_transcribe_whole_paper_node(deps))
    graph.add_node("build_source_paper", make_build_source_paper_node(deps))
    graph.add_node("source_review_wait", make_source_review_wait_node(deps))
    graph.add_node("build_draft", make_build_draft_node(deps))
    graph.add_node("complete_evidence", make_complete_evidence_node(deps))
    graph.add_node("split_into_questions", make_split_into_questions_node(deps))
    graph.add_node("build_assets", make_build_assets_node(deps))
    graph.add_node("audit_staging", make_audit_staging_node(deps))
    graph.add_node("refresh_review_ui", make_refresh_review_ui_node(deps))
    graph.add_node("final_review_check", make_final_review_check_node(deps))
    graph.add_node("approved_audit", make_approved_audit_node(deps))

    # -- edges: source extraction -> fan-out ------------------------------ #
    graph.add_edge(START, "extract_source")
    # Branch A (text): a conditional edge fans out to one Send per page. LangGraph
    # requires Send objects to come from the edge router, not from node state output.
    # Branch B (images): also starts here, running in parallel with the page fan-out.
    # The conditional router returns Send list; we ALSO need the image branch, so we
    # model the fork explicitly: extract_source -> attribute_images (plain edge) AND
    # extract_source -> [page Sends] (conditional edge). Both coexist.
    graph.add_edge("extract_source", "attribute_images")
    graph.add_conditional_edges(
        "extract_source",
        plan_page_text_dispatch,
        ["extract_page_text"],
    )
    graph.add_edge("extract_page_text", "page_barrier")
    # barrier -> transcribe when ready; on error end. extract_page_text callsites
    # all converge into page_barrier before transcribe.
    graph.add_conditional_edges(
        "page_barrier",
        route_after_page_barrier,
        ["transcribe_whole_paper", END],
    )

    # -- edges: join + source gate ---------------------------------------- #
    # build_source_paper joins transcription + image attribution. The image branch
    # (attribute_images) completes earlier and writes ``image_attribution`` to state;
    # build_source_paper has a single inbound edge from the SLOWER transcription
    # branch, so by the time it runs the image attribution is already in state. This
    # avoids LangGraph firing build_source_paper on the image branch's superstep.
    graph.add_edge("transcribe_whole_paper", "build_source_paper")
    graph.add_edge("attribute_images", END)  # image branch is a leaf that only writes state
    graph.add_conditional_edges(
        "build_source_paper",
        route_after_build_source,
        ["build_draft", "source_review_wait", END],
    )
    # source review loop: interrupt then rebuild.
    graph.add_edge("source_review_wait", "build_source_paper")

    # -- edges: staging pipeline (serial) --------------------------------- #
    graph.add_edge("build_draft", "complete_evidence")
    graph.add_edge("complete_evidence", "split_into_questions")
    graph.add_edge("split_into_questions", "build_assets")
    graph.add_edge("build_assets", "audit_staging")
    graph.add_conditional_edges(
        "audit_staging",
        route_after_audit_staging,
        ["refresh_review_ui", END],
    )
    graph.add_edge("refresh_review_ui", "final_review_check")

    # -- edges: final review loop ----------------------------------------- #
    graph.add_conditional_edges(
        "final_review_check",
        route_after_final_review,
        ["approved_audit", END],
    )
    graph.add_edge("approved_audit", END)

    return graph.compile(checkpointer=checkpointer) if checkpointer else graph.compile()
