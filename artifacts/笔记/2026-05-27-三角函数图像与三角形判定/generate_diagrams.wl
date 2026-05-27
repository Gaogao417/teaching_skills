base = DirectoryName[$InputFileName];

EnsureDir[path_] := If[! DirectoryQ[path], CreateDirectory[path, CreateIntermediateDirectories -> True]];

JobPath[job_] := FileNameJoin[{base, "diagram", "jobs", job}];
OutPath[job_] := FileNameJoin[{JobPath[job], "rendered", "prompt.png"}];

ExportGraph[job_, expr_, xmax_, y0_, ymax_, opts___] := Module[
  {dir = FileNameJoin[{JobPath[job], "rendered"}], plot},
  EnsureDir[dir];
  plot = Show[
    Plot[expr, {x, -Pi/2, Pi/2},
      PlotRange -> {{-Pi/2, Pi/2}, {-1.2 ymax, 1.25 ymax}},
      Axes -> True,
      AxesLabel -> {Style["x", 14], Style["y", 14]},
      PlotStyle -> {Blue, Thick},
      ImageSize -> 430,
      Ticks -> {None, None},
      GridLines -> None],
    Graphics[{
      Gray, Dashed, Line[{{xmax, 0}, {xmax, ymax}}],
      Gray, Dashed, Line[{{0, ymax}, {xmax, ymax}}],
      Red, PointSize[0.018], Point[{xmax, ymax}], Point[{0, y0}],
      Black, Text[Style[ToString[TraditionalForm[ymax]], 13], {-0.12, ymax}],
      Black, Text[Style[ToString[TraditionalForm[y0]], 13], {-0.12, y0}],
      Black, Text[Style[ToString[TraditionalForm[xmax]], 13], {xmax, -0.18 ymax}],
      opts
    }]
  ];
  Export[OutPath[job], plot]
];

ExportTriangle[job_, annotated_: False] := Module[
  {dir = FileNameJoin[{JobPath[job], "rendered"}], extra},
  EnsureDir[dir];
  extra = If[annotated,
    {Blue, Text[Style["B=\[Pi]/3", 13], {1.55, 2.35}],
     Blue, Text[Style["a+c=2b", 13], {1.5, -0.45}]},
    {}
  ];
  Export[OutPath[job],
    Graphics[{
      Thick, Line[{{0, 0}, {3, 0}, {0.9, 2}, {0, 0}}],
      Black,
      Text[Style["A", 14], {0.9, 2.18}],
      Text[Style["B", 14], {-0.14, -0.13}],
      Text[Style["C", 14], {3.14, -0.13}],
      Text[Style["a", 13], {1.5, -0.22}],
      Text[Style["b", 13], {2.02, 1.12}],
      Text[Style["c", 13], {0.36, 1.08}],
      Red, Circle[{0, 0}, 0.42, {0, 1.14}],
      Red, Text[Style["B", 12], {0.33, 0.18}],
      extra
    },
    PlotRange -> {{-0.35, 3.35}, {-0.65, 2.55}},
    ImageSize -> 340]
  ]
];

ExportGraph["orig-prompt", 2 Sin[2 x + Pi/6], Pi/6, 1, 2];
ExportGraph["orig-solution", 2 Sin[2 x + Pi/6], Pi/6, 1, 2,
  Arrow[{{-1.05, 1.35}, {-0.05, 1}}],
  Text[Style["f(0)=A sin \[CurlyPhi]", 12, Gray], {-1.13, 1.45}],
  Arrow[{{1.15, 1.62}, {Pi/6, 2}}],
  Text[Style["maximum", 12, Gray], {1.25, 1.72}]
];
ExportTriangle["tri-solution", True];

ExportGraph["c1-prompt", 3 Sin[2 x + Pi/4], Pi/8, 3/Sqrt[2], 3];
ExportGraph["f1-prompt", 4 Sin[4 x + Pi/6], Pi/12, 2, 4];
ExportGraph["p1-part1-prompt", 3 Sin[2 x + Pi/6], Pi/6, 3/2, 3];

ExportTriangle["c2-prompt"];
ExportTriangle["f2-prompt"];
ExportTriangle["p1-part2-prompt"];
ExportTriangle["p1-tri-prompt"];
