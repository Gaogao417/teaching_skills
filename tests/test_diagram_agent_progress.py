from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts" / "diagram_workflow" / "geometry_diagram_workflow" / "core"
sys.path.insert(0, str(ROOT / "scripts" / "diagram_workflow"))
sys.path.insert(0, str(CORE))

from agent_runner import (  # noqa: E402
    _heartbeat_fields,
    _notification_progress_event,
)
from progress_subprocess import run_subprocess_streaming  # noqa: E402


def _notification(method: str, item: object) -> SimpleNamespace:
    return SimpleNamespace(
        method=method,
        payload=SimpleNamespace(item=SimpleNamespace(root=item)),
    )


class DiagramAgentProgressTest(unittest.TestCase):
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
