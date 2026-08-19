#!/usr/bin/env python3
"""Phase 3 dogfood 驱动（P3-09）：以真实 HTTP API 走完整 authoring 链。

对每道题执行：新建教学策略 → TTS 合成教师口述音频（macOS say + ffmpeg，代理录音）
→ 上传（真实 ASR 转写）→ 润色（真实 LLM）→ 编辑 goal/entry/steps（manual edit 留痕）
→ 批准冻结 canonical ApprovedTeachingApproach.v1；可选 second_round 演练
Approved→Draft→重批（v2 Supersede v1）生命周期。全程计时写入 dogfood log。

用法（先启动 review server）：
  python3 question_bank_review_server.py --port 8899 [--canonical-root ...]
  DASHSCOPE_API_KEY=... python3 phase3_dogfood.py \
    --data ../data/phase3-dogfood-similarity.yaml \
    --base-url http://127.0.0.1:8899 --voice Flo \
    --out ../../../../artifacts/canonical-authoring/teaching-approach/dogfood/phase3-dogfood-log.yaml
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

SCRIPTS = Path(__file__).resolve().parent


def tts_to_wav(text: str, voice: str, workdir: Path) -> bytes:
    """macOS say → AIFF → ffmpeg 16kHz 单声道 WAV（代理教师录音）。"""
    aiff = workdir / "narration.aiff"
    wav = workdir / "narration.wav"
    subprocess.run(
        ["say", "-v", voice, "-o", str(aiff), text],
        check=True,
        capture_output=True,
        timeout=300,
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(aiff), "-ac", "1", "-ar", "16000", "-f", "wav", str(wav),
        ],
        check=True,
        capture_output=True,
        timeout=300,
    )
    return wav.read_bytes()


def run_one(
    client: httpx.Client,
    entry: dict[str, Any],
    *,
    voice: str,
    workdir: Path,
) -> dict[str, Any]:
    entry = {
        "author": "mvp-phase3-dogfood",
        "reviewer": "phase3-dogfood-reviewer",
        "review_note": "结构/答案一致性/skill 绑定通过（dogfood 默认备注）。",
        **entry,
    }
    base = (
        f"/api/banks/{entry['bank_id']}/items/{entry['item_id']}/teaching-approach"
    )
    log: dict[str, Any] = {
        "qt_id": entry["qt_id"],
        "bank_id": entry["bank_id"],
        "item_id": entry["item_id"],
        "timings_seconds": {},
        "ux_notes": [],
    }

    started = time.perf_counter()
    response = client.post(
        f"{base}/approaches",
        json={"title": entry["title"], "author": entry["author"]},
    )
    response.raise_for_status()
    approach_id = response.json()["approaches"][-1]["id"]
    log["approach_id"] = approach_id
    log["timings_seconds"]["create"] = round(time.perf_counter() - started, 3)

    started = time.perf_counter()
    audio = tts_to_wav(entry["narration_script"], voice, workdir)
    log["timings_seconds"]["tts_proxy_recording"] = round(time.perf_counter() - started, 3)
    log["audio_wav_bytes"] = len(audio)

    started = time.perf_counter()
    response = client.post(
        f"{base}/approaches/{approach_id}/audio",
        content=audio,
        headers={"Content-Type": "audio/wav"},
    )
    response.raise_for_status()
    transcript = response.json().get("transcript", "")
    log["timings_seconds"]["upload_and_asr"] = round(time.perf_counter() - started, 3)
    log["asr_transcript_chars"] = len(transcript)

    started = time.perf_counter()
    response = client.post(f"{base}/approaches/{approach_id}/polish")
    response.raise_for_status()
    log["timings_seconds"]["polish"] = round(time.perf_counter() - started, 3)

    editor = entry["author"]
    started = time.perf_counter()
    response = client.put(
        f"{base}/approaches/{approach_id}",
        json={
            "goal": entry["goal"],
            "entry_signal": entry["entry_signal"],
            "editor": editor,
        },
    )
    response.raise_for_status()
    log["timings_seconds"]["edit_goal_entry"] = round(time.perf_counter() - started, 3)

    started = time.perf_counter()
    response = client.put(
        f"{base}/approaches/{approach_id}",
        json={"steps": entry["steps"], "editor": editor},
    )
    response.raise_for_status()
    log["timings_seconds"]["edit_steps"] = round(time.perf_counter() - started, 3)

    started = time.perf_counter()
    response = client.post(
        f"{base}/approaches/{approach_id}/approve",
        json={
            "reviewer_id": entry["reviewer"],
            "review_note": entry["review_note"],
        },
    )
    response.raise_for_status()
    canonical = response.json()["canonical"]
    log["timings_seconds"]["approve_freeze"] = round(time.perf_counter() - started, 3)
    log["canonical_v1"] = canonical

    second = entry.get("second_round")
    if second:
        started = time.perf_counter()
        response = client.put(
            f"{base}/approaches/{approach_id}",
            json={"goal": second["goal"], "editor": editor},
        )
        response.raise_for_status()
        response = client.post(
            f"{base}/approaches/{approach_id}/approve",
            json={
                "reviewer_id": entry["reviewer"],
                "review_note": second["review_note"],
            },
        )
        response.raise_for_status()
        log["canonical_v2"] = response.json()["canonical"]
        log["timings_seconds"]["second_round_edit_reapprove"] = round(
            time.perf_counter() - started, 3
        )
    log["timings_seconds"]["total"] = round(sum(log["timings_seconds"].values()), 3)
    return log


def resume_approve(
    client: httpx.Client,
    entry: dict[str, Any],
) -> dict[str, Any]:
    """续跑：链路已走完（evidence/编辑在案）只差批准时，按 title 找到工作副本补批准。"""
    entry = {
        "author": "mvp-phase3-dogfood",
        "reviewer": "phase3-dogfood-reviewer",
        "review_note": "结构/答案一致性/skill 绑定通过（dogfood 默认备注）。",
        **entry,
    }
    base = (
        f"/api/banks/{entry['bank_id']}/items/{entry['item_id']}/teaching-approach"
    )
    started = time.perf_counter()
    view = client.get(base).json()
    approach = next(
        (a for a in view.get("approaches", []) if a.get("title") == entry["title"]),
        None,
    )
    if approach is None:
        raise RuntimeError(f"未找到 title={entry['title']} 的工作副本")
    if approach.get("approval"):
        return {
            "qt_id": entry["qt_id"],
            "skipped": "already approved",
            "canonical": approach["canonical"],
        }
    response = client.post(
        f"{base}/approaches/{approach['id']}/approve",
        json={
            "reviewer_id": entry["reviewer"],
            "review_note": entry["review_note"],
        },
    )
    response.raise_for_status()
    return {
        "qt_id": entry["qt_id"],
        "canonical": response.json()["canonical"],
        "timings_seconds": {"resume_approve": round(time.perf_counter() - started, 3)},
    }


def resume_re_record(
    client: httpx.Client,
    entry: dict[str, Any],
    *,
    voice: str,
    workdir: Path,
) -> dict[str, Any]:
    """续跑：重录（append-only 新录音修订）→ 重润色 → 重批出新 canonical 版本。

    用于替换质量不合格的代理录音（如 TTS 嗓音资源缺失产生的乱码音频）：
    旧修订与旧 canonical 版本按 append-only 原则保留在历史里。
    """
    entry = {
        "author": "mvp-phase3-dogfood",
        "reviewer": "phase3-dogfood-reviewer",
        "review_note": "结构/答案一致性/skill 绑定通过（dogfood 默认备注）。",
        **entry,
    }
    base = (
        f"/api/banks/{entry['bank_id']}/items/{entry['item_id']}/teaching-approach"
    )
    log: dict[str, Any] = {
        "qt_id": entry["qt_id"],
        "timings_seconds": {},
    }
    view = client.get(base).json()
    approach = next(
        (a for a in view.get("approaches", []) if a.get("title") == entry["title"]),
        None,
    )
    if approach is None:
        raise RuntimeError(f"未找到 title={entry['title']} 的工作副本")
    approach_id = approach["id"]

    started = time.perf_counter()
    audio = tts_to_wav(entry["narration_script"], voice, workdir)
    log["timings_seconds"]["tts_proxy_recording"] = round(time.perf_counter() - started, 3)
    log["audio_wav_bytes"] = len(audio)

    started = time.perf_counter()
    response = client.post(
        f"{base}/approaches/{approach_id}/audio",
        content=audio,
        headers={"Content-Type": "audio/wav"},
    )
    response.raise_for_status()
    transcript = response.json().get("transcript", "")
    log["timings_seconds"]["upload_and_asr"] = round(time.perf_counter() - started, 3)
    log["asr_transcript_chars"] = len(transcript)

    started = time.perf_counter()
    response = client.post(f"{base}/approaches/{approach_id}/polish")
    response.raise_for_status()
    log["timings_seconds"]["polish"] = round(time.perf_counter() - started, 3)

    started = time.perf_counter()
    response = client.post(
        f"{base}/approaches/{approach_id}/approve",
        json={
            "reviewer_id": entry["reviewer"],
            "review_note": f"[重录重批] {entry['review_note']}",
        },
    )
    response.raise_for_status()
    log["canonical"] = response.json()["canonical"]
    log["timings_seconds"]["approve_freeze"] = round(time.perf_counter() - started, 3)
    log["timings_seconds"]["total"] = round(sum(log["timings_seconds"].values()), 3)
    return log


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8899")
    parser.add_argument("--voice", default="Flo")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", default=None, help="只跑指定 qt_id（调试用）")
    parser.add_argument(
        "--resume",
        choices=["approve", "reRecord"],
        default=None,
        help="续跑模式：approve=只补批准；reRecord=重录新修订+重润色+重批出新版本。",
    )
    args = parser.parse_args(argv)

    data = yaml.safe_load(args.data.read_text(encoding="utf-8"))
    entries = data["questions"]
    if args.only:
        entries = [e for e in entries if e["qt_id"] == args.only]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    log = {
        "schema": phase3_dogfood_log_schema(),
        "base_url": args.base_url,
        "voice": args.voice,
        "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "questions": [],
    }
    failures: list[str] = []
    # trust_env=False：仅访问本机 review server，避免环境代理变量劫持 127.0.0.1。
    with httpx.Client(
        base_url=args.base_url, timeout=300.0, trust_env=False
    ) as client:
        for entry in entries:
            print(f"[dogfood] {entry['qt_id']} …", flush=True)
            try:
                if args.resume == "approve":
                    log["questions"].append(resume_approve(client, entry))
                    print(
                        f"[dogfood] {entry['qt_id']} resume-approve ok → "
                        f"{log['questions'][-1].get('canonical', {}).get('artifact_uri', '(skipped)')}",
                        flush=True,
                    )
                    continue
                if args.resume == "reRecord":
                    with tempfile.TemporaryDirectory() as tmp:
                        log["questions"].append(
                            resume_re_record(
                                client, entry, voice=args.voice, workdir=Path(tmp)
                            )
                        )
                    print(
                        f"[dogfood] {entry['qt_id']} re-record ok → "
                        f"{log['questions'][-1]['canonical']['artifact_uri']}",
                        flush=True,
                    )
                    continue
                with tempfile.TemporaryDirectory() as tmp:
                    log["questions"].append(
                        run_one(client, entry, voice=args.voice, workdir=Path(tmp))
                    )
                print(
                    f"[dogfood] {entry['qt_id']} ok → "
                    f"{log['questions'][-1]['canonical_v1']['artifact_uri']}",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — dogfood 全程留痕
                failures.append(f"{entry['qt_id']}: {exc}")
                log["questions"].append({"qt_id": entry["qt_id"], "error": str(exc)})
                print(f"[dogfood] {entry['qt_id']} FAILED: {exc}", flush=True)
    log["completed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    log["failures"] = failures
    args.out.write_text(
        yaml.safe_dump(log, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )
    print(f"[dogfood] log → {args.out}")
    return 1 if failures else 0


def phase3_dogfood_log_schema() -> str:
    return "phase3_dogfood_log/v1"


if __name__ == "__main__":
    raise SystemExit(main())
