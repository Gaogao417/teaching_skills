"""Root pytest configuration.

Adds a single cross-cutting behaviour: tests marked ``live`` (question-ingestion
LangGraph workflow canaries that call real model APIs) are skipped unless the
runner explicitly opts in by setting the ``RUN_LIVE=1`` environment variable or
selecting the marker with ``-m live``. This keeps the default suite fully offline
(AGENTS.md: never print/log key values; live tests must opt in explicitly).
"""

from __future__ import annotations

import os


def pytest_collection_modifyitems(config, items):
    opt_in = os.environ.get("RUN_LIVE") == "1" or any(
        "-m" == opt or opt.startswith("-m") for opt in config.invocation_params.args
    ) and any(
        "live" in arg for arg in config.invocation_params.args if arg.startswith("-m")
    )
    skip_live = not opt_in
    if not skip_live:
        return
    import pytest

    skip_marker = pytest.mark.skip(
        reason="live model canary; run with RUN_LIVE=1 (and keys loaded) to enable"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_marker)
