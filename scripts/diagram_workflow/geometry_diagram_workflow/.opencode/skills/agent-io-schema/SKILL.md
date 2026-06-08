---
name: agent-io-schema
description: Use this skill when defining or validating data schemas for agent inputs/outputs, including problems.jsonl, sweep.yaml, results.jsonl, and ratings.csv.
---

# Agent IO Schema

This skill defines the **canonical data schemas** for all agent interactions.

## Schema 1: problems.jsonl

**Producer**: problem-collector (or human)  
**Consumer**: bench-runner

### Required fields
- `id`: string (unique, e.g., "p0001")
- `points`: string[] (e.g., ["A", "B", "C"])
- `base_hypotheses_wl`: string[] (Wolfram expressions)

### Optional fields
- `text`: string (display only)
- `dsl`: object (internal use)
- `base_edge`: [string, string] (e.g., ["B", "C"])
- `known_angles`: array (for angle constraint exclusion)
- `constructed_points`: object (e.g., {"D": "Midpoint[{B,C}]"})
- `meta.source`: string
- `meta.difficulty`: "easy" | "medium" | "hard"

### Example
```json
{
  "id": "p0001",
  "text": "在△ABC 中，AB=AC=5，BC=6",
  "points": ["A", "B", "C"],
  "base_edge": ["B", "C"],
  "base_hypotheses_wl": [
    "EuclideanDistance[A, B] == EuclideanDistance[A, C]",
    "EuclideanDistance[B, C] == 6"
  ],
  "meta": {"source": "manual", "difficulty": "easy"}
}
```

---

## Schema 2: sweep.yaml (constraint_recipes fragment)

**Producer**: problem-constraint-designer (or human)  
**Consumer**: bench-runner

### Recipe structure
```yaml
constraint_recipes:
  - name: string (unique per sweep)
    risk: "low" | "medium" | "high"
    layout:
      triangle_base_horizontal: boolean
    shape:
      - type: "angle_min" | "side_ratio" | "height_base" | "height_perimeter"
        min_deg: float (for angle_min)
        min_ratio: float (for ratio types)
```

### Risk levels
- **low**: orientation only (no shape constraints)
- **medium**: one angle OR side ratio constraint
- **high**: height-based ratios (may timeout)

### Example
```yaml
constraint_recipes:
  - name: baseline_only
    risk: low
    layout: null
    shape: []
    
  - name: angle_min_10
    risk: medium
    layout:
      triangle_base_horizontal: true
    shape:
      - type: angle_min
        min_deg: 10
        
  - name: height_base_ge_0p1
    risk: high
    layout:
      triangle_base_horizontal: true
    shape:
      - type: height_base
        min_ratio: 0.1
```

---

## Schema 3: results.jsonl

**Producer**: bench-runner  
**Consumer**: analyst-reporter, scorer-ui

### Required fields (every case)
- `problem_id`: string
- `recipe_name`: string
- `seed`: integer
- `success`: boolean
- `solve_time_s`: float
- `fail_type`: string ("timeout" | "no_solution" | "invalid_head" | "runtime_error" | "host_watchdog_timeout" | "worker_error" | "")

### Optional fields (on success)
- `scene_build_time_s`: float
- `solver_wall_time_s`: float
- `parameters`: array (point coordinates)
- `algebraic_complexity`: integer
- `image_path`: string (relative to run_dir)
- `geometric_scene_code`: string (for debugging)

### Example (success)
```json
{
  "problem_id": "p0001",
  "recipe_name": "angle_min_10",
  "seed": 1,
  "success": true,
  "solve_time_s": 1.23,
  "scene_build_time_s": 0.003,
  "solver_wall_time_s": 12.5,
  "algebraic_complexity": 3809,
  "image_path": "images/p0001_angle_min_10_1.png"
}
```

### Example (failure)
```json
{
  "problem_id": "p0001",
  "recipe_name": "height_base_ge_0p1",
  "seed": 1,
  "success": false,
  "fail_type": "host_watchdog_timeout",
  "solve_time_s": 60.0,
  "message": "Host watchdog timeout after 80s"
}
```

---

## Schema 4: ratings.csv

**Producer**: scorer-ui (human input)  
**Consumer**: analyst-reporter

### CSV schema
```csv
problem_id,recipe_name,seed,rating,comment,rated_at
```

### Field constraints
- **Unique key**: (`problem_id`, `recipe_name`, `seed`)
- **rating**: integer 1-5
- **comment**: string (optional)
- **rated_at**: ISO 8601 timestamp

### Example
```csv
problem_id,recipe_name,seed,rating,comment,rated_at
p0001,angle_min_10,1,4,"好图",2026-02-24T10:00:00Z
p0001,side_ratio_0p3,1,5,"clean",2026-02-24T10:05:00Z
```

---

## Validation Rules

### Cross-schema consistency
1. Every `problem_id` in results.jsonl must exist in problems.jsonl
2. Every `recipe_name` in results.jsonl must exist in sweep.yaml
3. Every rated case in ratings.csv must have `success=true` in results.jsonl

### Data integrity
1. No duplicate keys in ratings.csv
2. All timestamps in ISO 8601 format
3. All paths in results.jsonl are relative to run_dir
