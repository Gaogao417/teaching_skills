(* ::Package:: *)
(* GeometricScene Constraint Builders - Pure Functions *)

(*
  所有函数都是无状态的纯函数：
  输入：points, parameters
  输出：hypotheses 列表
  
  用法:
    constraints = {
      BuildOrientation[points, baseEdge],
      BuildAngleMin[points, 10],
      BuildSideRatio[points, 0.3]
    };
    scene = AssembleScene[points, baseHypotheses, Flatten[constraints]];
*)

(* ============ 约束构建函数 (无状态纯函数) ============ *)

(* 1. 朝向约束 *)
BuildOrientation[
  points_List,
  baseEdge_List
] := Module[
  {base1, base2, top},
  {base1, base2} = baseEdge;
  top = First[Select[points, !MemberQ[{base1, base2}, #] &]];
  {
    GeometricAssertion[Line[{base1, base2}], "Horizontal"],
    GeometricAssertion[Line[{base1, base2}], "Rightward"],
    GeometricAssertion[{base1, base2, top}, "Counterclockwise"],
    GeometricAssertion[{base1, base2, top}, "Distinct"]
  }
];

(* 2. 角度下界约束 *)
BuildAngleMin[
  points_List,
  minAngleDeg_
] := Module[
  {triples},
  triples = Select[Tuples[points, 3], Length[Union[#]] == 3 &];
  Map[
    Function[{triple}, PlanarAngle[triple] > minAngleDeg Degree],
    triples
  ]
];

(* 3. 边长比约束 *)
BuildSideRatio[
  points_List,
  minRatio_
] := Module[
  {sides},
  sides = {
    EuclideanDistance[points[[1]], points[[2]]],
    EuclideanDistance[points[[2]], points[[3]]],
    EuclideanDistance[points[[3]], points[[1]]]
  };
  {Min[sides] > minRatio * Max[sides]}
];

(* 4. 高度/底边比约束 *)
BuildHeightBase[
  points_List,
  baseEdge_List,
  minRatio_
] := Module[
  {base1, base2, top, height, baseLen},
  {base1, base2} = baseEdge;
  top = First[Select[points, !MemberQ[{base1, base2}, #] &]];
  height = TriangleMeasurement[Triangle[points], {"Height", top}];
  baseLen = EuclideanDistance[base1, base2];
  {height > minRatio * baseLen}
];

(* 5. 高度/周长比约束 *)
BuildHeightPerimeter[
  points_List,
  minRatio_
] := Module[
  {tri, height, perimeter},
  tri = Triangle[points];
  height = TriangleMeasurement[tri, {"Height", First[points]}];
  perimeter = TriangleMeasurement[tri, "Perimeter"];
  {height > minRatio * perimeter}
];

(* ============ 场景组装 (工具函数) ============ *)

AssembleScene[
  points_List,
  baseHypotheses_List,
  constraints_List
] := Module[
  {hypotheses, scene},
  hypotheses = Join[baseHypotheses, Flatten[constraints]];
  scene = GeometricScene[points, Evaluate @ hypotheses];
  scene
];

(* ============ 定性约束构建函数 ============ *)

(* 6. 水平线约束 *)
BuildHorizontalLine[edge_List] := 
  GeometricAssertion[Line[edge], "Horizontal"];

(* 7. 顺逆时针约束 *)
BuildClockwise[points_List] := 
  GeometricAssertion[points, "Clockwise"];

BuildCounterclockwise[points_List] := 
  GeometricAssertion[points, "Counterclockwise"];

(* 8. 区域约束：点在多边形内 *)
BuildPointInPolygon[point_, polyPoints_List] := 
  Element[point, Region@Polygon[polyPoints]];

(* 9. 区域约束：点在三角形内 *)
BuildPointInTriangle[point_, triPoints_List] := 
  Element[point, Region@Triangle[triPoints]];
