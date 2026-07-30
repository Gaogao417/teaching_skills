from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / ".codex/skills/math-assignment-latex/scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from repo_paths import find_repo_root  # noqa: E402


def test_find_repo_root_from_nested_skill_directory() -> None:
    assert find_repo_root(SCRIPT_DIR) == REPO_ROOT


def test_compile_script_resolves_repository_python() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT_DIR / "compile_latex.sh")],
        cwd="/tmp",
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert f"Python: {REPO_ROOT / '.venv/bin/python'}" in result.stdout
    assert "repository root not found" not in result.stderr
