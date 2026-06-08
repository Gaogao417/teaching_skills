# GeometricScene Cheatsheet

## Core scene template

```wl
scene = GeometricScene[
  {A, B, C},
  {
    GeometricAssertion[Line[{B, C}], "Horizontal"],
    GeometricAssertion[{B, C, A}, "Counterclockwise"],
    GeometricAssertion[{A, B, C}, "Distinct"],
    TriangleMeasurement[{A, B, C}, {"InteriorAngle", B}] > 10 Degree,
    TriangleMeasurement[Triangle[{A, B, C}], "Inradius"] /
      TriangleMeasurement[Triangle[{A, B, C}], "Circumradius"] > 0.10
  }
];
```

## Solve with timeout and seed

```wl
TimeConstrained[
  BlockRandom[
    SeedRandom[1];
    inst = RandomInstance[scene]
  ],
  60,
  $Failed
]
```

## Validate solve result

```wl
If[inst === $Failed,
  <|"status" -> "timeout"|>,
  If[Head[inst] === GeometricScene,
    <|
      "status" -> "ok",
      "params" -> inst["Parameters"],
      "alg" -> inst["AlgebraicFormulation"]
    |>,
    <|"status" -> "invalid_head", "head" -> ToString[Head[inst]]|>
  ]
]
```

## Render after solve

```wl
Export[
  "outputs/run_20260223_120000/images/p0001_rR_010_s1.png",
  inst["Graphics"],
  ImageSize -> 512
]
```

## Common mistakes
- Using point symbol not declared in scene point list.
- Over-constraining with both fixed side lengths and aggressive ratio bounds.
- Measuring solve time together with rendering time.
- Forgetting deterministic seeds in sweep experiments.
- Treating all failures as one category.
