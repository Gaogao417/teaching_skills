from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path


def run_subprocess_streaming(
    command: list[str],
    *,
    cwd: Path | None = None,
    event_context: dict[str, object] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Capture a child result while forwarding its live stderr progress.

    ``GSB_EVENT`` records are enriched with the caller's job context before
    being printed. stdout remains captured because workflow CLIs use it for
    their final JSON result. Independent drain threads prevent either pipe
    from blocking a long-running child.
    """

    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd is not None else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    def drain_stdout() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_lines.append(line)

    def drain_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_lines.append(line)
            visible_line = line
            if event_context and line.startswith("GSB_EVENT "):
                try:
                    payload = json.loads(line.removeprefix("GSB_EVENT "))
                    if isinstance(payload, dict):
                        payload = {**event_context, **payload}
                        visible_line = "GSB_EVENT " + json.dumps(
                            payload, ensure_ascii=False
                        ) + "\n"
                except json.JSONDecodeError:
                    pass
            print(visible_line, end="", file=sys.stderr, flush=True)

    stdout_thread = threading.Thread(target=drain_stdout, daemon=True)
    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()
    return subprocess.CompletedProcess(
        command,
        returncode,
        "".join(stdout_lines),
        "".join(stderr_lines),
    )
