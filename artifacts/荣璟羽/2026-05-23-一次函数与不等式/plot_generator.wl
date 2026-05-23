(* Wolfram script to generate three precise, vector PDF diagrams for practice problems *)

SetDirectory[DirectoryName[$InputFileName]];

color1 = RGBColor[0.15, 0.35, 0.70]; (* Known line: Slate Blue *)
color2 = RGBColor[0.85, 0.15, 0.25]; (* Unknown/to-be-found line: Crimson *)

(* ------------------- Diagram 1: P1 ------------------- *)
(* y1 = -x + 3, y2 = 3x - 1, Intersection P(1, 2), y2 passes through (0, -1) *)
p1 = Plot[{-x + 3, 3*x - 1}, {x, -2.5, 4.5},
  PlotStyle -> {
    {Directive[Thick, color1]}, 
    {Directive[Thick, color2]}
  },
  Axes -> True,
  AxesStyle -> Directive[Black, Thin, Arrowheads[0.035]],
  AxesLabel -> {Style["x", 12, Italic], Style["y", 12, Italic]},
  Ticks -> {Range[-2, 4], Range[-3, 6]},
  GridLines -> {Range[-3, 5], Range[-4, 7]},
  GridLinesStyle -> Directive[GrayLevel[0.85], Dashed],
  PlotRange -> {{-2.2, 4.2}, {-3.2, 6.2}},
  AspectRatio -> 1,
  PlotRangePadding -> Scaled[0.05],
  Epilog -> {
    (* Point P *)
    PointSize[0.025], Point[{1, 2}],
    Text[Style["P(1,2)", 11, Bold, FontFamily -> "Arial", Background -> White], {1.5, 2.3}],
    (* Point A(0, -1) *)
    PointSize[0.02], Point[{0, -1}],
    Text[Style["A(0,-1)", 10, FontFamily -> "Arial", Background -> White], {0.5, -0.7}],
    (* Line Labels *)
    Text[Style["l1: y = -x + 3", 10, color1, FontFamily -> "Arial", Background -> White], {2.8, 1.2}],
    Text[Style["l2: y = kx + b", 10, color2, FontFamily -> "Arial", Background -> White], {1.7, 5.0}],
    (* Origin *)
    Text[Style["O", 11, Italic, FontFamily -> "Arial"], {-0.2, -0.2}]
  }
];

Export["plot_p1.pdf", p1];
Print["Generated plot_p1.pdf"];

(* ------------------- Diagram 2: P2 ------------------- *)
(* y1 = x - 1, y2 = -2x + 5, Intersection P(2, 1), y2 passes through (0, 5) *)
p2 = Plot[{x - 1, -2*x + 5}, {x, -2.5, 4.5},
  PlotStyle -> {
    {Directive[Thick, color1]}, 
    {Directive[Thick, color2]}
  },
  Axes -> True,
  AxesStyle -> Directive[Black, Thin, Arrowheads[0.035]],
  AxesLabel -> {Style["x", 12, Italic], Style["y", 12, Italic]},
  Ticks -> {Range[-2, 4], Range[-3, 6]},
  GridLines -> {Range[-3, 5], Range[-4, 7]},
  GridLinesStyle -> Directive[GrayLevel[0.85], Dashed],
  PlotRange -> {{-2.2, 4.2}, {-3.2, 6.2}},
  AspectRatio -> 1,
  PlotRangePadding -> Scaled[0.05],
  Epilog -> {
    (* Point P *)
    PointSize[0.025], Point[{2, 1}],
    Text[Style["P(2,1)", 11, Bold, FontFamily -> "Arial", Background -> White], {2.5, 1.4}],
    (* Point B(0, 5) *)
    PointSize[0.02], Point[{0, 5}],
    Text[Style["B(0,5)", 10, FontFamily -> "Arial", Background -> White], {0.5, 5.0}],
    (* Line Labels *)
    Text[Style["l1: y = x - 1", 10, color1, FontFamily -> "Arial", Background -> White], {3.2, 1.6}],
    Text[Style["l2: y = kx + b", 10, color2, FontFamily -> "Arial", Background -> White], {1.4, 3.2}],
    (* Origin *)
    Text[Style["O", 11, Italic, FontFamily -> "Arial"], {-0.2, -0.2}]
  }
];

Export["plot_p2.pdf", p2];
Print["Generated plot_p2.pdf"];

(* ------------------- Diagram 3: P3 ------------------- *)
(* y1 = 2x + 4, y2 = x + 3, Intersection P(-1, 2), y2 passes through (0, 3) *)
p3 = Plot[{2*x + 4, x + 3}, {x, -4.5, 3.5},
  PlotStyle -> {
    {Directive[Thick, color1]}, 
    {Directive[Thick, color2]}
  },
  Axes -> True,
  AxesStyle -> Directive[Black, Thin, Arrowheads[0.035]],
  AxesLabel -> {Style["x", 12, Italic], Style["y", 12, Italic]},
  Ticks -> {Range[-4, 3], Range[-2, 6]},
  GridLines -> {Range[-5, 4], Range[-3, 7]},
  GridLinesStyle -> Directive[GrayLevel[0.85], Dashed],
  PlotRange -> {{-4.2, 3.2}, {-1.2, 6.2}},
  AspectRatio -> 1,
  PlotRangePadding -> Scaled[0.05],
  Epilog -> {
    (* Point P *)
    PointSize[0.025], Point[{-1, 2}],
    Text[Style["P(-1,2)", 11, Bold, FontFamily -> "Arial", Background -> White], {-1.5, 2.3}],
    (* Point C(0, 3) *)
    PointSize[0.02], Point[{0, 3}],
    Text[Style["C(0,3)", 10, FontFamily -> "Arial", Background -> White], {0.5, 3.2}],
    (* Line Labels *)
    Text[Style["l1: y = 2x + 4", 10, color1, FontFamily -> "Arial", Background -> White], {-2.5, -0.2}],
    Text[Style["l2: y = kx + b", 10, color2, FontFamily -> "Arial", Background -> White], {1.2, 4.8}],
    (* Origin *)
    Text[Style["O", 11, Italic, FontFamily -> "Arial"], {-0.2, -0.2}]
  }
];

Export["plot_p3.pdf", p3];
Print["Generated plot_p3.pdf"];
