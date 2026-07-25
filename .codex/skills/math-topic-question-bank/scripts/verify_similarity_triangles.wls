(* Verify abstract triangle quality for similarity-realization candidates. *)

$CharacterEncoding = "UTF-8";

If[Length[$ScriptCommandLine] < 3,
  Print["usage: wolframscript -file verify_similarity_triangles.wls input.json output.json"];
  Exit[2]
];

inputPath = $ScriptCommandLine[[-2]];
outputPath = $ScriptCommandLine[[-1]];
payload = Import[inputPath, "RawJSON"];

exactValue[value_Association] :=
  ToExpression[value["coefficient"]] Sqrt[value["radicand"]];

verify[candidate_Association] := Module[
  {sides, a, b, c, semiperimeter, area, angles, inradius, circumradius,
   gaps, heights, perimeter, quality, valid},
  sides = exactValue /@ candidate["small_triangle_sides"];
  {a, b, c} = sides;
  semiperimeter = (a + b + c)/2;
  area = FullSimplify[Sqrt[semiperimeter (semiperimeter-a) (semiperimeter-b) (semiperimeter-c)]];
  angles = FullSimplify[{
    ArcCos[(b^2 + c^2 - a^2)/(2 b c)],
    ArcCos[(a^2 + c^2 - b^2)/(2 a c)],
    ArcCos[(a^2 + b^2 - c^2)/(2 a b)]
  }/Degree];
  inradius = FullSimplify[area/semiperimeter];
  circumradius = FullSimplify[a b c/(4 area)];
  gaps = {
    Abs[a-b]/Max[a,b], Abs[a-c]/Max[a,c], Abs[b-c]/Max[b,c]
  };
  perimeter = a+b+c;
  heights = {2 area/a, 2 area/b, 2 area/c};
  valid = TrueQ[
    a+b>c && a+c>b && b+c>a &&
    Min[angles] >= 30 && Min[gaps] >= 1/10 &&
    inradius/circumradius > 1/10 && Min[heights]/perimeter > 2/25
  ];
  quality = <|
    "minimum_angle_deg" -> N[Min[angles], 12],
    "minimum_relative_side_gap" -> N[Min[gaps], 12],
    "inradius_circumradius_ratio" -> N[inradius/circumradius, 12],
    "minimum_height_perimeter_ratio" -> N[Min[heights]/perimeter, 12],
    "wolfram_verified" -> valid
  |>;
  <|"id" -> candidate["id"], "valid" -> valid, "quality" -> quality|>
];

results = verify /@ payload["candidates"];
Export[outputPath, <|"results" -> results|>, "RawJSON"];

