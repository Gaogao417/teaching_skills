---
name: dimensionless-constraints-library
description: Use this skill when adding or tuning dimensionless geometric constraints (for example angle lower bounds, r/R, height/perimeter) for benchmark sweep recipes in GeometricScene.
---

# Dimensionless Constraints Library

Provide reusable constraint templates for sweep recipes.

## Workflow
1. Start with baseline layout-only recipe.
2. Add one dimensionless family at a time.
3. Sweep strength values from weak to strong.
4. Record expected complexity risk per recipe.

## Supported families
- angle lower bound (`PlanarAngle[triple] > minDeg Degree`)
- side ratio (`Min[sides] > minRatio * Max[sides]`)
- height/base ratio (`height > minRatio * baseLen`)
- height/perimeter ratio (`height > minRatio * perimeter`)
- layout assertions (`Horizontal`, `Rightward`, `Counterclockwise`, `Distinct`)

## Risk heuristics
- **low**: orientation only (BuildOrientation)
- **medium**: one angle OR side ratio constraint
- **high**: height-based ratios (BuildHeightBase, BuildHeightPerimeter)

## Recipe design rules
- Keep one baseline without shape constraints.
- Avoid stacking multiple strong bounds in first pass.
- Increase strictness gradually (e.g., 0.05 -> 0.10 -> 0.15).

See `references/constraint-recipes.md`.

## Done criteria
- Each recipe has a clear name and one dominant variable.
- Recipe metadata includes expected speed risk: low/medium/high.
