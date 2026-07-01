#!/usr/bin/env python3
"""Verify local teaching geometry workflow setup with real dependency checks."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from runtime import configure_utf8_stdio, redact_secrets, resolve_wolfram_kernel

configure_utf8_stdio()


def check_file(path: Path, description: str) -> bool:
    if not path.exists():
        print(f"[FAIL] {description}: {path} NOT FOUND")
        return False
    print(f"[OK] {description}: {path}")
    return True


def check_import(module_name: str, package_label: str | None = None) -> bool:
    try:
        importlib.import_module(module_name)
    except Exception as exc:
        label = package_label or module_name
        print(f"[FAIL] {label}: {exc.__class__.__name__}: {redact_secrets(exc)}")
        return False
    print(f"[OK] {package_label or module_name} installed")
    return True


def check_wolfram_kernel() -> bool:
    try:
        kernel = resolve_wolfram_kernel()
        from wolframclient.evaluation import WolframLanguageSession
        from wolframclient.language import wlexpr

        with WolframLanguageSession(kernel) as session:
            result = session.evaluate(wlexpr("1+1"))
        if result != 2:
            print(f"[FAIL] Wolfram kernel returned unexpected 1+1 result: {result}")
            return False
    except Exception as exc:
        print(f"[FAIL] Wolfram kernel test: {redact_secrets(exc)}")
        return False
    print(f"[OK] Wolfram kernel: {kernel}")
    print("[OK] Wolfram 1+1 test")
    return True


def main() -> None:
    print("=== Teaching Geometry Workflow Setup Verification ===")
    print(f"Root: {ROOT}")
    failures = 0

    print()
    print("Directories:")
    for path, desc in [
        (ROOT / "wl", "wl/"),
        (ROOT / "core", "core/"),
        (ROOT / ".codex" / "skills", ".codex/skills/"),
    ]:
        failures += 0 if check_file(path, desc) else 1

    print()
    print("Core files:")
    for path, desc in [
        (ROOT / "wl" / "scene_builders.wl", "scene_builders.wl"),
        (ROOT / "wl" / "bench_core.wl", "bench_core.wl"),
        (ROOT / "core" / "workflow.py", "workflow.py"),
        (ROOT / "core" / "runtime.py", "runtime.py"),
        (ROOT / "requirements.txt", "requirements.txt"),
    ]:
        failures += 0 if check_file(path, desc) else 1

    print()
    print("Python packages:")
    for module, label in [
        ("yaml", "pyyaml"),
        ("openai_codex", "openai-codex"),
        ("wolframclient", "wolframclient"),
    ]:
        failures += 0 if check_import(module, label) else 1

    print()
    print("Wolfram:")
    failures += 0 if check_wolfram_kernel() else 1

    print()
    if failures:
        print(f"=== Verification Failed: {failures} issue(s) ===")
        print("Next steps:")
        print("1. Install Python packages in a venv: python3 -m venv .venv")
        print("2. Install deps: .venv/bin/python -m pip install -r requirements.txt")
        print("3. Set GSB_WL_KERNEL if Wolfram is installed outside common paths")
        sys.exit(1)

    print("=== Verification Complete: OK ===")


if __name__ == "__main__":
    main()
