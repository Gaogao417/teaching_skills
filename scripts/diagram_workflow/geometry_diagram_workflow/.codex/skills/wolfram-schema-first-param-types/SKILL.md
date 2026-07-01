---
name: wolfram-schema-first-param-types
description: When writing Wolfram Language (.wl) code, declare schema first: use block comments with Usage, Schema (parameter types), and Returns sections. Annotate parameters with Head patterns (_Integer, _String, _List, _?BooleanQ). Use product notation (key*Type) for Association return types. Apply when authoring or reviewing Wolfram modules.
---

# Wolfram Schema-First Parameter Types

## Rule

**Schema first.** Before implementation, write a block comment that documents:
1. **Usage** - brief usage example
2. **Schema** - parameter names with types and semantic descriptions
3. **Returns** - return type structure (especially for Association)

## Annotation Format

### Block Comment Structure

```wl
(*
  Usage:
    Get["module.wl"];
    result = func[arg1, arg2, ...];

  Schema for func:
    param1: Type (semantic description)
    param2: Type (semantic description)
  
  Returns: TypeDescription
*)
func[param1_Type, param2_Type] := Module[...]
```

### Parameter Types

#### Atomic Types (use standard Head patterns)

| WL Type | Pattern | Example |
|---------|---------|---------|
| Integer | `_Integer` | `seed_Integer` |
| Real | `_Real` | `minRatio_` |
| String | `_String` | `imagePath_String` |
| Symbol | `_Symbol` | `var_Symbol` |
| Boolean | `_?BooleanQ` | `render_?BooleanQ` |

#### Composite Types

**List:**
- `List[Symbol]` - list of symbols
- `List[_[_]]` - list of expressions (generic)
- `List[a_, b_]` - exactly 2 elements (destructuring)

```wl
BuildLayer1[
  points_List,               (* all points *)
  baseEdge_List              (* exactly 2 points: {base1, base2} *)
] := Module[
  {base1, base2, top},
  {base1, base2} = baseEdge;  (* destructuring *)
  ...
]
```

**Association (product type notation):**

Use `key*Type` notation to document Association structure:

```wl
(*
  Returns: Association[
    "success" -> Bool,
    "fail_type" -> String ("timeout" | "invalid_head" | ""),
    "solve_time_s" -> Real,
    "parameters" -> Association,
    "image_path" -> String?  (* optional *)
  ]
*)
```

Or inline: `success*Bool * fail_type*String * solve_time_s*Real`

## Complete Example

```wl
(* ::Package:: *)
(* Module header comment *)

(*
  Usage:
    Get["bench_core.wl"];
    result = SolveSingleCase["p001", "baseline", {a,b,c}, {AB==5}, {}, 1, 60, True, "C:/out/img.png"];

  Schema for SolveAndMeasure:
    scene: GeometricScene
    seed: Integer (random seed for BlockRandom/SeedRandom)
    timeout: Integer (seconds for TimeConstrained)
    renderImages: Boolean (whether to export image)
    imagePathAbs: String (absolute path for PNG output, "" if no render)
  
  Returns: Association[
    "success" -> Bool,
    "fail_type" -> String,
    "solve_time_s" -> Real,
    "parameters" -> Association (point coordinates),
    "algebraic_complexity" -> Integer,
    "image_path" -> String? (optional)
  ]
*)

SolveAndMeasure[
  scene_,                    (* GeometricScene to solve *)
  seed_Integer,              (* random seed for reproducibility *)
  timeout_Integer,           (* timeout in seconds *)
  renderImages_?BooleanQ,    (* whether to export image *)
  imagePathAbs_String        (* absolute path for PNG, "" if no render *)
] := Module[
  {start, inst, solveTime, result},
  ...
];
```

## Checklist Before Writing a Function

1. [ ] Add block comment with Usage, Schema, Returns
2. [ ] Annotate each parameter with `_Type` pattern
3. [ ] Add inline comment for each parameter (semantic description)
4. [ ] For `_List`, specify element type or structure (e.g., "exactly 2 points")
5. [ ] For Association returns, document key-value types using `key*Type` notation
6. [ ] Use `?testQ` for Boolean parameters (`_?BooleanQ`, `_?NumericQ`)

## Anti-Patterns

### Wrong

```wl
(* No schema, vague types *)
SolveSingleCase[problemId, recipeName, points, baseHypotheses, layers, seed, timeout, render] := ...

(* List without structure documentation *)
AssembleScene[points_List, baseHypotheses_List, layers_List] := ...
(* What is in points? Symbol list? What is in layers? *)
```

### Right

```wl
(*
  Schema for SolveSingleCase:
    problemId: String (e.g., "p001")
    recipeName: String (e.g., "baseline_layout")
    points: List[Symbol] (e.g., {a, b, c})
    baseHypotheses: List[_[_]] (e.g., {AB == 5, BC == 6})
    layers: List[_[_]] (output from BuildLayerN functions)
    seed: Integer
    timeout: Integer
    renderImages: Boolean
    imagePathAbs: String
*)
SolveSingleCase[
  problemId_String,            (* unique problem identifier *)
  recipeName_String,           (* constraint recipe name *)
  points_List,                 (* list of Symbol points *)
  baseHypotheses_List,         (* base geometric constraints *)
  layers_List,                 (* layered constraints from BuildLayerN *)
  seed_Integer,                (* random seed *)
  timeout_Integer,             (* timeout in seconds *)
  renderImages_?BooleanQ,      (* whether to render *)
  imagePathAbs_String          (* absolute path for PNG *)
] := Module[...]
```

## Reference

- `_Head` matches any expression with that Head
- `_?testQ` applies a predicate test (e.g., `_?BooleanQ` matches only `True` or `False`)
- Destructuring: `{a, b} = list` extracts first two elements
- Product notation: `a*Type1 * b*Type2` means "a of Type1 AND b of Type2" (F# tuple style)
