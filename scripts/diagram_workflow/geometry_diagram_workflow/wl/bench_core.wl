(* ::Package:: *)
(* Wolfram Benchmark Core - Solve and Measure *)

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
    "fail_type" -> String ("timeout" | "invalid_head" | ""),
    "solve_time_s" -> Real,
    "parameters" -> Association (point coordinates),
    "algebraic_complexity" -> Integer,
    "image_path" -> String? (optional, present if render succeeded)
  ]
*)

(* Main solving function with timeout and timing *)
SolveAndMeasure[
  scene_,                    (* GeometricScene to solve *)
  seed_Integer,              (* random seed for reproducibility *)
  timeout_Integer,           (* timeout in seconds *)
  renderImages_?BooleanQ,    (* whether to export image *)
  imagePathAbs_String        (* absolute path for PNG, "" if no render *)
] := Module[
  {start, inst, solveTime, result},
  start = AbsoluteTime[];
  inst = TimeConstrained[
    BlockRandom[
      SeedRandom[seed];
      RandomInstance[scene]
    ],
    timeout,
    $Failed
  ];
  solveTime = AbsoluteTime[] - start;

  (* Build result based on success/failure *)
  result = Which[
    inst === $Failed,
    <|
      "success" -> False,
      "fail_type" -> "timeout",
      "solve_time_s" -> N[timeout],
      "message" -> "Solve timeout"
    |>,
    Head[inst] =!= GeometricScene,
    <|
      "success" -> False,
      "fail_type" -> "invalid_head",
      "solve_time_s" -> N[solveTime],
      "message" -> ToString[Head[inst]]
    |>,
    True,
    Module[{successResult, exportResult, imageExists},
      successResult = <|
        "success" -> True,
        "fail_type" -> "",
        "solve_time_s" -> N[solveTime],
        "parameters" -> Normal[inst["Parameters"]],
        "algebraic_complexity" -> StringLength[ToString[inst["AlgebraicFormulation"]]]
      |>;

      (* Optional rendering: export to imagePathAbs (dir already created by Python) *)
      If[renderImages && StringLength[imagePathAbs] > 0,
        exportResult = Quiet[Check[
          Export[imagePathAbs, inst["Graphics"], ImageSize -> 512],
          $Failed
        ]];
        imageExists = FileExistsQ[imagePathAbs];
        If[exportResult === $Failed || !TrueQ[imageExists],
          <|
            "success" -> False,
            "fail_type" -> "render_export_failed",
            "solve_time_s" -> N[solveTime],
            "parameters" -> Normal[inst["Parameters"]],
            "algebraic_complexity" -> StringLength[ToString[inst["AlgebraicFormulation"]]],
            "message" -> "Wolfram Export did not produce a PNG",
            "export_result_head" -> ToString[Head[exportResult]],
            "image_path" -> imagePathAbs
          |>,
          AppendTo[successResult, "image_path" -> imagePathAbs]
        ],
        successResult
      ]
    ]
  ];

  result
];

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

  Returns: Association[
    "problem_id" -> String,
    "recipe_name" -> String,
    "seed" -> Integer,
    "success" -> Bool,
    "fail_type" -> String,
    "solve_time_s" -> Real,
    ... (from SolveAndMeasure)
  ]
*)

(* Solve single case with all constraint layers *)
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
] := Module[
  {buildStart, solveStart, scene, result, buildTime, solveTime},
  buildStart = AbsoluteTime[];
  scene = AssembleScene[points, baseHypotheses, layers];
  buildTime = AbsoluteTime[] - buildStart;
  solveStart = AbsoluteTime[];
  result = SolveAndMeasure[scene, seed, timeout, renderImages, imagePathAbs];
  solveTime = AbsoluteTime[] - solveStart;
  Join[
    <|
      "problem_id" -> problemId,
      "recipe_name" -> recipeName,
      "seed" -> seed,
      "scene_build_time_s" -> N[buildTime],
      "solver_wall_time_s" -> N[solveTime]
    |>,
    result
  ]
];

(* Functions are automatically available after Get[], no need to export *)
