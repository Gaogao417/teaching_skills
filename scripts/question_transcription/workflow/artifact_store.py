"""Atomic artifact store — commit validated artifacts by path + sha256 (design §7).

Run layout (under the gitignored repo-root ``build/``)::

    build/question-ingestion/<paper-id>/<run-id>/
        run-manifest.yaml
        source/source-ref.yaml
        pages/page-NNN.txt + page-NNN.extract.yaml
        structured/{transcription,image-attribution,paper.source,paper.draft}.yaml
        review/{review-issues,review-resolutions}.yaml
        reports/{assembly,audit,trace-summary}.yaml
        cache/provider-results/

Commit discipline (design §7, §16): write a sibling ``.tmp``, validate via Pydantic
(or schema name), compute SHA-256, ``os.replace`` to the final path, then return an
:class:`~.contracts.ArtifactRef`. A node never writes a partial success to a final
artifact path. The graph state only ever holds ``ArtifactRef`` — bytes never enter
the checkpoint (design §16.2).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml
from pydantic import BaseModel

from .contracts import ArtifactRef


__all__ = [
    "RunLayout",
    "ArtifactStore",
    "sha256_file",
    "sha256_bytes",
    "atomic_write_text",
    "atomic_write_yaml",
]


_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def sha256_bytes(data: bytes) -> str:
    """Return the ``sha256:<hex>`` fingerprint of ``data``."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    """Stream-hash a file in 1 MiB chunks, returning ``sha256:<hex>``."""

    h = hashlib.sha256()
    with Path(path).open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def atomic_write_text(path: Path | str, text: str) -> None:
    """Atomically write UTF-8 ``text`` to ``path`` via a sibling ``.tmp`` + replace."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, target)


