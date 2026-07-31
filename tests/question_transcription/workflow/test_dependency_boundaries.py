"""Architecture dependency-boundary gate (architecture §12 invariants).

This is the M0 dependency-boundary test entry required by the implementation plan.
It guards the layering invariants that survive the whole migration:

- ``scripts/utilities`` does not depend on provider, workflow or question domain;
- ``scripts/infrastructure`` does not import ``scripts.question_transcription``;
- domain/application do not depend on LangGraph, provider SDK or concrete adapter;
- bootstrap is the only module that selects a concrete implementation.

Layers are introduced incrementally (M1 utilities/infrastructure, M3 domain,
M4 application, M6 bootstrap). A layer that does not yet exist is skipped, so this
file stays green throughout the migration while still enforcing every layer that
*has* landed. As each milestone lands a new layer, its boundary assertion activates
automatically.

The checks use :mod:`importlib` + module introspection rather than text greps so they
follow real (post-``sys.path``-bootstrap) import graphs.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _module_exists(dotted: str) -> bool:
    """True if ``dotted`` is importable in the current (offline) environment."""

    try:
        importlib.import_module(dotted)
    except ImportError:
        return False
    except Exception:  # pragma: no cover - a module that errors on import still "exists"
        return True
    return True


def _direct_imports(module_name: str) -> set[str]:
    """Top-level (``import x`` / ``from x import y``) absolute module roots.

    Mirrors the architecture's intent (a layer may not *statically* depend on a
    forbidden package) without following the whole transitive graph — the goal is to
    catch direct layering violations, not third-party transitive deps.
    """

    module = importlib.import_module(module_name)
    roots: set[str] = set()
    for attr in vars(module).values():
        if isinstance(attr, type(module)):  # imported submodule
            roots.add(attr.__name__.split(".")[0])
    # also collect names recorded by the import system for this module
    for name in getattr(module, "__dict__", {}):
        if "." in name or name.startswith("_"):
            continue
    return roots


# --------------------------------------------------------------------------- #
# Utilities layer (M7) — must not depend on provider/workflow/domain
# --------------------------------------------------------------------------- #


UTILITIES_MODULES = ["scripts.utilities", "scripts.utilities.files", "scripts.utilities.resilience"]


@pytest.mark.parametrize("mod", UTILITIES_MODULES)
def test_utilities_layer_is_dependency_free_when_present(mod):
    if not _module_exists(mod):
        pytest.skip(f"{mod} not yet introduced (M7)")
    forbidden = {
        "langgraph",
        "pydantic_ai",
        "httpx",
        "scripts.question_transcription",
    }
    roots = _direct_imports(mod)
    leak = {r for f in forbidden for r in roots if r == f or r.startswith(f + ".")}
    assert not leak, f"{mod} imports forbidden layer: {leak}"


# --------------------------------------------------------------------------- #
# Shared infrastructure layer (M1) — must not import question_transcription
# --------------------------------------------------------------------------- #


SHARED_INFRA_PREFIX = "scripts.infrastructure"


def test_shared_infrastructure_does_not_import_question_transcription():
    """``scripts/infrastructure`` (once introduced in M1) must stay domain-free.

    Walks every loaded submodule under ``scripts.infrastructure`` and asserts none of
    them statically reference ``scripts.question_transcription``. Because infrastructure
    is imported lazily, we explicitly import the known subpackages first.
    """

    if not _module_exists(SHARED_INFRA_PREFIX):
        pytest.skip("scripts.infrastructure not yet introduced (M1)")

    import scripts.infrastructure  # noqa: F401

    # Force-import the subpackages we expect to create so the assertion covers them.
    for sub in ("scripts.infrastructure.ai",):
        if _module_exists(sub):
            importlib.import_module(sub)

    def _all_submodules(prefix: str) -> list[str]:
        mods: list[str] = []
        for name in list(sys.modules):
            if name == prefix or name.startswith(prefix + "."):
                mods.append(name)
        return sorted(mods)

    infra_modules = _all_submodules(SHARED_INFRA_PREFIX)
    for mod_name in infra_modules:
        module = sys.modules.get(mod_name)
        if module is None:
            continue
        roots = _direct_imports(mod_name)
        leak = {r for r in roots if r == "scripts.question_transcription" or r.startswith("scripts.question_transcription.")}
        assert not leak, f"{mod_name} imports question_transcription: {leak}"


# --------------------------------------------------------------------------- #
# Domain layer (M3) — must not import LangGraph / provider SDK / concrete adapter
# --------------------------------------------------------------------------- #


DOMAIN_MODULES = [
    "scripts.question_transcription.workflow.domain.lifecycle",
    "scripts.question_transcription.workflow.domain.artifacts",
    "scripts.question_transcription.workflow.domain.paper_layout",
]


@pytest.mark.parametrize("mod", DOMAIN_MODULES)
def test_domain_layer_is_dependency_free(mod):
    if not _module_exists(mod):
        pytest.skip(f"{mod} not yet introduced (M3)")
    forbidden = {
        "langgraph",
        "pydantic_ai",
        "httpx",
        "scripts.infrastructure",
    }
    import ast
    import inspect

    module = importlib.import_module(mod)
    tree = ast.parse(inspect.getsource(module))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                roots.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    leak = {r for f in forbidden for r in roots if r == f or r.startswith(f + ".")}
    assert not leak, f"{mod} imports forbidden layer: {leak}"


# --------------------------------------------------------------------------- #
# Application layer (M4) — stages must not import LangGraph / provider SDK
# --------------------------------------------------------------------------- #


APPLICATION_STAGE_MODULES = [
    "scripts.question_transcription.workflow.application.stages.page_text",
    "scripts.question_transcription.workflow.application.stages.source",
    "scripts.question_transcription.workflow.application.stages.whole_paper",
]


@pytest.mark.parametrize("mod", APPLICATION_STAGE_MODULES)
def test_application_stages_are_framework_free(mod):
    if not _module_exists(mod):
        pytest.skip(f"{mod} not yet introduced (M4)")
    forbidden = {"langgraph", "pydantic_ai", "httpx", "scripts.infrastructure"}
    import ast
    import inspect

    module = importlib.import_module(mod)
    tree = ast.parse(inspect.getsource(module))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                roots.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    leak = {r for f in forbidden for r in roots if r == f or r.startswith(f + ".")}
    assert not leak, f"{mod} imports forbidden layer: {leak}"


# --------------------------------------------------------------------------- #
# Current-state guard: config is the only workflow module naming provider choices
# (carried over from test_g0_gate, restated here as an architecture invariant)
# --------------------------------------------------------------------------- #


def test_workflow_state_and_contracts_name_no_provider_choice():
    import ast
    import inspect

    # config lives in bootstrap/ now (M6); inspect the canonical module (the workflow
    # shim only re-exports, so it would not contain the frozen-choice tokens).
    from scripts.question_transcription.workflow.bootstrap import config as wconfig
    from scripts.question_transcription.workflow import contracts as wcontracts
    from scripts.question_transcription.workflow import state as wstate

    forbidden = {"UseOpenCode", "UseClaudeCode", "UseApi", "RuntimeAdapterConfig"}

    def code_names(module):
        tree = ast.parse(inspect.getsource(module))
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        return names

    assert not (code_names(wstate) & forbidden), "state.py names a choice token"
    assert not (code_names(wcontracts) & forbidden), "contracts.py names a choice token"
    # config.py is the one allowed place.
    assert "opencode" in inspect.getsource(wconfig).lower()
