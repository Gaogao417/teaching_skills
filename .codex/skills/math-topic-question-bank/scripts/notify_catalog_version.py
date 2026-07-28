#!/usr/bin/env python3
"""通知 Review UI 失效题库缓存（§5.3 / §7 受控 writer 契约）。

ingestion / geometry / resolved writer 改完题库文件后调用，让 Review UI 的读模型重建，
不必等 TTL/watcher 兜底。两种工作模式：

1. ``--bank-dir <dir>``：直接 bump 该 bank 目录下的 ``.catalog-version`` 文件。
   适合 Review UI 在**别的进程**运行、或 writer 不想走 HTTP 的场景。bump 后所有共享
   文件系统的 Review UI 进程在下次读该 bank 时都会重建（ensure_bank_fresh 快速路径）。
2. ``--endpoint <url> --bank <bank_id>``：POST 该 Review UI 的 ``/api/admin/reindex``，
   让**同进程**立即重建。适合 writer 知道 UI 在本机哪个端口跑。

两者可同时用：先 bump 文件（跨进程生效），再 POST endpoint（同进程立即生效，无延迟）。

用法::

    # ingestion 写完 staging 后
    ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/notify_catalog_version.py \\
        --bank-dir artifacts/题库/<source-bank>/staging/<paper-id>

    # 已知 Review UI 在本机 8877
    ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/notify_catalog_version.py \\
        --endpoint http://127.0.0.1:8877 --bank staging:<source-bank>:<paper-id>

    # 两者都做
    ./.venv/bin/python .codex/skills/math-topic-question-bank/scripts/notify_catalog_version.py \\
        --bank-dir <dir> --endpoint http://127.0.0.1:8877 --bank <bank_id>
"""

from __future__ import annotations

import argparse
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def bump_version_file(bank_dir: Path) -> Path:
    """原子写 <bank_dir>/.catalog-version（§5.3），返回写入的路径。

    文件本身是可重建产物（git 忽略）。用 os.replace 原子替换，父目录 mtime 不变。
    """
    if not bank_dir.is_dir():
        raise FileNotFoundError(f"bank 目录不存在：{bank_dir}")
    version_path = bank_dir / ".catalog-version"
    version_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = version_path.with_suffix(".tmp")
    tmp_path.write_text(f"{datetime.now(timezone.utc).isoformat()}\n", encoding="utf-8")
    tmp_path.replace(version_path)
    return version_path


def post_reindex(endpoint: str, bank_id: str | None) -> dict:
    """POST /api/admin/reindex，返回响应 JSON。bank_id 为空则全量重建。"""
    base = endpoint.rstrip("/")
    url = f"{base}/api/admin/reindex"
    body = b""
    if bank_id:
        from urllib.parse import urlencode

        url = f"{url}?{urlencode({'bank': bank_id, 'bump': '1'})}"
    request = urllib.request.Request(url, data=body, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            import json

            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url} → HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 {url}：{exc.reason}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bank-dir",
        type=Path,
        help="直接 bump 该 bank 目录的 .catalog-version（跨进程，文件系统级）。",
    )
    parser.add_argument(
        "--endpoint",
        help="Review UI 的根 URL（如 http://127.0.0.1:8877），POST /api/admin/reindex。",
    )
    parser.add_argument(
        "--bank",
        help="配合 --endpoint：精准失效该 bank_id；省略则全量重建。",
    )
    args = parser.parse_args(argv)

    if not args.bank_dir and not args.endpoint:
        parser.error("至少提供 --bank-dir 或 --endpoint 之一")

    success = True
    if args.bank_dir:
        try:
            version_path = bump_version_file(args.bank_dir)
            print(f"bumped {version_path}")
        except (OSError, FileNotFoundError) as exc:
            print(f"bump 失败：{exc}", file=sys.stderr)
            success = False

    if args.endpoint:
        try:
            result = post_reindex(args.endpoint, args.bank)
            print(f"reindex ok: {result}")
        except (RuntimeError, ValueError) as exc:
            print(f"reindex 失败：{exc}", file=sys.stderr)
            success = False

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
