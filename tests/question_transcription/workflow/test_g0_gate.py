"""G0 contract gate tests.

These verify the Wave 0 exit gate (plan §4 G0):
- ``WorkflowState`` serializes round-trip;
- ports are runtime-checkable Protocols and carry NO host/provider attribute;
- importing the workflow package needs no API key;
- the frozen adapter choices live only in ``config`` (state/nodes must not import it).
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.question_transcription.workflow import contracts as wcontracts
from scripts.question_transcription.workflow import state as wstate
from scripts.question_transcription.workflow import config as wconfig


# --------------------------------------------------------------------------- #
# State round-trip
# --------------------------------------------------------------------------- #


def _ref(page: int = 1) -> wcontracts.ArtifactRef:
    return wcontracts.ArtifactRef(
        path=f"pages/page-{page:03d}.txt",
        sha256="sha256:" + "a" * 64,
        schema="text/plain",
    )


def test_state_round_trip_preserves_fields():
    original = wstate.initial_state(
        run_id="run-1",
        paper_id="paper-1",
        source_kind="docx",
        source_archive="documents/x.docx",
    )
    original["extracted_source"] = _ref(0)
    original["page_text_extracts"] = [
        wcontracts.PageTextExtract(
            artifact=wcontracts.PageTextArtifact(
                page_number=2,
                text=_ref(2),
                metadata=_ref(2),
                provenance=wcontracts.ExecutionProvenance(
                    adapter_id="qwen", model="qwen3.5-ocr", prompt_version="v1"
                ),
            )
        ),
        wcontracts.PageTextExtract(
            artifact=wcontracts.PageTextArtifact(
                page_number=1,
                text=_ref(1),
                metadata=_ref(1),
                provenance=wcontracts.ExecutionProvenance(
                    adapter_id="qwen", model="qwen3.5-ocr", prompt_version="v1"
                ),
            )
        ),
    ]
    original["staging_directory"] = "staging/paper-1"

    dumped = wstate.dump_state(original)
    assert dumped["run_id"] == "run-1"
    # reducer should have sorted extracts by page number (1 before 2)
    assert [e["artifact"]["page_number"] for e in dumped["page_text_extracts"]] == [1, 2]

    reloaded = wstate.load_state(dumped)
    assert wstate.dump_state(reloaded) == dumped
    # load_state returns a TypedDict whose values are plain JSON dicts (the graph
    # runtime representation); the typed object comes from WorkflowStateModel.
    assert reloaded["extracted_source"]["path"] == "pages/page-000.txt"
    assert reloaded["extracted_source"]["schema"] == "text/plain"


def test_page_extract_reducer_is_order_independent():
    def make(page: int) -> wcontracts.PageTextExtract:
        return wcontracts.PageTextExtract(
            artifact=wcontracts.PageTextArtifact(
                page_number=page,
                text=_ref(page),
                metadata=_ref(page),
                provenance=wcontracts.ExecutionProvenance(
                    adapter_id="qwen", model="qwen3.5-ocr", prompt_version="v1"
                ),
            )
        )

    forward = wstate.add_page_extract([], [make(3), make(1), make(2)])
    reverse = wstate.add_page_extract([], [make(2), make(3), make(1)])
    assert [e.artifact.page_number for e in forward] == [1, 2, 3]
    assert [e.artifact.page_number for e in reverse] == [1, 2, 3]
    # byte-stable: dumping both yields identical text artifacts
    assert (
        forward[0].artifact.text.sha256 == reverse[0].artifact.text.sha256
    )  # same page -> same content


def test_extract_outcome_projection():
    base = wstate.initial_state(
        run_id="r", paper_id="p", source_kind="pdf", source_archive="a"
    )
    assert wstate.extract_outcome(base) == "running"
    base["terminal_errors"] = ["boom"]
    assert wstate.extract_outcome(base) == "failed"
    base["terminal_errors"] = []
    base["review_state"] = "waiting_for_source_review"
    assert wstate.extract_outcome(base) == "waiting_for_source_review"
    base["review_state"] = "waiting_for_final_review"
    assert wstate.extract_outcome(base) == "waiting_for_final_review"
    base["review_state"] = "all_questions_approved"
    base["staging_directory"] = "staging/p"
    assert wstate.extract_outcome(base) == "completed"


# --------------------------------------------------------------------------- #
# Ports are Protocols, carry no Host attribute, and choice stays in config
# --------------------------------------------------------------------------- #

from scripts.question_transcription.workflow.ports import (
    downstream,
    page_text,
    review,
    source,
    source_build,
    whole_paper,
)

PORT_MODULES = [source, page_text, whole_paper, source_build, downstream, review]


@pytest.mark.parametrize("mod", PORT_MODULES, ids=[m.__name__.split(".")[-1] for m in PORT_MODULES])
def test_ports_define_at_least_one_protocol(mod):
    protocols = [
        obj
        for _, obj in inspect.getmembers(mod, inspect.isclass)
        if getattr(obj, "_is_protocol", False)
    ]
    assert protocols, f"{mod.__name__} defines no Protocol"


@pytest.mark.parametrize("mod", PORT_MODULES, ids=[m.__name__.split(".")[-1] for m in PORT_MODULES])
def test_ports_have_no_host_or_choice_attribute(mod):
    # The design forbids provider/host choice in port CODE (docstrings may still
    # reference the names for documentation). Inspect AST Name/Attribute nodes only.
    tree = ast.parse(inspect.getsource(mod))
    forbidden_names = {"UseQwen", "UseMimo", "UseOpenCode", "UseClaudeCode", "UseApi", "Host"}
    found = {
        n.id for node in ast.walk(tree) if isinstance(node, ast.Name) for n in [node] if isinstance(n, ast.Name)
    }
    found |= {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    leak = found & forbidden_names
    assert not leak, f"port module {mod.__name__} references choice tokens in code: {leak}"


def test_config_is_the_only_module_naming_choices():
    # state.py and contracts.py must NOT reference the choice tokens in code
    # (docstrings are allowed). Inspect AST, not raw source.
    forbidden_names = {"UseOpenCode", "UseClaudeCode", "UseApi", "RuntimeAdapterConfig"}


    def code_names(module):
        tree = ast.parse(inspect.getsource(module))
        names = {n.id for node in ast.walk(tree) if isinstance(node, ast.Name) for n in [node] if isinstance(n, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        return names

    assert not (code_names(wstate) & forbidden_names), "state.py names a choice token"
    assert not (code_names(wcontracts) & forbidden_names), "contracts.py names a choice token"
    # config.py IS allowed to name them.
    assert "opencode" in inspect.getsource(wconfig).lower()
    assert "qwen" in inspect.getsource(wconfig).lower()


def test_default_choices_are_frozen():
    assert wconfig.DEFAULT_PAGE_TEXT_PROVIDER == "qwen"
    assert wconfig.DEFAULT_QWEN_MODEL == "qwen3.5-ocr"
    assert wconfig.DEFAULT_WHOLE_PAPER_ADAPTER == "opencode"
    assert wconfig.DEFAULT_OPENCODE_MODEL == "glm-5.2"


def test_runtime_config_validates_without_api_keys():
    cfg = wconfig.RuntimeAdapterConfig()
    assert cfg.page_text_provider == "qwen"
    assert cfg.whole_paper_adapter == "opencode"
    # No exception means no key was required.
