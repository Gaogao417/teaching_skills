---
name: wl-benchmark-runbook
description: Use this skill when writing or reviewing Wolfram scripts for GeometricScene benchmarks: layered constraints, RandomInstance with timeout/seed control, solve-time measurement, and optional post-render export.
---

# WL Benchmark Runbook

Use this runbook to avoid invalid GeometricScene code and unfair timing.

## Core workflow
1. Build `GeometricScene` using constraint builders:
   - Layout constraints: `BuildOrientation[points, baseEdge]`
   - Angle constraints: `BuildAngleMin[points, minDeg]`
   - Side ratio constraints: `BuildSideRatio[points, minRatio]`
   - Height ratio constraints: `BuildHeightBase[points, baseEdge, minRatio]`, `BuildHeightPerimeter[points, minRatio]`
2. Assemble all constraints: `AssembleScene[points, baseHypotheses, Flatten[constraints]]`
3. Solve with deterministic seed and timeout.
4. Record structured result fields.
5. Render only after solve succeeds.

## Mandatory pattern
- `TimeConstrained[expr, timeout, $Failed]`
- deterministic random seed per case
- `Head[result] === GeometricScene` check
- fixed `ImageSize` for all rendered outputs

## Required outputs per case
- `problem_id`
- `recipe_name`
- `seed`
- `success`
- `solve_time_s`
- `fail_type`

## Failure taxonomy
- `timeout`: TimeConstrained exceeded timeout
- `invalid_head`: RandomInstance returned non-GeometricScene
- `runtime_error`: Python/wolframclient exception
- `host_watchdog_timeout`: Worker process killed by host
- `worker_error`: Worker startup failed

## References
- GeometricScene syntax and snippets: `references/geometricscene-cheatsheet.md`
- Recommended solve/record patterns: `references/wl-solve-patterns.md`

## Guardrails
- Do not duplicate given constraints with stricter conflicting bounds.
- Do not include rendering time in solve time.
- Keep seeds identical across recipes for comparability.
