"""Small, file-backed wall-clock profiles for diagram workflow artifacts."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from time import perf_counter
from typing import Iterator


class StageTimer:
    """Collect named wall-clock stages without changing workflow behavior."""

    def __init__(self) -> None:
        self._started = perf_counter()
        self.stages: list[dict[str, float | str]] = []

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        started = perf_counter()
        try:
            yield
        finally:
            self.stages.append({
                "name": name,
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            })

    def payload(self) -> dict[str, object]:
        elapsed_ms = round((perf_counter() - self._started) * 1000, 3)
        return {"total_ms": elapsed_ms, "stages": self.stages}


def write_profile_section(
    out_dir: Path,
    section: str,
    timer: StageTimer,
    *,
    job_id: str = "",
    route: str = "",
    filename: str = "performance_profile.json",
) -> Path:
    """Merge a stage timer into the stable per-job performance artifact."""
    path = out_dir / filename
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data.update({
        "schema_version": "diagram-performance-profile/v1",
        **({"job_id": job_id} if job_id else {}),
    })
    if route and not data.get("route"):
        data["route"] = route
    section_data = timer.payload()
    if route:
        section_data["route"] = route
    data[section] = section_data
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
