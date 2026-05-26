# Ratings Format

## CSV header

```csv
problem_id,recipe_name,seed,rating,comment,rated_at
```

## Example rows

```csv
p0001,baseline_layout,1,3,"acceptable",2026-02-23T10:20:31Z
p0001,r_over_R_ge_0p10,1,5,"clean geometry",2026-02-23T10:20:42Z
```

## Key uniqueness
Unique key = (`problem_id`,`recipe_name`,`seed`).

## Resume behavior
- Keep checkpoint file with current index.
- Rewrite same key row when reviewer updates score.
