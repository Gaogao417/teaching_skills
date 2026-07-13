from __future__ import annotations

import json
import mimetypes
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any


STATUS_KEYS = ("pending", "running", "stalled", "failed", "incomplete", "success", "conflict")
STAGE_KEYS = ("collect", "agent", "wolfram", "renderer_spec", "tikz", "preview", "audit", "resolve")
TERMINAL_EVENTS = {"agent.end", "workflow.finalize", "generate.end", "render.end"}
TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".log",
    ".tex",
    ".wl",
    ".css",
    ".js",
    ".html",
}


def safe_resolve(root: Path, relative: str | Path) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / relative).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError("path escapes configured artifacts root") from exc
    return candidate


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = {"event": "unparsed", "message": line}
        if isinstance(event, dict):
            events.append(event)
    return events


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _iso_time(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")


def _latest_descendant_mtime(path: Path) -> float:
    latest = _mtime(path)
    for root, dirs, files in os.walk(path):
        dirs[:] = [item for item in dirs if item not in {".latex-workshop", "__pycache__", ".git"}]
        root_path = Path(root)
        for name in files:
            latest = max(latest, _mtime(root_path / name))
    return latest


def _is_audit_success(audit: dict[str, Any]) -> bool:
    if not audit:
        return False
    status = str(audit.get("status") or "").lower()
    if status in {"pass", "ok", "success"}:
        return True
    checks = audit.get("checks")
    if isinstance(checks, dict) and checks:
        return all(value is True for value in checks.values())
    return False


class DiagramArtifactScanner:
    def __init__(self, artifacts_root: str | Path, stale_after_seconds: int = 300) -> None:
        self.artifacts_root = Path(artifacts_root).expanduser().resolve()
        self.stale_after_seconds = stale_after_seconds
        self._candidate_cache: tuple[float, list[Path]] = (0.0, [])

    def search(
        self,
        keyword: str = "",
        status: str = "",
        problems_only: bool = False,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        query = keyword.strip().casefold()
        results: list[dict[str, Any]] = []
        for artifact_dir in self._artifact_dirs():
            relative = artifact_dir.relative_to(self.artifacts_root).as_posix()
            if query and query not in relative.casefold():
                continue
            summary = self._folder_summary(artifact_dir)
            if status == "conflict" and not summary.get("has_conflict"):
                continue
            if status and status != "conflict" and summary["status"] != status:
                continue
            if problems_only and summary["status"] == "success" and not summary.get("has_conflict"):
                continue
            results.append(summary)
        results.sort(key=lambda item: (float(item["latest_activity_epoch"]), str(item["name"])), reverse=True)
        return results[: max(1, min(limit, 250))]

    def folder_detail(self, relative_folder: str) -> dict[str, Any]:
        artifact_dir = safe_resolve(self.artifacts_root, relative_folder)
        diagram_dir = artifact_dir / "build" / "diagram"
        if not artifact_dir.is_dir() or not diagram_dir.is_dir():
            raise FileNotFoundError(relative_folder)

        manifest = _read_json(diagram_dir / "diagram_jobs.json")
        batch = _read_json(diagram_dir / "diagram_batch_report.json")
        manifest_jobs = {
            str(item.get("job_id")): item
            for item in manifest.get("jobs", [])
            if isinstance(item, dict) and item.get("job_id")
        }
        batch_jobs = {
            str(item.get("job_id")): item
            for item in batch.get("jobs", [])
            if isinstance(item, dict) and item.get("job_id")
        }
        jobs_dir = diagram_dir / "jobs"
        job_ids = set(manifest_jobs) | set(batch_jobs)
        if jobs_dir.is_dir():
            job_ids.update(path.name for path in jobs_dir.iterdir() if path.is_dir())

        jobs = [
            self._job_summary(
                artifact_dir,
                job_id,
                manifest_jobs.get(job_id, {}),
                batch_jobs.get(job_id, {}),
            )
            for job_id in sorted(job_ids)
        ]
        folder_summary = self._folder_summary(artifact_dir, jobs=jobs)
        folder_summary.update(
            {
                "assignment_id": manifest.get("assignment_id") or batch.get("assignment_id") or artifact_dir.name,
                "source_assignment": manifest.get("source_assignment") or "",
                "jobs": jobs,
                "assignment_artifacts": self._assignment_artifacts(artifact_dir),
                "pipeline_performance": _read_json(diagram_dir / "pipeline_performance.json"),
            }
        )
        return folder_summary

    def job_detail(self, relative_folder: str, job_id: str) -> dict[str, Any]:
        folder = self.folder_detail(relative_folder)
        job = next((item for item in folder["jobs"] if item["job_id"] == job_id), None)
        if job is None:
            raise FileNotFoundError(job_id)
        artifact_dir = safe_resolve(self.artifacts_root, relative_folder)
        job_dir = safe_resolve(artifact_dir, Path("build") / "diagram" / "jobs" / job_id)
        if not job_dir.is_dir():
            return {**job, "events": [], "rounds": [], "artifact_groups": [], "performance": {}}

        rounds: list[dict[str, Any]] = []
        rounds_dir = job_dir / "rounds"
        if rounds_dir.is_dir():
            for round_dir in sorted(rounds_dir.glob("round_*"), key=self._round_index):
                if not round_dir.is_dir():
                    continue
                audit = _read_json(round_dir / "audit_result.json")
                preview = self._first_existing(
                    round_dir,
                    ["rendered/prompt.preview.png", "rendered/solution.preview.png"],
                )
                rounds.append(
                    {
                        "round_index": self._round_index(round_dir),
                        "status": "success" if _is_audit_success(audit) else (str(audit.get("status")) or "incomplete"),
                        "preview_path": self._relative(preview, artifact_dir) if preview else "",
                        "audit": audit,
                        "modified_at": _iso_time(_latest_descendant_mtime(round_dir)),
                    }
                )

        return {
            **job,
            "events": _read_events(job_dir / "workflow_events.jsonl"),
            "rounds": rounds,
            "artifact_groups": self._artifact_groups(job_dir, artifact_dir),
            "performance": _read_json(job_dir / "performance_profile.json"),
            "workflow_result": _read_json(job_dir / "workflow_result.json"),
            "renderer_result": _read_json(job_dir / "renderer_result.json"),
            "renderer_audit": _read_json(job_dir / "renderer_audit.json"),
        }

    def read_text(self, relative_folder: str, relative_path: str, max_bytes: int = 2_000_000) -> dict[str, Any]:
        artifact_dir = safe_resolve(self.artifacts_root, relative_folder)
        path = safe_resolve(artifact_dir, relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"wrapper_stdout", "wrapper_stderr"}:
            raise ValueError("artifact is not a supported text file")
        raw = path.read_bytes()
        truncated = len(raw) > max_bytes
        content = raw[:max_bytes].decode("utf-8", errors="replace")
        return {
            "path": self._relative(path, artifact_dir),
            "content": content,
            "truncated": truncated,
            "size": len(raw),
            "modified_at": _iso_time(_mtime(path)),
        }

    def resolve_file(self, relative_folder: str, relative_path: str) -> Path:
        artifact_dir = safe_resolve(self.artifacts_root, relative_folder)
        path = safe_resolve(artifact_dir, relative_path)
        if not path.is_file():
            raise FileNotFoundError(relative_path)
        return path

    def resolve_job_dir(self, relative_folder: str, job_id: str) -> Path:
        artifact_dir = safe_resolve(self.artifacts_root, relative_folder)
        job_dir = safe_resolve(artifact_dir / "build" / "diagram" / "jobs", job_id)
        if not job_dir.is_dir():
            raise FileNotFoundError(job_id)
        return job_dir

    def _artifact_dirs(self) -> list[Path]:
        cached_at, cached = self._candidate_cache
        if time.time() - cached_at < 5:
            return cached
        if not self.artifacts_root.is_dir():
            return []
        found: set[Path] = set()
        for diagram_dir in self.artifacts_root.rglob("diagram"):
            if diagram_dir.is_dir() and diagram_dir.name == "diagram" and diagram_dir.parent.name == "build":
                found.add(diagram_dir.parent.parent)
        result = sorted(found)
        self._candidate_cache = (time.time(), result)
        return result

    def _folder_summary(self, artifact_dir: Path, jobs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if jobs is None:
            relative = artifact_dir.relative_to(self.artifacts_root).as_posix()
            detail = self.folder_detail(relative)
            jobs = detail["jobs"]
        counts = {key: 0 for key in STATUS_KEYS}
        for job in jobs:
            counts[str(job["status"])] = counts.get(str(job["status"]), 0) + 1
            if job.get("has_conflict"):
                counts["conflict"] += 1
        counts["total"] = len(jobs)
        precedence = ("failed", "stalled", "running", "incomplete", "pending", "success")
        status = next((key for key in precedence if counts.get(key, 0)), "incomplete")
        reasons: list[str] = []
        warnings: list[str] = []
        for job in jobs:
            if job["status"] != "success":
                reasons.extend(str(item) for item in job.get("status_reasons", []))
            warnings.extend(str(item) for item in job.get("status_warnings", []))
        latest = _latest_descendant_mtime(artifact_dir)
        return {
            "name": artifact_dir.name,
            "path": artifact_dir.relative_to(self.artifacts_root).as_posix(),
            "absolute_path": str(artifact_dir),
            "status": status,
            "status_reasons": list(dict.fromkeys(reasons))[:8],
            "status_warnings": list(dict.fromkeys(warnings))[:8],
            "has_conflict": any(bool(job.get("has_conflict")) for job in jobs),
            "job_counts": counts,
            "preview_count": sum(1 for job in jobs if job.get("preview_path")),
            "latest_activity": _iso_time(latest),
            "latest_activity_epoch": latest,
            "has_resolved_yaml": any(artifact_dir.glob("*.resolved.assignment.yaml")),
            "has_final_pdf": any(artifact_dir.glob("*.pdf")),
        }

    def _job_summary(
        self,
        artifact_dir: Path,
        job_id: str,
        manifest_job: dict[str, Any],
        batch_job: dict[str, Any],
    ) -> dict[str, Any]:
        job_dir = artifact_dir / "build" / "diagram" / "jobs" / job_id
        workflow = _read_json(job_dir / "workflow_result.json")
        renderer = _read_json(job_dir / "renderer_result.json")
        request = _read_json(job_dir / "request.json")
        events = _read_events(job_dir / "workflow_events.jsonl")
        engine = str(manifest_job.get("engine") or request.get("engine") or "")
        variant = str(manifest_job.get("variant") or request.get("variant") or renderer.get("diagram_variant") or "")
        root_preview = self._renderer_path(job_dir, renderer, "preview_png_path", variant, ".preview.png")
        root_tikz = self._renderer_path(job_dir, renderer, "tikz_fragment_path", variant, ".fragment.tex")
        renderer_spec = job_dir / "final_renderer_spec.json"
        workflow_status = str(workflow.get("status") or "").lower()
        renderer_status = str(renderer.get("status") or "").lower()
        agent = workflow.get("agent") if isinstance(workflow.get("agent"), dict) else {}
        selected_round = agent.get("selected_round")
        root_audit_path = job_dir / "renderer_audit.json"
        audit_path = root_audit_path if root_audit_path.is_file() else None
        audit = _read_json(audit_path) if audit_path else {}
        audit_source = audit_path.relative_to(job_dir).as_posix() if audit_path else ""
        wolfram_required = engine == "geometric_scene"
        wolfram_ok = bool((workflow.get("wolfram") or {}).get("success")) if isinstance(workflow.get("wolfram"), dict) else False
        audit_ok = _is_audit_success(audit)
        preview = root_preview
        tikz = root_tikz
        effective_round: int | None = None
        warnings: list[str] = []
        root_complete = bool(root_preview and root_tikz and audit_ok)
        if not root_complete:
            round_evidence = self._successful_round_evidence(job_dir, selected_round, variant)
            if round_evidence:
                preview = round_evidence["preview"]
                tikz = round_evidence["tikz"]
                audit_path = round_evidence["audit_path"]
                audit = round_evidence["audit"]
                audit_ok = True
                audit_source = audit_path.relative_to(job_dir).as_posix()
                effective_round = int(round_evidence["round_index"])
                source_label = "selected" if effective_round == selected_round else "latest successful"
                warnings.append(
                    f"root final artifacts are incomplete; {source_label} round {effective_round} evidence is used"
                )
        last_start = max((index for index, item in enumerate(events) if item.get("event") == "agent.start"), default=-1)
        last_end = max((index for index, item in enumerate(events) if item.get("event") == "agent.end"), default=-1)
        active = last_start > last_end
        latest = _latest_descendant_mtime(job_dir) if job_dir.is_dir() else 0.0
        stale = active and time.time() - latest > self.stale_after_seconds
        resolved = any(artifact_dir.glob("*.resolved.assignment.yaml"))

        stages = {key: "pending" for key in STAGE_KEYS}
        stages["collect"] = "success" if manifest_job or request else "incomplete"
        if active:
            stages["agent"] = "stalled" if stale else "running"
        elif workflow_status == "ok":
            stages["agent"] = "success"
        elif workflow_status in {"failed", "error"}:
            stages["agent"] = "failed"
        elif (job_dir / "scene_payload.json").is_file():
            stages["agent"] = "incomplete"
        if wolfram_required:
            stages["wolfram"] = "success" if wolfram_ok else ("failed" if workflow_status in {"failed", "error"} else "pending")
        else:
            stages["wolfram"] = "not_applicable"
        stages["renderer_spec"] = "success" if renderer_spec.is_file() else "pending"
        if renderer_status == "ok" and tikz:
            stages["tikz"] = "success"
        elif renderer_status in {"failed", "error"}:
            stages["tikz"] = "failed"
        if preview:
            stages["preview"] = "success"
        elif renderer_status in {"failed", "error"}:
            stages["preview"] = "failed"
        stages["audit"] = "success" if audit_ok else ("failed" if audit else "pending")
        stages["resolve"] = "success" if resolved else "pending"

        reasons: list[str] = []
        failed_stage = ""
        if workflow_status in {"failed", "error"}:
            failed_stage = "wolfram" if wolfram_required and not wolfram_ok else "agent"
            reasons.append(str(workflow.get("message") or workflow.get("fail_type") or "workflow failed"))
            base_status = "failed"
        elif renderer_status in {"failed", "error"}:
            failed_stage = "tikz"
            reasons.append(str(renderer.get("message") or renderer.get("fail_type") or "renderer failed"))
            base_status = "failed"
        elif active:
            base_status = "stalled" if stale else "running"
            reasons.append("agent.start has no matching agent.end")
        elif workflow_status == "ok" and (not wolfram_required or wolfram_ok) and renderer_status == "ok" and preview and tikz and audit_ok:
            base_status = "success"
        elif not manifest_job and not job_dir.is_dir():
            base_status = "pending"
        else:
            base_status = "incomplete"
            missing = [key for key in ("renderer_spec", "tikz", "preview", "audit") if stages[key] != "success"]
            reasons.append("missing required evidence: " + ", ".join(missing))

        batch_statuses = {
            str(batch_job.get(key) or "").lower()
            for key in ("status", "workflow_status", "renderer_status")
            if batch_job.get(key)
        }
        conflict = False
        if batch_statuses:
            batch_success = bool(batch_statuses & {"ok", "success"})
            batch_nonfinal = bool(batch_statuses & {"dry_run", "failed", "error", "workflow_failed", "renderer_failed"})
            if base_status == "success" and batch_nonfinal:
                conflict = True
            if base_status == "failed" and batch_success:
                conflict = True
        status = base_status
        if conflict:
            warnings.insert(0, f"batch status {sorted(batch_statuses)} conflicts with actual job state {base_status}")

        rounds = workflow.get("rounds") if isinstance(workflow.get("rounds"), list) else []
        wolfram = workflow.get("wolfram") if isinstance(workflow.get("wolfram"), dict) else {}
        return {
            "job_id": job_id,
            "slot_id": manifest_job.get("slot_id") or batch_job.get("slot_id") or "",
            "variant": variant,
            "engine": engine,
            "diagram_kind": manifest_job.get("diagram_kind") or request.get("diagram_kind") or request.get("diagram_type") or "",
            "required": bool(manifest_job.get("required", True)),
            "status": status,
            "base_status": base_status,
            "status_reasons": list(dict.fromkeys(reasons)),
            "status_warnings": list(dict.fromkeys(warnings)),
            "has_conflict": conflict,
            "audit_source": audit_source,
            "failed_stage": failed_stage,
            "stages": stages,
            "preview_path": self._relative(preview, artifact_dir) if preview else "",
            "tikz_path": self._relative(tikz, artifact_dir) if tikz else "",
            "round_count": max(len(rounds), self._count_round_dirs(job_dir)),
            "selected_round": agent.get("selected_round"),
            "effective_round": effective_round,
            "agent_duration_ms": agent.get("duration_ms"),
            "wolfram_solve_time_s": wolfram.get("solve_time_s"),
            "last_event": events[-1] if events else {},
            "latest_activity": _iso_time(latest),
            "latest_activity_epoch": latest,
            "batch_statuses": sorted(batch_statuses),
        }

    def _successful_round_evidence(
        self,
        job_dir: Path,
        selected_round: object,
        variant: str,
    ) -> dict[str, Any] | None:
        rounds_dir = job_dir / "rounds"
        if not rounds_dir.is_dir():
            return None
        round_dirs = sorted(
            (path for path in rounds_dir.glob("round_*") if path.is_dir()),
            key=self._round_index,
            reverse=True,
        )
        candidates: list[Path] = []
        if isinstance(selected_round, int):
            selected_dir = rounds_dir / f"round_{selected_round}"
            if selected_dir.is_dir():
                candidates.append(selected_dir)
        candidates.extend(path for path in round_dirs if path not in candidates)
        for round_dir in candidates:
            audit_path = self._first_existing(round_dir, ["audit_result.json", "renderer_audit.json"])
            if audit_path is None:
                continue
            audit = _read_json(audit_path)
            if not _is_audit_success(audit):
                continue
            renderer = _read_json(round_dir / "renderer_result.json")
            if str(renderer.get("status") or "ok").lower() not in {"ok", "success"}:
                continue
            preview = self._renderer_path(round_dir, renderer, "preview_png_path", variant, ".preview.png")
            tikz = self._renderer_path(round_dir, renderer, "tikz_fragment_path", variant, ".fragment.tex")
            if preview and tikz:
                return {
                    "round_index": self._round_index(round_dir),
                    "preview": preview,
                    "tikz": tikz,
                    "audit_path": audit_path,
                    "audit": audit,
                }
        return None

    def _assignment_artifacts(self, artifact_dir: Path) -> list[dict[str, Any]]:
        paths: list[Path] = []
        for pattern in ("*.assignment.yaml", "*.tex", "*.pdf", "01-structure-analysis.md"):
            paths.extend(path for path in artifact_dir.glob(pattern) if path.is_file())
        diagram_dir = artifact_dir / "build" / "diagram"
        for name in ("diagram_jobs.json", "diagram_batch_report.json", "pipeline_performance.json"):
            if (diagram_dir / name).is_file():
                paths.append(diagram_dir / name)
        return [self._file_meta(path, artifact_dir) for path in sorted(set(paths))]

    def _artifact_groups(self, job_dir: Path, artifact_dir: Path) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {
            "请求与计划": [],
            "Agent 与 GeometricScene": [],
            "Wolfram 求解": [],
            "Renderer 与 TikZ": [],
            "预览": [],
            "审核": [],
            "性能": [],
            "日志": [],
            "其他": [],
        }
        for path in sorted(item for item in job_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(job_dir).as_posix().lower()
            name = path.name.lower()
            if name in {"request.json", "request.gsb.json", "teaching_request.json"}:
                group = "请求与计划"
            elif "scene_payload" in name or name.endswith(".wl") or name == "agent_result.json":
                group = "Agent 与 GeometricScene"
            elif name == "render_result.json":
                group = "Wolfram 求解"
            elif "renderer_spec" in name or "tikz_spec" in name or name.endswith(".fragment.tex") or name.endswith(".standalone.tex"):
                group = "Renderer 与 TikZ"
            elif path.suffix.lower() in {".png", ".svg", ".pdf"}:
                group = "预览"
            elif "audit" in name:
                group = "审核"
            elif "performance" in name:
                group = "性能"
            elif path.suffix.lower() in {".log", ".txt"} or "events" in name or "stdout" in name or "stderr" in name:
                group = "日志"
            else:
                group = "其他"
            item = self._file_meta(path, artifact_dir)
            item["round"] = self._round_from_relative(relative)
            groups[group].append(item)
        return [{"name": name, "items": items} for name, items in groups.items() if items]

    def _file_meta(self, path: Path, artifact_dir: Path) -> dict[str, Any]:
        stat = path.stat()
        suffix = path.suffix.lower()
        return {
            "name": path.name,
            "path": self._relative(path, artifact_dir),
            "size": stat.st_size,
            "modified_at": _iso_time(stat.st_mtime),
            "kind": "image" if suffix in {".png", ".svg", ".jpg", ".jpeg", ".webp"} else ("pdf" if suffix == ".pdf" else "text" if suffix in TEXT_SUFFIXES else "binary"),
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        }

    def _renderer_path(self, job_dir: Path, renderer: dict[str, Any], key: str, variant: str, suffix: str) -> Path | None:
        configured = renderer.get(key)
        if isinstance(configured, str) and configured:
            candidate = job_dir / configured
            if candidate.is_file():
                return candidate
        rendered = job_dir / "rendered"
        if variant and (rendered / f"{variant}{suffix}").is_file():
            return rendered / f"{variant}{suffix}"
        matches = sorted(rendered.glob(f"*{suffix}")) if rendered.is_dir() else []
        return matches[0] if matches else None

    @staticmethod
    def _first_existing(base: Path, relatives: list[str]) -> Path | None:
        return next((base / relative for relative in relatives if (base / relative).is_file()), None)

    @staticmethod
    def _relative(path: Path, base: Path) -> str:
        return path.resolve().relative_to(base.resolve()).as_posix()

    @staticmethod
    def _round_index(path: Path) -> int:
        try:
            return int(path.name.rsplit("_", 1)[-1])
        except ValueError:
            return 10**9

    @staticmethod
    def _round_from_relative(relative: str) -> int | None:
        parts = relative.split("/")
        if "rounds" not in parts:
            return None
        index = parts.index("rounds") + 1
        if index >= len(parts):
            return None
        try:
            return int(parts[index].rsplit("_", 1)[-1])
        except ValueError:
            return None

    @staticmethod
    def _count_round_dirs(job_dir: Path) -> int:
        rounds_dir = job_dir / "rounds"
        return sum(1 for path in rounds_dir.glob("round_*") if path.is_dir()) if rounds_dir.is_dir() else 0
