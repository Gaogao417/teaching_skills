"""``ArtifactRef`` — the stable value object referencing a committed file artifact
(architecture §3.3, §6).

The graph state only ever holds ``ArtifactRef`` to large objects (page images, page
text, model responses, the full ``paper.source.yaml``); the bytes themselves never
enter the checkpoint (architecture §6 invariant).

The on-disk YAML key is ``schema`` (mirroring the existing ``source_contracts`` /
``contracts`` convention); the Python attribute is ``schema_`` to avoid shadowing the
(deprecated) Pydantic v1 ``BaseModel.schema`` method.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


__all__ = ["ArtifactRef", "StrictModel"]


class StrictModel(BaseModel):
    """Frozen base mirroring the existing contract modules.

    - ``extra="forbid"`` catches typo'd field names at the boundary.
    - ``populate_by_name=True`` lets code construct with either the Python attribute
      name (``schema_=...``) or the on-disk alias (``schema=...``).
    - ``serialize_by_alias=True`` makes ``model_dump()`` emit the on-disk alias
      (``schema``), so round-trips are byte-stable without per-call ``by_alias``.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )


class ArtifactRef(StrictModel):
    """A path + sha256 + schema-name reference to a committed file artifact."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    schema_: str = Field(default=..., alias="schema", min_length=1)
