#!/usr/bin/env python3
from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path
from urllib.parse import quote

import uvicorn

try:
    from .server import REPO_ROOT, create_app
except ImportError:  # pragma: no cover - direct script execution
    from server import REPO_ROOT, create_app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open the local diagram pipeline monitor")
    parser.add_argument("--query", default="")
    parser.add_argument("--artifacts-root", type=Path, default=REPO_ROOT / "artifacts")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)
    url = f"http://{args.host}:{args.port}/"
    if args.query:
        url += f"?q={quote(args.query)}"
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(args.artifacts_root), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

