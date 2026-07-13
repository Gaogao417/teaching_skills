from __future__ import annotations

import json
import hashlib
import subprocess
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

try:
    from .scanner import safe_resolve
except ImportError:  # pragma: no cover - direct script execution
    from scanner import safe_resolve


RevisionRunner = Callable[..., dict[str, Any] | None]
NONTERMINAL_STATUSES = {"queued", "revision_running"}


class ReviewConflict(RuntimeError):
    pass


class HumanReviewService:
    """Persist human decisions and launch one explicitly requested revision.

    Locks are process-local because the monitor is a single-worker localhost
    tool. Multi-worker hosting would require a file or database lock.
    """

    def __init__(self, artifacts_root: Path, repo_root: Path, runner: RevisionRunner | None = None):
        self.artifacts_root = artifacts_root.resolve()
        self.repo_root = repo_root.resolve()
        self.runner = runner or self._run_revision_subprocess
        self._locks_guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._active_review_ids: set[str] = set()

    def submit(
        self,
        *,
        folder: str,
        job_id: str,
        action_id: str,
        decision: str,
        feedback: str,
        base_round: int | None,
    ) -> tuple[dict[str, Any], bool, Path | None, dict[str, Any] | None]:
        job_dir = self._job_dir(folder, job_id)
        lock = self._job_lock(job_dir)
        with lock:
            feedback = feedback.strip()
            replay = self._find_action(job_dir, action_id)
            if replay:
                if (
                    replay.get("decision") != decision
                    or str(replay.get("feedback") or "") != feedback
                    or (base_round is not None and replay.get("base_round") != base_round)
                ):
                    raise ReviewConflict("action_id already exists with a different review payload")
                return replay, True, None, None

            candidate_round = self._candidate_round(job_dir)
            if base_round is not None and base_round != candidate_round:
                raise ReviewConflict(
                    f"candidate Round changed from {base_round} to {candidate_round}; refresh before reviewing"
                )
            base_round = candidate_round
            if decision == "changes_requested" and not feedback:
                raise ValueError("请输入修改建议")

            current = self._read_json(job_dir / "human_review.json")
            if current.get("status") == "accepted":
                raise ReviewConflict("the current diagram has already been accepted")
            if current.get("status") in NONTERMINAL_STATUSES:
                raise ReviewConflict("a diagram revision is already queued or running")

            audit_status = self._audit_status(job_dir, base_round)
            if decision == "accepted" and audit_status != "pass":
                raise ReviewConflict(
                    f"deterministic audit is {audit_status}; current candidate cannot be accepted"
                )

            review_id = self._next_review_id(job_dir)
            requested_round = None if decision == "accepted" else self._next_round(job_dir)
            now = self._now()
            record: dict[str, Any] = {
                "schema_version": "diagram-human-review/v1",
                "action_id": action_id,
                "review_id": review_id,
                "job_id": job_id,
                "decision": decision,
                "status": "accepted" if decision == "accepted" else "queued",
                "feedback": feedback,
                "base_round": base_round,
                "requested_round": requested_round,
                "deterministic_audit": audit_status,
                "created_at": now,
                "updated_at": now,
                "message": "",
            }
            self._persist_record(job_dir, record)
            if decision == "accepted":
                return record, False, None, None

            self._active_review_ids.add(review_id)
            envelope = self._revision_envelope(job_dir, record)
            request_path = job_dir / "human_reviews" / f"{review_id}.request.json"
            self._atomic_write(request_path, envelope)
            return record, False, request_path, envelope

    def run_revision(
        self,
        *,
        job_dir: Path,
        request_path: Path,
        request: dict[str, Any],
        review_id: str,
    ) -> None:
        lock = self._job_lock(job_dir)
        with lock:
            record = self._read_json(job_dir / "human_review.json")
            if record.get("review_id") != review_id or record.get("status") != "queued":
                return
            record["status"] = "revision_running"
            record["updated_at"] = self._now()
            self._persist_record(job_dir, record)
            self._active_review_ids.add(review_id)

        try:
            with tempfile.TemporaryDirectory(prefix="diagram-round-backup-") as backup_tmp:
                backup_dir = Path(backup_tmp)
                self._backup_rounds(job_dir, backup_dir, request)
                try:
                    result = self.runner(job_dir=job_dir, request_path=request_path, request=request)
                except Exception as exc:
                    round_error = self._validate_round_mutation(job_dir, request)
                    message = str(exc)
                    if round_error:
                        self._restore_rounds(job_dir, backup_dir, request)
                        message = f"{message}; {round_error}; unauthorized round changes rolled back"
                    self._finish(job_dir, review_id, "revision_failed", message)
                    return
                if result is None:
                    return
                expected = record.get("requested_round")
                ok = str(result.get("status") or "").lower() in {"ok", "success"}
                selected = result.get("selected_round")
                if selected is not None and selected != expected:
                    ok = False
                round_error = self._validate_round_mutation(job_dir, request)
                if round_error:
                    ok = False
                    self._restore_rounds(job_dir, backup_dir, request)
                message = str(result.get("message") or "")
                if round_error:
                    message = f"{message}; {round_error}; unauthorized round changes rolled back".strip("; ")
                self._finish(
                    job_dir,
                    review_id,
                    "revision_completed" if ok else "revision_failed",
                    message,
                )
        except Exception as exc:
            self._finish(job_dir, review_id, "revision_failed", str(exc))
        finally:
            with lock:
                self._active_review_ids.discard(review_id)

    def current(self, job_dir: Path, *, recover: bool = True) -> dict[str, Any]:
        job_dir = job_dir.resolve()
        lock = self._job_lock(job_dir)
        with lock:
            record = self._read_json(job_dir / "human_review.json")
            if (
                recover
                and record.get("status") in NONTERMINAL_STATUSES
                and record.get("review_id") not in self._active_review_ids
            ):
                record["status"] = "revision_failed"
                record["message"] = "monitor restart interrupted the queued/running revision"
                record["updated_at"] = self._now()
                self._persist_record(job_dir, record)
            return record

    def _finish(self, job_dir: Path, review_id: str, status: str, message: str) -> None:
        lock = self._job_lock(job_dir)
        with lock:
            record = self._read_json(job_dir / "human_review.json")
            if record.get("review_id") != review_id:
                return
            record["status"] = status
            record["message"] = message
            record["updated_at"] = self._now()
            self._persist_record(job_dir, record)

    def _job_dir(self, folder: str, job_id: str) -> Path:
        artifact_dir = safe_resolve(self.artifacts_root, folder)
        if not artifact_dir.is_dir():
            raise FileNotFoundError(f"artifact folder not found: {folder}")
        job_dir = safe_resolve(artifact_dir / "build" / "diagram" / "jobs", job_id)
        if not job_dir.is_dir():
            raise FileNotFoundError(f"diagram job not found: {job_id}")
        return job_dir

    def _candidate_round(self, job_dir: Path) -> int:
        rounds = self._round_indexes(job_dir)
        existing = set(rounds)
        review = self._read_json(job_dir / "human_review.json")
        requested = review.get("requested_round")
        if (
            review.get("status") in {"queued", "revision_running", "revision_completed", "revision_failed"}
            and isinstance(requested, int)
            and requested in existing
        ):
            return requested
        agent = self._read_json(job_dir / "agent_result.json")
        if isinstance(agent.get("selected_round"), int) and agent["selected_round"] in existing:
            return int(agent["selected_round"])
        workflow = self._read_json(job_dir / "workflow_result.json")
        workflow_agent = workflow.get("agent") if isinstance(workflow.get("agent"), dict) else {}
        if (
            isinstance(workflow_agent.get("selected_round"), int)
            and workflow_agent["selected_round"] in existing
        ):
            return int(workflow_agent["selected_round"])
        return max(rounds) if rounds else 0

    def _audit_status(self, job_dir: Path, round_index: int) -> str:
        audit = self._read_json(job_dir / "rounds" / f"round_{round_index}" / "audit_result.json")
        status = str(audit.get("status") or "").lower()
        return "pass" if status in {"pass", "ok", "success"} else ("block" if audit else "missing")

    def _next_round(self, job_dir: Path) -> int:
        rounds = self._round_indexes(job_dir)
        return (max(rounds) + 1) if rounds else 0

    @staticmethod
    def _round_indexes(job_dir: Path) -> list[int]:
        indexes: list[int] = []
        for path in (job_dir / "rounds").glob("round_*"):
            try:
                indexes.append(int(path.name.removeprefix("round_")))
            except ValueError:
                continue
        return indexes

    def _next_review_id(self, job_dir: Path) -> str:
        numbers: list[int] = []
        for path in (job_dir / "human_reviews").glob("review_*.json"):
            if path.name.endswith(".request.json"):
                continue
            try:
                numbers.append(int(path.stem.removeprefix("review_")))
            except ValueError:
                continue
        return f"review_{(max(numbers) + 1) if numbers else 1:04d}"

    def _find_action(self, job_dir: Path, action_id: str) -> dict[str, Any]:
        for path in sorted((job_dir / "human_reviews").glob("review_*.json")):
            if path.name.endswith(".request.json"):
                continue
            record = self._read_json(path)
            if record.get("action_id") == action_id:
                return record
        return {}

    def _revision_envelope(self, job_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
        base = self._read_json(job_dir / "teaching_request.json") or self._read_json(job_dir / "request.json")
        engine_options = base.get("engine_options") if isinstance(base.get("engine_options"), dict) else {}
        human_revision = {
            "action_id": record["action_id"],
            "review_id": record["review_id"],
            "feedback": record["feedback"],
            "base_round": record["base_round"],
            "requested_round": record["requested_round"],
        }
        diagram_request = {
            **base,
            "engine_options": {**engine_options, "max_retries": 0},
            "human_revision": human_revision,
        }
        return {
            "schema_version": "diagram-human-revision-request/v1",
            "review_id": record["review_id"],
            "job_id": record["job_id"],
            "feedback": record["feedback"],
            "base_round": record["base_round"],
            "requested_round": record["requested_round"],
            "max_retries": 0,
            "existing_rounds": self._round_indexes(job_dir),
            "existing_round_fingerprints": self._round_fingerprints(job_dir),
            "diagram_request": diagram_request,
        }

    def _validate_round_mutation(self, job_dir: Path, request: dict[str, Any]) -> str:
        before = {int(value) for value in request.get("existing_rounds", [])}
        after = set(self._round_indexes(job_dir))
        requested = int(request["requested_round"])
        new_rounds = after - before
        if new_rounds != {requested}:
            return f"revision must add exactly Round {requested}; observed new rounds {sorted(new_rounds)}"
        before_fingerprints = request.get("existing_round_fingerprints") or {}
        after_fingerprints = self._round_fingerprints(job_dir)
        changed = [
            index
            for index in sorted(before)
            if before_fingerprints.get(str(index)) != after_fingerprints.get(str(index))
        ]
        if changed:
            return f"revision modified historical rounds {changed}"
        return ""

    @staticmethod
    def _backup_rounds(job_dir: Path, backup_dir: Path, request: dict[str, Any]) -> None:
        for value in request.get("existing_rounds", []):
            index = int(value)
            source = job_dir / "rounds" / f"round_{index}"
            if source.is_dir():
                shutil.copytree(source, backup_dir / source.name)

    @staticmethod
    def _restore_rounds(job_dir: Path, backup_dir: Path, request: dict[str, Any]) -> None:
        rounds_dir = job_dir / "rounds"
        before = {int(value) for value in request.get("existing_rounds", [])}
        requested = int(request["requested_round"])
        allowed = before | {requested}
        for path in rounds_dir.glob("round_*"):
            try:
                index = int(path.name.removeprefix("round_"))
            except ValueError:
                continue
            if index not in allowed:
                shutil.rmtree(path, ignore_errors=True)
        for index in sorted(before):
            target = rounds_dir / f"round_{index}"
            source = backup_dir / target.name
            if target.exists():
                shutil.rmtree(target)
            if source.is_dir():
                shutil.copytree(source, target)

    @staticmethod
    def _round_fingerprints(job_dir: Path) -> dict[str, str]:
        fingerprints: dict[str, str] = {}
        for index in HumanReviewService._round_indexes(job_dir):
            digest = hashlib.sha256()
            round_dir = job_dir / "rounds" / f"round_{index}"
            for path in sorted(item for item in round_dir.rglob("*") if item.is_file()):
                digest.update(path.relative_to(round_dir).as_posix().encode("utf-8"))
                digest.update(path.read_bytes())
            fingerprints[str(index)] = digest.hexdigest()
        return fingerprints

    def _run_revision_subprocess(
        self,
        *,
        job_dir: Path,
        request_path: Path,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        python = self.repo_root / ".venv-diagram" / "bin" / "python"
        script = self.repo_root / "scripts" / "diagram_workflow" / "run_diagram_workflow.py"
        runtime_dir = job_dir / ".human_review_runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".json",
            prefix=f"{request['review_id']}-",
            dir=runtime_dir,
            delete=False,
        ) as handle:
            json.dump(request["diagram_request"], handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            runtime_request = Path(handle.name)
        command = [
            str(python),
            str(script),
            str(runtime_request),
            "--out",
            str(job_dir),
            "--python",
            str(python),
            "--strict",
        ]
        completed = subprocess.run(command, cwd=self.repo_root, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "diagram revision failed")
        result = self._read_json(job_dir / "agent_result.json")
        return {
            "status": result.get("status"),
            "selected_round": result.get("selected_round"),
            "message": result.get("message", ""),
        }

    def _persist_record(self, job_dir: Path, record: dict[str, Any]) -> None:
        self._atomic_write(job_dir / "human_reviews" / f"{record['review_id']}.json", record)
        self._atomic_write(job_dir / "human_review.json", record)

    def _job_lock(self, job_dir: Path) -> threading.Lock:
        key = str(job_dir.resolve())
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{threading.get_ident()}.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
