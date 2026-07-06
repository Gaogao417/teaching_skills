#!/usr/bin/env python3
"""Open the focused review UI for exam-zh explanation assignment YAML."""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from pathlib import Path

from review_server import create_explanation_app, run_explanation_server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("yaml", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()

    try:
        create_explanation_app(args.yaml)
    except Exception as exc:  # noqa: BLE001
        json.dump({"ok": False, "error": str(exc)}, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 1

    url = f"http://{args.host}:{args.port}/"
    result = {"status": "explanation_review_ui_ready", "url": url, "yaml": str(args.yaml)}
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()
    if args.prepare_only:
        return 0
    if not args.no_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        run_explanation_server(args.yaml, args.host, args.port)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
