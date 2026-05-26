root = Environment["FIG_ROOT"];
If[! StringQ[root] || root === "", root = DirectoryName[$InputFileName]];
out = FileNameJoin[{root, "figures"}];
If[! DirectoryQ[out], CreateDirectory[out]];

h = 3 Sqrt[3];
r = Sqrt[3];
A = {-3, 0}; Cc = {3, 0}; B = {0, h}; G = {0, 0};

blue = RGBColor[0.08, 0.32, 0.72];
orange = RGBColor[0.9, 0.38, 0.08];
green = RGBColor[0.08, 0.50, 0.30];
purple = RGBColor[0.45, 0.18, 0.75];
gray = GrayLevel[0.55];

pt[p_, lab_, off_: {0.16, 0.16}] := {
  Black, PointSize[0.014], Point[p],
  Text[Style[lab, 14, Bold, FontFamily -> "Helvetica"], p + off]
};

thinPt[p_, lab_, off_: {0.14, 0.14}] := {
  GrayLevel[0.20], PointSize[0.011], Point[p],
  Text[Style[lab, 12, FontFamily -> "Helvetica"], p + off]
};

foot[D_, lab_] := Module[{H = {D[[1]], 0}},
  {Directive[GrayLevel[0.6], Dashed], Line[{D, H}], thinPt[H, lab, {0.10, -0.25}]}
];

base[range_] := {
  {GrayLevel[0.18], Thick, Line[{A, B, Cc, A}]},
  {Directive[GrayLevel[0.7], Dashed], Line[{{range[[1, 1]], 0}, {range[[1, 2]], 0}}]},
  {Directive[GrayLevel[0.62], Dashed], Line[{B, G}]},
  pt[A, "A", {-0.30, 0.20}], pt[B, "B", {0.16, 0.18}],
  pt[Cc, "C", {0.18, 0.18}], pt[G, "G", {0.12, -0.28}]
};

exportFig[name_, title_, extra_, range_: {{-4.5, 4.5}, {-2.6, 5.8}}] := Export[
  FileNameJoin[{out, name <> ".pdf"}],
  Graphics[
    {
      base[range],
      extra,
      Inset[
        Style[title, 14, Bold, FontFamily -> "Helvetica", Black],
        Scaled[{0.03, 0.95}], {-1, 1}
      ]
    },
    PlotRange -> range,
    ImageSize -> 540,
    Background -> White
  ]
];

(* Problem 1: AD perpendicular DC, segment BD and segment AC. Two symmetric
   positions give the same BD; both are shown. *)
x1 = Sqrt[27/8];
E1 = {x1, 0}; D1 = {4 x1/3, -r};
E1b = {-x1, 0}; D1b = {-4 x1/3, -r};
exportFig[
  "problem1",
  "Problem 1: AD perp DC",
  {
    {Directive[GrayLevel[0.55], Dashed], Circle[G, 3]},
    {Directive[blue, Thick], Line[{B, E1, D1}]},
    {Directive[blue, Dashed], Line[{A, D1, Cc}]},
    foot[D1, "H"],
    pt[E1, "E1", {0.10, 0.22}], pt[D1, "D1", {0.16, -0.16}],
    {Directive[orange, Thick, Opacity[0.65]], Line[{B, E1b, D1b}]},
    {Directive[orange, Dashed, Opacity[0.65]], Line[{A, D1b, Cc}]},
    foot[D1b, "H'"],
    pt[E1b, "E2", {-0.48, 0.22}], pt[D1b, "D2", {-0.42, -0.16}],
    Text[Style["DG = 3", 12, blue, FontFamily -> "Helvetica"], {2.45, 2.2}],
    Text[Style["BE = 3 DE", 12, blue, FontFamily -> "Helvetica"], {1.95, 4.1}]
  }
];

(* Problem 2: AD = AC. Valid branch is E between B and D. *)
x2 = (3/4) (Sqrt[33] - 3);
E2 = {x2, 0}; D2 = {4 x2/3, -r};
exportFig[
  "problem2",
  "Problem 2: AD = AC",
  {
    {Directive[GrayLevel[0.62], Dashed], Circle[A, 6]},
    {Directive[green, Thick], Line[{B, E2, D2}]},
    {Directive[green, Dashed], Line[{A, D2}]},
    foot[D2, "H"],
    pt[E2, "E", {0.10, 0.22}], pt[D2, "D", {0.16, -0.16}],
    Text[Style["AD = AC = 6", 12, green, FontFamily -> "Helvetica"], {1.1, -1.85}],
    Text[Style["BE = 3 DE", 12, green, FontFamily -> "Helvetica"], {1.85, 4.15}]
  }
];

(* Problem 3: AD perpendicular DC, line BD and line AC. Show one segment branch
   and one extension branch; symmetric partners have the same lengths. *)
x3a = Sqrt[27/8]; E3a = {x3a, 0}; D3a = {4 x3a/3, -r};
x3b = Sqrt[27/2]; E3b = {x3b, 0}; D3b = {2 x3b/3, r};
exportFig[
  "problem3",
  "Problem 3: AD perp DC, lines",
  {
    {Directive[GrayLevel[0.55], Dashed], Circle[G, 3]},
    {Directive[blue, Thick], Line[{B, E3a, D3a}]},
    {Directive[blue, Dashed], Line[{A, D3a, Cc}]},
    foot[D3a, "H1"],
    pt[E3a, "E1", {0.10, 0.22}], pt[D3a, "D1", {0.16, -0.16}],
    {Directive[purple, Thick], Line[{B, D3b, E3b}]},
    {Directive[purple, Dashed], Line[{A, D3b, Cc}]},
    foot[D3b, "H2"],
    pt[E3b, "E2", {0.10, 0.22}], pt[D3b, "D2", {0.16, 0.18}],
    Text[Style["BD = 3 sqrt(6)", 12, blue, FontFamily -> "Helvetica"], {2.65, -1.75}],
    Text[Style["BD = 3 sqrt(2)", 12, purple, FontFamily -> "Helvetica"], {3.8, 2.65}]
  },
  {{-4.5, 5.2}, {-2.6, 5.8}}
];

(* Problem 4: BD perpendicular DC. Valid branch has D between B and E. *)
m = (Sqrt[33] - 3)/2;
D4 = {-m, r}; E4 = {-3 m/2, 0};
exportFig[
  "problem4",
  "Problem 4: BD perp DC",
  {
    {Directive[orange, Thick], Line[{B, D4, E4}]},
    {Directive[orange, Dashed], Line[{D4, Cc}]},
    foot[D4, "H"],
    pt[E4, "E", {-0.42, 0.22}], pt[D4, "D", {-0.42, 0.18}],
    Text[Style["BD perpendicular DC", 12, orange, FontFamily -> "Helvetica"], {-2.45, 2.65}],
    Text[Style["E on segment AC", 12, orange, FontFamily -> "Helvetica"], {-2.55, -0.55}]
  }
];

Print["Exported figures to: ", out];
