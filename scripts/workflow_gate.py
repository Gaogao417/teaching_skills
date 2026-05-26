#!/usr/bin/env python3
"""Small structured-state helper for math-homework-pipeline runs."""

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from datetime import datetime, timezone


RUN_MODES = {
    "new-homework-run",
    "resume-existing-artifact",
    "repair-existing-artifact",
    "workflow-maintenance",
    "explanation-only",
}

PASS_VERDICTS = {"PASS", "PASS_WITH_NOTES"}


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    ensure_dir(os.path.dirname(path) or ".")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")


def print_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def artifact_dir_path(args):
    return os.path.abspath(args.artifact_dir)


def manifest_path(artifact_dir):
    return os.path.join(artifact_dir, "run_manifest.json")


def ledger_path(artifact_dir):
    return os.path.join(artifact_dir, "build", "review-ledger.jsonl")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def default_marker_for(yaml_path):
    if yaml_path.endswith(".assignment.yaml"):
        return yaml_path[: -len(".assignment.yaml")] + ".reviewed"
    if yaml_path.endswith(".yaml"):
        return yaml_path[: -len(".yaml")] + ".reviewed"
    return yaml_path + ".reviewed"


def load_manifest(artifact_dir):
    return read_json(manifest_path(artifact_dir), {
        "schema_version": 1,
        "artifact_dir": artifact_dir,
        "created_at": now_iso(),
        "updated_at": None,
        "run_mode": None,
        "goal": None,
        "inputs": {},
        "stages": {},
        "deliverables": {},
        "intermediates": {},
        "do_not_commit": ["build/*.log", "build/exam-zh*.sty", "build/exam-zh.cls"],
        "commits": [],
    })


def save_manifest(artifact_dir, manifest):
    manifest["updated_at"] = now_iso()
    write_json(manifest_path(artifact_dir), manifest)


def cmd_init_manifest(args):
    artifact_dir = artifact_dir_path(args)
    if args.run_mode not in RUN_MODES:
        raise SystemExit(f"Unsupported run_mode: {args.run_mode}")
    ensure_dir(artifact_dir)
    manifest = load_manifest(artifact_dir)
    manifest["artifact_dir"] = artifact_dir
    manifest["run_mode"] = args.run_mode
    manifest["goal"] = args.goal
    if args.inputs_json:
        manifest["inputs"] = json.loads(args.inputs_json)
    manifest["stages"].setdefault("S0", {})
    manifest["stages"]["S0"].update({
        "name": "输入/运行模式检查",
        "status": "PASS",
        "run_mode": args.run_mode,
        "timestamp": now_iso(),
    })
    save_manifest(artifact_dir, manifest)
    print_json({"status": "OK", "manifest": manifest_path(artifact_dir)})


def cmd_stage(args):
    artifact_dir = artifact_dir_path(args)
    manifest = load_manifest(artifact_dir)
    stage = {
        "name": args.name,
        "status": args.status,
        "timestamp": now_iso(),
    }
    if args.artifact:
        stage.setdefault("artifacts", []).append(os.path.abspath(args.artifact))
    if args.skip_reason:
        stage["skip_reason"] = args.skip_reason
    if args.verdict:
        stage["verdict"] = args.verdict
    manifest["stages"][args.stage] = stage
    save_manifest(artifact_dir, manifest)
    print_json({"status": "OK", "stage": args.stage, "manifest": manifest_path(artifact_dir)})


def can_import(module_name):
    return importlib.util.find_spec(module_name) is not None


