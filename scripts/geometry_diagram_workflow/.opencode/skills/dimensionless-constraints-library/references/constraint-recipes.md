# Constraint Recipes

## Example sweep fragment

```yaml
constraint_recipes:
  - name: baseline_layout
    risk: low
    layout:
      triangle_base_horizontal: true
    shape: []

  - name: angle_min_10
    risk: medium
    layout:
      triangle_base_horizontal: true
    shape:
      - type: interior_angle_min
        vertex: B
        min_deg: 10

  - name: r_over_R_ge_0p10
    risk: high
    layout:
      triangle_base_horizontal: true
    shape:
      - type: inradius_over_circumradius_min
        min_ratio: 0.10
```

## Mapping hints
- `interior_angle_min` -> `TriangleMeasurement[..., {"InteriorAngle", v}] > k Degree`
- `inradius_over_circumradius_min` -> `TriangleMeasurement[..., "Inradius"] / TriangleMeasurement[..., "Circumradius"] > eps`
- `height_over_perimeter_min` -> `TriangleMeasurement[..., {"Height", v}] / TriangleMeasurement[..., "Perimeter"] > eps`

## Risk heuristics
- low: orientation only
- medium: one linear angle lower bound
- high: ratio bounds with radicals or multi-bounds
