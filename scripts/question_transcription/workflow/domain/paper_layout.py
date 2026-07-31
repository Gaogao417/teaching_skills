"""``PaperLayout`` — a request/domain semantic, not a provider runtime choice
(architecture §7.4).

Whether a paper is ``interleaved`` (questions and solutions on the same pages) or
``questions_and_solutions_separated`` (question paper and answer/solution file are
separate) is a property of the *source/request*, identical for every provider. The
prompt builder consumes it; no provider adapter branches on it to pick a different
host or model.

The wire values are kept as the existing short strings (``"interleaved"`` /
``"separated"``) so existing serialized states/configs remain valid; this module just
names and owns the type in the domain layer.
"""

from __future__ import annotations

from typing import Literal


__all__ = ["PaperLayout", "PAPER_LAYOUTS", "paper_layout_from_str"]


PaperLayout = Literal["interleaved", "separated"]
"""The two supported whole-paper layouts (architecture §7.4).

- ``interleaved``: questions and solutions appear on the same pages (default).
- ``separated``: the question paper and the answer/solution file are separate.
"""

PAPER_LAYOUTS: tuple[str, ...] = ("interleaved", "separated")


def paper_layout_from_str(value: str | None) -> PaperLayout:
    """Coerce a config/request string into a :data:`PaperLayout`, defaulting to interleaved.

    Used where request semantics meet legacy config (``whole_paper_prompt_mode``).
    """

    if value == "separated":
        return "separated"
    return "interleaved"
