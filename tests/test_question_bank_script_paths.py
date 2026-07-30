from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".codex/skills/math-topic-question-bank/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from question_bank_repo import find_repo_root  # noqa: E402


def test_find_repo_root_from_question_bank_skill() -> None:
    assert find_repo_root(SCRIPT_DIR) == REPO_ROOT


def test_moved_script_runs_from_outside_repo() -> None:
    result = subprocess.run(
        [
            str(REPO_ROOT / ".venv/bin/python"),
            str(SCRIPT_DIR / "crop_assignment_assets.py"),
            "--help",
        ],
        cwd="/tmp",
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
