from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(CORE))

from agent_runner import (  # noqa: E402
    _codex_agent_worker,
    _heartbeat_fields,
    _notification_progress_event,
    _write_codex_task_sidecar,
)
from progress_subprocess import run_subprocess_streaming  # noqa: E402


def _notification(method: str, item: object) -> SimpleNamespace:
    return SimpleNamespace(
        method=method,
        payload=SimpleNamespace(item=SimpleNamespace(root=item)),
    )


class _QueueCapture:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    def put(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)


@contextmanager
def _fake_codex_sdk(*, failure: str | None = None, thread_id: str = "thread-current"):
    """Install a no-I/O SDK double around the real worker boundary."""

    capture = SimpleNamespace(configs=[], thread_starts=[], names=[], turns=[], resumes=[])

    class ApprovalMode:
        deny_all = "deny_all"

    class Sandbox:
        full_access = "full_access"

    class ThreadSource:
        user = "user"

    class SkillInput:
        def __init__(self, *, name: str, path: str) -> None:
            self.name = name
            self.path = path

    class TextInput:
        def __init__(self, text: str) -> None:
            self.text = text

    class CodexConfig:
        def __init__(self, **kwargs: object) -> None:
            if failure == "config":
                raise RuntimeError("current-config-failed")
            capture.configs.append(kwargs)

    class ItemCompletedNotification:
        pass

    class ThreadTokenUsageUpdatedNotification:
        pass

    class TurnCompletedNotification:
        def __init__(self, turn: object) -> None:
            self.turn = turn

    class FakeStream:
        def __init__(self, turn: object) -> None:
            self.turn = turn

        def __iter__(self):
            payload = TurnCompletedNotification(
                SimpleNamespace(
                    id=self.turn.id,
                    status="completed",
                    duration_ms=23,
                    error=None,
                )
            )
            yield SimpleNamespace(method="turn/completed", payload=payload)

        def close(self) -> None:
            return None

    class FakeTurn:
        id = "turn-current"

        def stream(self) -> FakeStream:
            return FakeStream(self)

    class FakeThread:
        id = thread_id

        def set_name(self, name: str) -> None:
            capture.names.append(name)
            if failure == "set_name":
                raise RuntimeError("current-name-failed")

        def turn(self, run_input: list[object], **kwargs: object) -> FakeTurn:
            capture.turns.append((run_input, kwargs))
            if failure == "turn":
                raise RuntimeError("current-turn-failed")
            return FakeTurn()

    class Codex:
        def __init__(self, *, config: object) -> None:
            self.config = config

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def thread_start(self, **kwargs: object) -> FakeThread:
            capture.thread_starts.append(kwargs)
            if failure == "thread_start":
                raise RuntimeError("current-thread-start-failed")
            return FakeThread()

    sdk = SimpleNamespace(
        ApprovalMode=ApprovalMode,
        Codex=Codex,
        CodexConfig=CodexConfig,
        Sandbox=Sandbox,
        SkillInput=SkillInput,
        TextInput=TextInput,
    )
    generated = SimpleNamespace(
        ItemCompletedNotification=ItemCompletedNotification,
        ThreadSource=ThreadSource,
        ThreadTokenUsageUpdatedNotification=ThreadTokenUsageUpdatedNotification,
        TurnCompletedNotification=TurnCompletedNotification,
    )
    with patch.dict(
        sys.modules,
        {
            "openai_codex": sdk,
            "openai_codex.generated": SimpleNamespace(v2_all=generated),
            "openai_codex.generated.v2_all": generated,
        },
    ):
        yield capture


