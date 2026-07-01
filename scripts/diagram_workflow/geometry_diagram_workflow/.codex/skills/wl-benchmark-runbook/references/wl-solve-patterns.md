# WL Solve Patterns

## Pattern: solve-first, render-later

```wl
start = AbsoluteTime[];
inst = TimeConstrained[
  BlockRandom[SeedRandom[seed]; RandomInstance[scene]],
  timeout,
  $Failed
];
solveTime = AbsoluteTime[] - start;
```

## Pattern: typed result status

```wl
result = Which[
  inst === $Failed,
    <|"success" -> False, "fail_type" -> "timeout"|>,
  Head[inst] =!= GeometricScene,
    <|"success" -> False, "fail_type" -> "invalid_head"|>,
  True,
    <|
      "success" -> True,
      "fail_type" -> "",
      "parameters" -> inst["Parameters"],
      "algebraic" -> inst["AlgebraicFormulation"]
    |>
];
```

## Pattern: optional rendering

```wl
If[result["success"] && renderImages,
  Export[imagePath, inst["Graphics"], ImageSize -> 512]
]
```

## Pattern: never resample when debugging

```wl
(* BAD: RandomInstance called twice *)
(* GOOD: reuse `inst` object for all properties and render *)
```
