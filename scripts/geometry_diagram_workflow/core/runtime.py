"""Runtime configuration helpers for local model and Wolfram execution."""

from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from pathlib import Path
from typing import Optional


WINDOWS_WOLFRAM_KERNELS = [
    "C:/Program Files/Wolfram Research/Wolfram/15.0/WolframKernel.exe",
    "C:/Program Files/Wolfram Research/Wolfram/15.0/wolfram.exe",
    "D:/Program Files/Wolfram Research/Wolfram/15.0/WolframKernel.exe",
    "D:/Program Files/Wolfram Research/Wolfram/15.0/wolfram.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.3/WolframKernel.exe",
    "D:/Program Files/Wolfram Research/Wolfram/14.3/WolframKernel.exe",
    "D:/Program Files/Wolfram Research/Wolfram/14.3/wolfram.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.3/wolfram.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.2/WolframKernel.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.2/wolfram.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.1/WolframKernel.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.1/wolfram.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.0/WolframKernel.exe",
    "C:/Program Files/Wolfram Research/Wolfram/14.0/wolfram.exe",
]

MACOS_WOLFRAM_KERNELS = [
    "/Applications/Wolfram.app/Contents/MacOS/WolframKernel",
    "/Applications/Mathematica.app/Contents/MacOS/WolframKernel",
    "/Applications/Wolfram Engine.app/Contents/MacOS/WolframKernel",
]


PATH_WOLFRAM_EXECUTABLES = (
    "wolfram",
    "WolframKernel",
    "WolframKernel.exe",
    "wolframscript",
    "wolframscript.exe",
)

SECRET_ENV_NAMES = (
    "GSB_API_KEY",
    "DASHSCOPE_API_KEY",
    "OPENAI_API_KEY",
    "VISION_API_KEY",
    "GSB_VISION_API_KEY",
)


def configure_utf8_stdio() -> None:
    """Make CLI output robust on Windows consoles with non-UTF-8 defaults."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def project_root() -> Path:
    """Return the repository root, independent of the caller's cwd."""
    return Path(__file__).resolve().parent.parent


def wl_dir() -> Path:
    return project_root() / "wl"


def _normalize_executable(value: str) -> str:
    return os.path.expandvars(os.path.expanduser(value.strip().strip('"').strip("'")))


def _resolve_existing_executable(value: str, source: str) -> str:
    normalized = _normalize_executable(value)
    if not normalized:
        raise RuntimeError(f"{source} is empty")

    path = Path(normalized)
    if path.exists():
        return str(path)

    if path.parent == Path("."):
        found = shutil.which(normalized)
        if found:
            return found

    raise FileNotFoundError(
        f"{source} points to a Wolfram kernel that was not found: {normalized}"
    )


def resolve_wolfram_kernel(config_value: Optional[str] = None) -> str:
    """Resolve a Wolfram kernel executable for Windows/macOS/Linux.

    Precedence:
    1. Explicit request/config value (`wl_kernel`).
    2. Environment variables.
    3. Well-known Windows/macOS install paths.
    4. PATH lookup.
    """
    if config_value:
        return _resolve_existing_executable(config_value, "wl_kernel")

    for env_name in ("GSB_WL_KERNEL", "WOLFRAM_KERNEL", "WOLFRAM_KERNEL_PATH"):
        value = os.getenv(env_name)
        if value:
            return _resolve_existing_executable(value, env_name)

    system = platform.system()
    candidates = []
    if system == "Windows":
        candidates.extend(WINDOWS_WOLFRAM_KERNELS)
        candidates.extend(MACOS_WOLFRAM_KERNELS)
    elif system == "Darwin":
        candidates.extend(MACOS_WOLFRAM_KERNELS)
        candidates.extend(WINDOWS_WOLFRAM_KERNELS)
    else:
        candidates.extend(MACOS_WOLFRAM_KERNELS)
        candidates.extend(WINDOWS_WOLFRAM_KERNELS)
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate

    for executable in PATH_WOLFRAM_EXECUTABLES:
        found = shutil.which(executable)
        if found:
            return found

    searched = [
        "env GSB_WL_KERNEL/WOLFRAM_KERNEL/WOLFRAM_KERNEL_PATH",
        *candidates,
        "PATH: " + ", ".join(PATH_WOLFRAM_EXECUTABLES),
    ]
    raise FileNotFoundError(
        "Wolfram kernel not found. Install Wolfram Engine/Mathematica or set "
        "GSB_WL_KERNEL to the WolframKernel/wolfram executable. Searched: "
        + "; ".join(searched)
    )


def redact_secrets(text: object) -> str:
    """Redact common key/token patterns before sending text to stdout/JSON logs."""
    redacted = str(text)
    for env_name in SECRET_ENV_NAMES:
        value = os.getenv(env_name)
        if value and len(value) >= 8:
            redacted = redacted.replace(value, f"<redacted:{env_name}>")
    keyed_patterns = [
        r"(?i)(api[_-]?key\s*[=:]\s*)['\"]?[^'\"\s,}]+",
        r"(?i)(authorization\s*[=:]\s*)['\"]?[^'\"\s,}]+",
        r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+",
        r"(?i)(token\s*[=:]\s*)['\"]?[^'\"\s,}]+",
    ]
    for pattern in keyed_patterns:
        redacted = re.sub(pattern, r"\1<redacted>", redacted)
    redacted = re.sub(r"sk-[A-Za-z0-9._-]+", "sk-<redacted>", redacted)
    return redacted