def atomic_write_yaml(path: Path | str, value: Any) -> None:
    """Atomically dump ``value`` as YAML (stable, unicode, no sort)."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(
            value,
            fp,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
        )
    os.replace(tmp, target)


class RunLayout:
    """Deterministic per-run directory layout (design §7).

    All paths are relative to ``build_root`` (default repo-root ``build/``). The
    layout is created lazily; tests may point ``build_root`` at a tmp_path.
    """

    def __init__(
        self, build_root: Path | str, paper_id: str, run_id: str
    ) -> None:
        self.build_root = Path(build_root)
        self.paper_id = paper_id
        self.run_id = run_id
        self.root = self.build_root / "question-ingestion" / paper_id / run_id

    # -- subdirectories ----------------------------------------------------- #
    @property
    def source_dir(self) -> Path:
        return self.root / "source"

    @property
    def pages_dir(self) -> Path:
        return self.root / "pages"

    @property
    def structured_dir(self) -> Path:
        return self.root / "structured"

    @property
    def review_dir(self) -> Path:
        return self.root / "review"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache" / "provider-results"

    @property
    def manifest_path(self) -> Path:
        return self.root / "run-manifest.yaml"

    # -- known artifact paths ---------------------------------------------- #
    @property
    def page_text_path_template(self) -> str:
        return "page-{n:03d}.txt"

    def page_text_path(self, page_number: int) -> Path:
        return self.pages_dir / f"page-{page_number:03d}.txt"

    def page_sidecar_path(self, page_number: int) -> Path:
        return self.pages_dir / f"page-{page_number:03d}.extract.yaml"

    @property
    def transcription_path(self) -> Path:
        return self.structured_dir / "transcription.yaml"

    @property
    def image_attribution_path(self) -> Path:
        return self.structured_dir / "image-attribution.yaml"

    @property
    def source_paper_path(self) -> Path:
        return self.structured_dir / "paper.source.yaml"

    @property
    def draft_path(self) -> Path:
        return self.structured_dir / "paper.draft.yaml"

    @property
    def review_issues_path(self) -> Path:
        return self.review_dir / "review-issues.yaml"

    @property
    def review_resolutions_path(self) -> Path:
        return self.review_dir / "review-resolutions.yaml"

    @property
    def assembly_report_path(self) -> Path:
        return self.reports_dir / "assembly-report.yaml"

    @property
    def audit_report_path(self) -> Path:
        return self.reports_dir / "audit-report.yaml"

    @property
    def trace_summary_path(self) -> Path:
        return self.reports_dir / "trace-summary.yaml"

    def ensure(self) -> "RunLayout":
        """Create all subdirectories (idempotent)."""
        for d in (
            self.source_dir,
            self.pages_dir,
            self.structured_dir,
            self.review_dir,
            self.reports_dir,
            self.cache_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        return self


class ArtifactStore:
    """Commit validated artifacts and return ``ArtifactRef`` handles.

    The store never validates business semantics — it only guarantees atomicity,
    sha256 fingerprinting, and a schema tag. Pydantic validation is the caller's
    responsibility (use :meth:`commit_model` for a typed commit).
    """

    def __init__(self, layout: RunLayout) -> None:
        self.layout = layout

    # -- raw commits -------------------------------------------------------- #
    def commit_text(self, rel_path: Path | str, text: str, schema: str) -> ArtifactRef:
        """Atomically write ``text`` and return its ``ArtifactRef``."""

        path = self.layout.root / rel_path
        atomic_write_text(path, text)
        return ArtifactRef(
            path=str(rel_path),
            sha256=sha256_bytes(text.encode("utf-8")),
            schema=schema,
        )

    def commit_bytes(
        self, rel_path: Path | str, data: bytes, schema: str
    ) -> ArtifactRef:
        """Atomically write raw ``data`` and return its ``ArtifactRef``."""

        path = self.layout.root / rel_path
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        return ArtifactRef(
            path=str(rel_path), sha256=sha256_bytes(data), schema=schema
        )

    def commit_yaml(
        self, rel_path: Path | str, value: Any, schema: str
    ) -> ArtifactRef:
        """Atomically dump ``value`` as YAML and return its ``ArtifactRef``."""

        path = self.layout.root / rel_path
        atomic_write_yaml(path, value)
        return ArtifactRef(
            path=str(rel_path),
            sha256=sha256_file(path),
            schema=schema,
        )

    def commit_model(self, rel_path: Path | str, model: BaseModel, schema: str) -> ArtifactRef:
        """Dump a Pydantic model by alias/exclude-none and commit as YAML.

        Mirrors the existing ``adapt_*_images.py`` CLIs which validate the dict via
        ``ImageAttributionBundle.model_validate`` before writing by-alias YAML.
        """

        return self.commit_yaml(
            rel_path, model.model_dump(by_alias=True, exclude_none=True, mode="json"), schema
        )

    # -- manifest ----------------------------------------------------------- #
    def write_manifest(self, run_id: str, paper_id: str, provenance: dict) -> ArtifactRef:
        """Write the run manifest recording adapter provenance (design §13).

        Provenance is recorded ONCE here for observability; it is NOT read by nodes
        to decide routing (design §16.13). State never stores the adapter choice.
        """

        manifest = {
            "run_id": run_id,
            "paper_id": paper_id,
            "graph_version": "question-ingestion-langgraph/v0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provenance": provenance,
        }
        return self.commit_yaml(self.layout.manifest_path.relative_to(self.layout.root), manifest, "question-ingestion-run-manifest/v1")

    # -- reading ----------------------------------------------------------- #
    def read_text(self, ref: ArtifactRef) -> str:
        path = self.layout.root / ref.path
        return path.read_text(encoding="utf-8")

    def read_yaml(self, ref: ArtifactRef) -> Any:
        path = self.layout.root / ref.path
        with path.open("r", encoding="utf-8") as fp:
            return yaml.safe_load(fp)

    def verify(self, ref: ArtifactRef) -> bool:
        """Re-hash the file and confirm it matches ``ref.sha256``."""

        actual = sha256_file(self.layout.root / ref.path)
        return actual == ref.sha256
