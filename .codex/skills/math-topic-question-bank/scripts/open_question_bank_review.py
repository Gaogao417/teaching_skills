#!/usr/bin/env python3
"""Open the local topic question-bank review UI."""

from __future__ import annotations

import argparse
import threading
import webbrowser
from pathlib import Path

import uvicorn

from question_bank_review_server import (
    DEFAULT_BANK_ROOT,
    DEFAULT_NUMBER_REVIEW_URL,
    create_question_bank_app,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank-root", type=Path, default=DEFAULT_BANK_ROOT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--number-review-url", default=DEFAULT_NUMBER_REVIEW_URL)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    url = f"http://{args.host}:{args.port}/"
    print(f"QUESTION BANK REVIEW READY: {url}")
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    uvicorn.run(
        create_question_bank_app(args.bank_root, args.number_review_url),
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