class DiagramAgentProgressTest(unittest.TestCase):
    def test_human_revision_uses_real_home_user_thread_and_one_named_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real_home = root / "real-codex-home"
            real_home.mkdir()
            sentinel = real_home / "keep.txt"
            sentinel.write_text("owned by user", encoding="utf-8")
            out_dir = root / "job"
            queue = _QueueCapture()
            feedback = "这段用户反馈绝不能进入任务名"

            with patch.dict("os.environ", {"CODEX_HOME": str(real_home)}), _fake_codex_sdk() as capture:
                _codex_agent_worker(
                    queue,
                    prompt=f"revision prompt: {feedback}",
                    output_schema={"type": "object"},
                    cwd=str(ROOT),
                    model="gpt-test",
                    codex_bin="codex-test",
                    skill_inputs=[{"name": "diagram", "path": "/skills/diagram"}],
                    out_dir=str(out_dir),
                    job_id="q1-prompt",
                    review_id="review_0001",
                    requested_round=1,
                )

            self.assertEqual(capture.configs[0]["env"]["CODEX_HOME"], str(real_home))
            self.assertTrue(sentinel.is_file(), "persistent mode must not remove or replace the real CODEX_HOME")
            self.assertEqual(len(capture.thread_starts), 1)
            self.assertEqual(capture.thread_starts[0]["ephemeral"], False)
            self.assertEqual(capture.thread_starts[0]["thread_source"], "user")
            self.assertEqual(capture.thread_starts[0]["approval_mode"], "deny_all")
            self.assertEqual(capture.thread_starts[0]["sandbox"], "full_access")
            self.assertEqual(capture.thread_starts[0]["cwd"], str(ROOT))
            self.assertEqual(capture.thread_starts[0]["model"], "gpt-test")
            self.assertEqual(capture.thread_starts[0]["service_tier"], "fast")
            self.assertEqual(
                capture.thread_starts[0]["config"],
                {
                    "model_reasoning_effort": "medium",
                    "features": {"fast_mode": True},
                },
            )
            self.assertEqual(len(capture.names), 1)
            self.assertIn("q1-prompt", capture.names[0])
            self.assertIn("Round 1", capture.names[0])
            self.assertNotIn(feedback, capture.names[0])
            self.assertLessEqual(len(capture.names[0]), 80)
            self.assertEqual(len(capture.turns), 1)
            run_input, turn_kwargs = capture.turns[0]
            self.assertEqual(run_input[0].name, "diagram")
            self.assertEqual(turn_kwargs["output_schema"], {"type": "object"})
            self.assertEqual(turn_kwargs["approval_mode"], "deny_all")
            self.assertEqual(turn_kwargs["sandbox"], "full_access")
            self.assertEqual(capture.resumes, [])

            sidecar = json.loads(
                (out_dir / "human_reviews" / "review_0001.codex-task.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                sidecar,
                {
                    "schema_version": "diagram-codex-task/v1",
                    "review_id": "review_0001",
                    "agent_thread_id": "thread-current",
                    "created_at": sidecar["created_at"],
                },
            )
            self.assertTrue(sidecar["created_at"])

    def test_ordinary_agent_request_remains_ephemeral_and_uses_isolated_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            real_home = Path(tmp) / "real-codex-home"
            real_home.mkdir()
            (real_home / "auth.json").write_text("{}", encoding="utf-8")
            queue = _QueueCapture()

            with patch.dict("os.environ", {"CODEX_HOME": str(real_home)}), _fake_codex_sdk() as capture:
                _codex_agent_worker(
                    queue,
                    prompt="ordinary batch request",
                    output_schema={"type": "object"},
                    cwd=str(ROOT),
                    model="gpt-test",
                    codex_bin="codex-test",
                    skill_inputs=[],
                )
                isolated_home = Path(capture.configs[0]["env"]["CODEX_HOME"])

            self.assertNotEqual(isolated_home, real_home)
            self.assertFalse(isolated_home.exists(), "ordinary temporary CODEX_HOME should be cleaned")
            self.assertEqual(capture.thread_starts[0]["ephemeral"], True)
            self.assertNotIn("thread_source", capture.thread_starts[0])
            self.assertEqual(capture.names, [])

    def test_human_revision_without_codex_home_uses_user_home_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_user_home = Path(tmp) / "user"
            fallback = fake_user_home / ".codex"
            fallback.mkdir(parents=True)
            out_dir = Path(tmp) / "job"
            with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.home", return_value=fake_user_home), _fake_codex_sdk(
            ) as capture:
                _codex_agent_worker(
                    _QueueCapture(),
                    prompt="human revision",
                    output_schema={"type": "object"},
                    cwd=str(ROOT),
                    model="gpt-test",
                    codex_bin="codex-test",
                    skill_inputs=[],
                    out_dir=str(out_dir),
                    job_id="q1-prompt",
                    review_id="review_0001",
                    requested_round=1,
                )

            self.assertEqual(capture.configs[0]["env"]["CODEX_HOME"], str(fallback))
            self.assertTrue(fallback.is_dir())

    def test_codex_task_sidecar_is_append_once_and_rejects_conflicting_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "codex-home"
            home.mkdir()
            out_dir = root / "job"
            common = {
                "prompt": "human revision",
                "output_schema": {"type": "object"},
                "cwd": str(ROOT),
                "model": "gpt-test",
                "codex_bin": "codex-test",
                "skill_inputs": [],
                "out_dir": str(out_dir),
                "job_id": "q1-prompt",
                "review_id": "review_0001",
                "requested_round": 1,
            }
            with patch.dict("os.environ", {"CODEX_HOME": str(home)}), _fake_codex_sdk(
                thread_id="thread-current"
            ):
                _codex_agent_worker(_QueueCapture(), **common)
            original = (out_dir / "human_reviews" / "review_0001.codex-task.json").read_bytes()
            conflict_queue = _QueueCapture()
            with patch.dict("os.environ", {"CODEX_HOME": str(home)}), _fake_codex_sdk(
                thread_id="thread-conflict"
            ):
                _codex_agent_worker(conflict_queue, **common)

            self.assertEqual(
                (out_dir / "human_reviews" / "review_0001.codex-task.json").read_bytes(),
                original,
            )
            failed = [item for item in conflict_queue.messages if item.get("kind") == "result"][-1]
            self.assertEqual(failed["status"], "failed")
            self.assertIn("conflict", str(failed["error"]).lower())

    def test_codex_task_sidecar_rejects_any_same_review_content_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "job"
            sidecar = out_dir / "human_reviews" / "review_0001.codex-task.json"
            sidecar.parent.mkdir(parents=True)
            sidecar.write_text(
                json.dumps(
                    {
                        "schema_version": "diagram-codex-task/v1",
                        "review_id": "review_0001",
                        "agent_thread_id": "thread-current",
                        "created_at": "existing-created-at",
                    }
                ),
                encoding="utf-8",
            )

            with patch("agent_runner.time.strftime", return_value="different-created-at"):
                with self.assertRaisesRegex(RuntimeError, "sidecar conflict"):
                    _write_codex_task_sidecar(str(out_dir), "review_0001", "thread-current")

            self.assertEqual(json.loads(sidecar.read_text(encoding="utf-8"))["created_at"], "existing-created-at")

    def test_worker_writes_invocation_sidecar_before_name_or_turn_failure(self) -> None:
        for failure, expected_error in (
            ("set_name", "current-name-failed"),
            ("turn", "current-turn-failed"),
        ):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                real_home = root / "codex-home"
                real_home.mkdir()
                out_dir = root / "job"
                queue = _QueueCapture()
                with patch.dict("os.environ", {"CODEX_HOME": str(real_home)}), _fake_codex_sdk(
                    failure=failure
                ):
                    _codex_agent_worker(
                        queue,
                        prompt="human revision",
                        output_schema={"type": "object"},
                        cwd=str(ROOT),
                        model="gpt-test",
                        codex_bin="codex-test",
                        skill_inputs=[],
                        out_dir=str(out_dir),
                        job_id="q1-prompt",
                        review_id="review_0001",
                        requested_round=1,
                    )

                sidecar = json.loads(
                    (out_dir / "human_reviews" / "review_0001.codex-task.json").read_text(encoding="utf-8")
                )
                self.assertEqual(sidecar["review_id"], "review_0001")
                self.assertEqual(sidecar["agent_thread_id"], "thread-current")
                failed = [item for item in queue.messages if item.get("kind") == "result"][-1]
                self.assertEqual(failed["status"], "failed")
                self.assertIn(expected_error, str(failed["error"]))

    def test_thread_start_failure_writes_no_current_sidecar(self) -> None:
        for failure in ("config", "thread_start"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                real_home = root / "codex-home"
                real_home.mkdir()
                out_dir = root / "job"
                queue = _QueueCapture()
                with patch.dict("os.environ", {"CODEX_HOME": str(real_home)}), _fake_codex_sdk(
                    failure=failure
                ):
                    _codex_agent_worker(
                        queue,
                        prompt="human revision",
                        output_schema={"type": "object"},
                        cwd=str(ROOT),
                        model="gpt-test",
                        codex_bin="codex-test",
                        skill_inputs=[],
                        out_dir=str(out_dir),
                        job_id="q1-prompt",
                        review_id="review_0001",
                        requested_round=1,
                    )

                self.assertFalse((out_dir / "human_reviews" / "review_0001.codex-task.json").exists())

    def test_sdk_import_failure_writes_no_current_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "job"
            queue = _QueueCapture()
            with patch.dict(sys.modules, {"openai_codex": None}):
                _codex_agent_worker(
                    queue,
                    prompt="human revision",
                    output_schema={"type": "object"},
                    cwd=str(ROOT),
                    model="gpt-test",
                    codex_bin="codex-test",
                    skill_inputs=[],
                    out_dir=str(out_dir),
                    job_id="q1-prompt",
                    review_id="review_0001",
                    requested_round=1,
                )

            self.assertFalse((out_dir / "human_reviews" / "review_0001.codex-task.json").exists())
            failed = [item for item in queue.messages if item.get("kind") == "result"][-1]
            self.assertEqual(failed["status"], "failed")

    def test_render_command_is_reported_as_wolfram_stage_without_command_text(self) -> None:
        item = SimpleNamespace(
            id="item-1",
            type="commandExecution",
            command="python workflow.py --action render --request secret.json",
            status="inProgress",
            duration_ms=None,
            exit_code=None,
        )

        event = _notification_progress_event(_notification("item/started", item))

        self.assertEqual(event["event"], "agent.stage.started")
        self.assertEqual(event["stage"], "wolfram_render")
        self.assertEqual(event["item_type"], "commandExecution")
        self.assertNotIn("command", event)

    def test_audit_completion_reports_status_and_duration(self) -> None:
        item = SimpleNamespace(
            id="item-2",
            type="commandExecution",
            command="python workflow.py --action audit --request request.json",
            status="completed",
            duration_ms=1840,
            exit_code=0,
        )

        event = _notification_progress_event(_notification("item/completed", item))

        self.assertEqual(event["event"], "agent.stage.completed")
        self.assertEqual(event["stage"], "audit")
        self.assertEqual(event["status"], "completed")
        self.assertEqual(event["duration_ms"], 1840)
        self.assertEqual(event["exit_code"], 0)

    def test_reasoning_event_never_exposes_reasoning_content(self) -> None:
        item = SimpleNamespace(
            id="item-3",
            type="reasoning",
            summary=["private summary"],
            content=["private reasoning"],
        )

        event = _notification_progress_event(_notification("item/started", item))

        self.assertEqual(event["stage"], "agent_reasoning")
        self.assertNotIn("summary", event)
        self.assertNotIn("content", event)

    def test_heartbeat_contains_elapsed_idle_pid_and_latest_stage(self) -> None:
        fields = _heartbeat_fields(
            started_at=100.0,
            last_progress_at=124.5,
            now=140.0,
            process_pid=321,
            stage="preview_render",
        )

        self.assertEqual(
            fields,
            {
                "elapsed_s": 40.0,
                "idle_s": 15.5,
                "pid": 321,
                "stage": "preview_render",
                "status": "running",
                "health": "active",
            },
        )

        stalled = _heartbeat_fields(
            started_at=100.0,
            last_progress_at=100.0,
            now=401.0,
            process_pid=321,
            stage="agent_reasoning",
        )
        self.assertEqual(stalled["health"], "suspected_stall")

    def test_subprocess_stderr_is_forwarded_while_output_is_still_captured(self) -> None:
        visible_stderr = io.StringIO()
        with redirect_stderr(visible_stderr):
            completed = run_subprocess_streaming(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys; "
                        "print('final-json'); "
                        "print('GSB_EVENT {\"event\": \"agent.heartbeat\"}', "
                        "file=sys.stderr, flush=True)"
                    ),
                ],
                cwd=ROOT,
                event_context={"job_id": "q2-prompt"},
            )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("final-json", completed.stdout)
        self.assertIn("agent.heartbeat", completed.stderr)
        self.assertIn('"job_id": "q2-prompt"', visible_stderr.getvalue())
        self.assertIn("heartbeat", visible_stderr.getvalue())

    def test_workflow_wrapper_forwards_inner_gsb_events_with_job_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            request_path = tmp_path / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "schema_version": "diagram-job-request/v2",
                        "job_id": "wrapper-smoke",
                        "engine": "geometric_scene",
                        "diagram_kind": "synthetic_geometry",
                        "variant": "prompt",
                        "disclosure_policy": "clean",
                    }
                ),
                encoding="utf-8",
            )
            fake_core = tmp_path / "fake-gsb" / "core"
            fake_core.mkdir(parents=True)
            (fake_core / "workflow.py").write_text(
                """
import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--action')
parser.add_argument('--request')
parser.add_argument('--out')
args = parser.parse_args()
out = Path(args.out)
out.mkdir(parents=True, exist_ok=True)
print('GSB_EVENT {"event": "agent.heartbeat", "health": "active"}', file=sys.stderr, flush=True)
(out / 'workflow_result.json').write_text(json.dumps({'status': 'ok'}), encoding='utf-8')
print(json.dumps({'status': 'ok'}))
""".lstrip(),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "diagram_workflow" / "run_diagram_workflow.py"),
                    str(request_path),
                    "--job-id",
                    "wrapper-smoke",
                    "--out",
                    str(tmp_path / "out"),
                    "--gsb-root",
                    str(tmp_path / "fake-gsb"),
                    "--python",
                    sys.executable,
                    "--strict",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('"event": "agent.heartbeat"', completed.stderr)
        self.assertIn('"job_id": "wrapper-smoke"', completed.stderr)


if __name__ == "__main__":
    unittest.main()