def cmd_preflight(args):
    artifact_dir = artifact_dir_path(args)
    repo_root = os.path.abspath(args.repo_root)
    checks = {
        "python_yaml": can_import("yaml"),
        "jinja2": can_import("jinja2"),
        "xelatex": shutil.which("xelatex") is not None,
        "pdftoppm": shutil.which("pdftoppm") is not None,
        "render_assignment_py": os.path.exists(
            os.path.join(repo_root, "math-assignment-latex", "scripts", "render_assignment.py")
        ),
        "compile_latex_sh": os.path.exists(
            os.path.join(repo_root, "math-assignment-latex", "scripts", "compile_latex.sh")
        ),
    }
    blocking = [name for name in ("python_yaml", "jinja2", "xelatex", "render_assignment_py", "compile_latex_sh") if not checks[name]]
    skipped = []
    status = "PASS"
    if blocking:
        status = "BLOCKED_ENVIRONMENT"
    elif not checks["pdftoppm"]:
        status = "WARN"
        skipped.append({"check": "pdf_visual_check", "reason": "pdftoppm missing"})
    payload = {
        "schema_version": 1,
        "status": status,
        "checks": checks,
        "blocking": blocking,
        "skipped": skipped,
        "timestamp": now_iso(),
    }
    write_json(os.path.join(artifact_dir, "preflight.json"), payload)
    manifest = load_manifest(artifact_dir)
    manifest["stages"]["S-1"] = {
        "name": "LaTeX preflight",
        "status": status,
        "timestamp": payload["timestamp"],
        "blocking": blocking,
        "skipped": skipped,
    }
    save_manifest(artifact_dir, manifest)
    print_json(payload)
    return 2 if status == "BLOCKED_ENVIRONMENT" else 0


def read_ledger(artifact_dir):
    path = ledger_path(artifact_dir)
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def append_ledger(artifact_dir, row):
    path = ledger_path(artifact_dir)
    ensure_dir(os.path.dirname(path))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_review_ledger(args):
    artifact_dir = artifact_dir_path(args)
    artifact = os.path.abspath(args.artifact)
    marker = os.path.abspath(args.marker or default_marker_for(artifact))
    digest = sha256_file(artifact)
    row = {
        "schema_version": 1,
        "stage": args.stage,
        "artifact": artifact,
        "hash": digest,
        "reviewer": args.reviewer,
        "verdict": args.verdict,
        "blocking_issues": args.blocking_issues,
        "marker": marker,
        "timestamp": now_iso(),
    }
    if args.summary:
        row["summary"] = args.summary
    append_ledger(artifact_dir, row)
    if args.create_marker and args.verdict in PASS_VERDICTS:
        ensure_dir(os.path.dirname(marker))
        with open(marker, "a", encoding="utf-8"):
            os.utime(marker, None)
    manifest = load_manifest(artifact_dir)
    manifest["stages"][args.stage] = {
        "name": "YAML review gate",
        "status": args.verdict,
        "artifact": artifact,
        "hash": digest,
        "marker": marker,
        "timestamp": row["timestamp"],
    }
    save_manifest(artifact_dir, manifest)
    print_json({"status": "OK", "ledger": ledger_path(artifact_dir), "row": row})


def cmd_check_render_gate(args):
    artifact_dir = artifact_dir_path(args)
    artifact = os.path.abspath(args.artifact)
    marker = os.path.abspath(args.marker or default_marker_for(artifact))
    digest = sha256_file(artifact)
    rows = [
        row for row in read_ledger(artifact_dir)
        if row.get("artifact") == artifact and row.get("hash") == digest and row.get("verdict") in PASS_VERDICTS
    ]
    marker_ok = os.path.exists(marker) and os.path.getmtime(marker) >= os.path.getmtime(artifact)
    payload = {
        "artifact": artifact,
        "hash": digest,
        "marker": marker,
        "review_pass": bool(rows),
        "marker_ok": marker_ok,
        "status": "PASS" if rows and marker_ok else "BLOCK",
        "timestamp": now_iso(),
    }
    if not rows:
        payload["reason"] = "No PASS/PASS_WITH_NOTES review-ledger row for current artifact hash."
    elif not marker_ok:
        payload["reason"] = "Review marker is missing or older than artifact."
    print_json(payload)
    return 0 if payload["status"] == "PASS" else 2


def cmd_invalidate_review(args):
    removed = []
    for artifact in args.artifacts:
        marker = args.marker or default_marker_for(os.path.abspath(artifact))
        if os.path.exists(marker):
            os.remove(marker)
            removed.append(marker)
    print_json({"status": "OK", "removed_markers": removed})


