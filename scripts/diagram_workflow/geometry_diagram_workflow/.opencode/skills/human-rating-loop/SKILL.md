---
name: human-rating-loop
description: Use this skill when building or running the manual image scoring loop (1-5 ratings) for benchmark outputs, including resume support and ratings.csv export.
---

# Human Rating Loop

Run fast and resumable manual scoring.

## Workflow
1. Load successful cases with images.
2. Display one image at a time with metadata.
3. Capture score `1..5` and optional comment.
4. Autosave and allow resume.
5. Export `ratings.csv`.

## UI minimum
- image preview
- metadata panel (`problem_id`, `recipe_name`, `seed`, `solve_time_s`)
- score input 1..5
- next/back controls
- progress counter

## CSV schema
- `problem_id`
- `recipe_name`
- `seed`
- `rating`
- `comment`
- `rated_at`

See examples in `references/ratings-format.md`.

## Done criteria
- No duplicate key rows.
- Interrupted session can continue from checkpoint.