def cmd_final_review(args):
    artifact_dir = artifact_dir_path(args)
    review_dir = os.path.join(artifact_dir, "review")
    ensure_dir(review_dir)
    dimensions = json.loads(args.dimensions_json) if args.dimensions_json else {}
    payload = {
        "schema_version": 1,
        "stage": "S6",
        "reviewer": args.reviewer,
        "verdict": args.verdict,
        "dimensions": dimensions,
        "summary": args.summary,
        "next_action": args.next_action,
        "timestamp": now_iso(),
    }
    json_path = os.path.join(review_dir, "final-homework-review.json")
    md_path = os.path.join(review_dir, "final-homework-review.md")
    write_json(json_path, payload)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Final Homework Review\n\n")
        f.write(f"- Verdict: `{args.verdict}`\n")
        f.write(f"- Reviewer: `{args.reviewer}`\n")
        f.write(f"- Timestamp: `{payload['timestamp']}`\n")
        if args.summary:
            f.write(f"- Summary: {args.summary}\n")
        if args.next_action:
            f.write(f"- Next action: {args.next_action}\n")
        if dimensions:
            f.write("\n## Dimensions\n\n")
            for key, value in dimensions.items():
                f.write(f"- `{key}`: {value}\n")
    manifest = load_manifest(artifact_dir)
    manifest["stages"]["S6"] = {
        "name": "最终作业审核",
        "status": args.verdict,
        "json": json_path,
        "markdown": md_path,
        "timestamp": payload["timestamp"],
    }
    save_manifest(artifact_dir, manifest)
    print_json({"status": "OK", "json": json_path, "markdown": md_path})


def build_parser():
    parser = argparse.ArgumentParser(description="Structured gate helper for math-homework-pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-manifest")
    init.add_argument("--artifact-dir", required=True)
    init.add_argument("--run-mode", required=True, choices=sorted(RUN_MODES))
    init.add_argument("--goal", required=True)
    init.add_argument("--inputs-json")
    init.set_defaults(func=cmd_init_manifest)

    stage = sub.add_parser("stage")
    stage.add_argument("--artifact-dir", required=True)
    stage.add_argument("--stage", required=True)
    stage.add_argument("--name", required=True)
    stage.add_argument("--status", required=True)
    stage.add_argument("--artifact")
    stage.add_argument("--skip-reason")
    stage.add_argument("--verdict")
    stage.set_defaults(func=cmd_stage)

    preflight = sub.add_parser("preflight")
    preflight.add_argument("--artifact-dir", required=True)
    preflight.add_argument("--repo-root", default=os.getcwd())
    preflight.set_defaults(func=cmd_preflight)

    review = sub.add_parser("review-ledger")
    review.add_argument("--artifact-dir", required=True)
    review.add_argument("--stage", required=True)
    review.add_argument("--artifact", required=True)
    review.add_argument("--reviewer", default="math-yaml-review")
    review.add_argument("--verdict", required=True, choices=sorted(PASS_VERDICTS | {"BLOCK", "SKIP"}))
    review.add_argument("--blocking-issues", type=int, default=0)
    review.add_argument("--marker")
    review.add_argument("--summary")
    review.add_argument("--create-marker", action="store_true")
    review.set_defaults(func=cmd_review_ledger)

    gate = sub.add_parser("check-render-gate")
    gate.add_argument("--artifact-dir", required=True)
    gate.add_argument("--artifact", required=True)
    gate.add_argument("--marker")
    gate.set_defaults(func=cmd_check_render_gate)

    invalidate = sub.add_parser("invalidate-review")
    invalidate.add_argument("artifacts", nargs="+")
    invalidate.add_argument("--marker")
    invalidate.set_defaults(func=cmd_invalidate_review)

    final = sub.add_parser("final-review")
    final.add_argument("--artifact-dir", required=True)
    final.add_argument("--reviewer", default="math-homework-review")
    final.add_argument("--verdict", required=True, choices=["PASS", "PASS_WITH_NOTES", "BLOCK", "SKIP"])
    final.add_argument("--dimensions-json")
    final.add_argument("--summary", default="")
    final.add_argument("--next-action", default="")
    final.set_defaults(func=cmd_final_review)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    result = args.func(args)
    if isinstance(result, int):
        return result
    return 0


if __name__ == "__main__":
    sys.exit(main())
