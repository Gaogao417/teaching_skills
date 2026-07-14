(* Generate exact training-number groups from Wolfram integer solution sets. *)

$CharacterEncoding = "UTF-8";

ClearAll[
  fractionText, normalizeLength, exactValue, latexOf, displayOf,
  lengthRecord, makeEntry, slug, family, squarefreePart,
  largestPrimeFactor, simpleRationalQ
];

fractionText[value_] := Module[{q = Together[value]},
  If[Denominator[q] == 1,
    ToString[Numerator[q]],
    ToString[Numerator[q]] <> "/" <> ToString[Denominator[q]]
  ]
];

normalizeLength[coefficient_, radicand_Integer] := Module[
  {factors, outside, inside},
  factors = FactorInteger[radicand];
  outside = Times @@ ((#[[1]]^Floor[#[[2]]/2]) & /@ factors);
  inside = Times @@ ((#[[1]]^Mod[#[[2]], 2]) & /@ factors);
  {Together[coefficient outside], inside}
];

squarefreePart[n_Integer] := normalizeLength[1, n][[2]];
largestPrimeFactor[1] := 1;
largestPrimeFactor[n_Integer] := Max[FactorInteger[Abs[n]][[All, 1]]];
simpleRationalQ[value_] := Module[{q = Together[value]},
  Max[largestPrimeFactor[Numerator[q]], largestPrimeFactor[Denominator[q]]] <= 7
];
exactValue[value_List] := value[[1]] Sqrt[value[[2]]];

latexOf[{coefficient_, 1}] := ToString[TeXForm[coefficient]];
latexOf[{1, radicand_}] := "\\sqrt{" <> ToString[radicand] <> "}";
latexOf[{-1, radicand_}] := "-\\sqrt{" <> ToString[radicand] <> "}";
latexOf[{coefficient_, radicand_}] :=
  ToString[TeXForm[coefficient]] <> "\\sqrt{" <> ToString[radicand] <> "}";

displayOf[{coefficient_, 1}] := fractionText[coefficient];
displayOf[{1, radicand_}] := "sqrt(" <> ToString[radicand] <> ")";
displayOf[{-1, radicand_}] := "-sqrt(" <> ToString[radicand] <> ")";
displayOf[{coefficient_, radicand_}] :=
  fractionText[coefficient] <> "*sqrt(" <> ToString[radicand] <> ")";

lengthRecord[value_List] := <|
  "coefficient" -> fractionText[value[[1]]],
  "radicand" -> value[[2]],
  "latex" -> latexOf[value],
  "display" -> displayOf[value]
|>;

slug[text_] := StringReplace[ToLowerCase[ToString[text]], {
  "/" -> "-over-", "*" -> "-times-", "(" -> "", ")" -> "",
  " " -> "", "," -> "-", "." -> "-"
}];

makeEntry[id_, familyId_, values_List, relation_, tags_List, parameters_: <||>] := <|
  "id" -> id,
  "family" -> familyId,
  "label" -> "(" <> StringRiffle[displayOf /@ values, ", "] <> ")",
  "values" -> (lengthRecord /@ values),
  "relation" -> relation,
  "tags" -> tags,
  "parameters" -> parameters
|>;

family[id_, title_, description_, entries_] := <|
  "id" -> id,
  "title" -> title,
  "description" -> description,
  "entries" -> entries
|>;

(* 1. Reduced rational lengths and their exact multipliers. *)
rationalRules = Solve[
  1 <= p <= 12 && 2 <= q <= 12 && GCD[p, q] == 1 && p <= 6 q,
  {p, q}, Integers
];
baseFractions = DeleteDuplicates[(p/q) /. rationalRules];
rationalMultipliers = {2, 3, 4, 5, 6};
rationalCandidates = Flatten[Outer[List, baseFractions, rationalMultipliers], 1];
rationalCandidates = Select[
  rationalCandidates,
  #[[1]] #[[2]] <= 12 &&
    Denominator[Together[#[[1]] #[[2]]]] <= 24 &&
    simpleRationalQ[#[[1]]] &&
    simpleRationalQ[#[[1]] #[[2]]] &
];
rationalEntries = Map[
  Function[candidate,
    Module[{first = candidate[[1]], multiplier = candidate[[2]], second},
      second = Together[first multiplier];
      makeEntry[
        "rational-" <> slug[fractionText[first]] <> "-x-" <> slug[fractionText[multiplier]],
        "rational_multiple_pairs",
        {{first, 1}, {second, 1}},
        "second_equals_multiplier_times_first",
        {"fraction_lengths", "rational_multiple", "integer_multiplier"},
        <|"multiplier" -> fractionText[multiplier]|>
      ]
    ]
  ],
  rationalCandidates
];
rationalEntries = DeleteDuplicatesBy[rationalEntries, # ["id"] &];

(* 2a. The parameterized family sqrt(a), sqrt(k a). Solve supplies all bounded parameters. *)
sqrtKaRules = Solve[
  2 <= a <= 10 && 2 <= k <= 10,
  {a, k}, Integers
];
sqrtKaEntries = Map[
  Function[rule,
    Module[{av = a /. rule, kv = k /. rule, first, second, quotient},
      first = normalizeLength[1, av];
      second = normalizeLength[1, av kv];
      quotient = FullSimplify[
        Sqrt[k a]/Sqrt[a] /. rule,
        Assumptions -> Element[{a, k}, Integers] && a > 0 && k > 0
      ];
      makeEntry[
        "sqrt-ka-a" <> ToString[av] <> "-k" <> ToString[kv],
        "radical_multiple_pairs",
        {first, second},
        "second_equals_sqrt_k_times_first",
        Join[
          {"sqrt_a_sqrt_ka", "radical_quotient"},
          If[IntegerQ[quotient], {"integer_multiplier"}, {}],
          If[kv == av, {"k_equals_a"}, {}]
        ],
        <|
          "a" -> av,
          "k" -> kv,
          "source_radicands" -> {av, av kv},
          "quotient_latex" -> ToString[TeXForm[quotient]]
        |>
      ]
    ]
  ],
  sqrtKaRules
];

(* 2b. Coefficient-radical pairs whose bounded radicands are not coprime. *)
nonCoprimeRules = Solve[
  2 <= a < b <= 10 && GCD[a, b] > 1 && 1 <= x <= 3 && 1 <= y <= 3,
  {a, b, x, y}, Integers
];
nonCoprimeEntries = Map[
  Function[rule,
    Module[{av = a /. rule, bv = b /. rule, xv = x /. rule, yv = y /. rule},
      makeEntry[
        "noncoprime-a" <> ToString[av] <> "-b" <> ToString[bv] <>
          "-x" <> ToString[xv] <> "-y" <> ToString[yv],
        "noncoprime_radicand_pairs",
        {normalizeLength[xv, av], normalizeLength[yv, bv]},
        "source_radicands_share_a_nontrivial_factor",
        {"noncoprime_radicands", "radical_simplification"},
        <|"a" -> av, "b" -> bv, "x" -> xv, "y" -> yv, "gcd" -> GCD[av, bv]|>
      ]
    ]
  ],
  nonCoprimeRules
];
nonCoprimeEntries = Select[
  nonCoprimeEntries,
  RootReduce[exactValue[#["values"] /. record_Association :>
    {ToExpression[record["coefficient"]], record["radicand"]}][[1]] -
    exactValue[#["values"] /. record_Association :>
    {ToExpression[record["coefficient"]], record["radicand"]}][[2]]] =!= 0 &
];

(* 3a. Complete bounded primitive Pythagorean solution set. *)
pythagoreanRules = Solve[
  1 <= sideA < sideB < hypotenuse <= 100 &&
    sideA^2 + sideB^2 == hypotenuse^2 &&
    GCD[sideA, sideB, hypotenuse] == 1,
  {sideA, sideB, hypotenuse}, Integers
];
pythagoreanTriples = ({sideA, sideB, hypotenuse} /. pythagoreanRules);
commonTriples = {{3, 4, 5}, {5, 12, 13}, {7, 24, 25}};
integerTripleEntries = Map[
  Function[triple,
    makeEntry[
      "pythagorean-" <> StringRiffle[ToString /@ triple, "-"],
      "right_triangle_integer_triples",
      ({#, 1} & /@ triple),
      "leg1_squared_plus_leg2_squared_equals_hypotenuse_squared",
      Join[
        {"primitive_pythagorean"},
        If[MemberQ[commonTriples, triple], {"common_memorized"}, {"extended_primitive"}]
      ],
      <|"squared_lengths" -> (triple^2)|>
    ]
  ],
  pythagoreanTriples
];

(* 3b. Exact special-angle base ratios. *)
specialAngleEntries = {
  makeEntry[
    "special-angle-30-60-90", "right_triangle_special_angles",
    {{1, 1}, {1, 3}, {2, 1}},
    "leg1_squared_plus_leg2_squared_equals_hypotenuse_squared",
    {"30_degrees", "60_degrees", "trig_ratio"},
    <|"angles" -> {30, 60, 90}|>
  ],
  makeEntry[
    "special-angle-45-45-90", "right_triangle_special_angles",
    {{1, 1}, {1, 1}, {1, 2}},
    "leg1_squared_plus_leg2_squared_equals_hypotenuse_squared",
    {"45_degrees", "isosceles_right", "trig_ratio"},
    <|"angles" -> {45, 45, 90}|>
  ]
};

(* 3c. All x+y=z solutions in 1..20 whose simplified radicands are below 10. *)
sqrtSquareRules = Solve[
  1 <= sx < sy < sz <= 20 && sx + sy == sz,
  {sx, sy, sz}, Integers
];
sqrtSquareTriples = ({sx, sy, sz} /. sqrtSquareRules);
sqrtSquareTriples = Select[
  sqrtSquareTriples,
  Max[squarefreePart /@ #] < 10 &
];
sqrtSquareEntries = Map[
  Function[squares,
    makeEntry[
      "sqrt-squares-" <> StringRiffle[ToString /@ squares, "-"],
      "right_triangle_sqrt_square_sums",
      (normalizeLength[1, #] & /@ squares),
      "leg1_squared_plus_leg2_squared_equals_hypotenuse_squared",
      {"sqrt_squared_lengths", "radicand_under_10_after_simplification"},
      <|"squared_lengths" -> squares|>
    ]
  ],
  sqrtSquareTriples
];

(* 4a. Integer right triangles are scaled only by small reduced fractions. *)
simpleFractionScaleRules = Solve[
  1 <= scaleP <= 7 && 2 <= scaleQ <= 7 &&
    GCD[scaleP, scaleQ] == 1 &&
    scaleQ <= 2 scaleP && scaleP <= 2 scaleQ,
  {scaleP, scaleQ}, Integers
];
simpleFractionScales = DeleteDuplicates[
  normalizeLength[scaleP/scaleQ, 1] /. simpleFractionScaleRules
];

integerBaseTriangles = Map[
  Function[triple,
    <|
      "id" -> ("pythagorean-" <> StringRiffle[ToString /@ triple, "-"]),
      "values" -> ({#, 1} & /@ triple)
    |>
  ],
  commonTriples
];

(* 4b. Radical base triangles may use those fractions or compatible simple radicals. *)
simpleRadicandRules = Solve[2 <= scaleD <= 7, scaleD, Integers];
simpleRadicands = Select[scaleD /. simpleRadicandRules, SquareFreeQ];
simpleRadicalScales = DeleteDuplicates[Join[
  (normalizeLength[1, #] & /@ simpleRadicands),
  (normalizeLength[1/#, #] & /@ simpleRadicands)
]];

radicalBaseTriangles = {
  <|"id" -> "special-angle-30-60-90", "values" -> {{1, 1}, {1, 3}, {2, 1}}|>,
  <|"id" -> "special-angle-45-45-90", "values" -> {{1, 1}, {1, 1}, {1, 2}}|>
};

compatibleRadicalScaleQ[base_Association, scale_List] :=
  MemberQ[Select[base["values"][[All, 2]], # > 1 &], scale[[2]]];

scaleTriangle[familyId_, base_Association, scale_List] := Module[{scaledValues, scaleTag},
  scaledValues = Map[
    normalizeLength[#[[1]] scale[[1]], #[[2]] scale[[2]]] &,
    base["values"]
  ];
  scaleTag = Which[
    scale[[2]] == 1, "fraction_scale",
    Denominator[scale[[1]]] == scale[[2]], "reciprocal_radical_scale",
    True, "simple_radical_scale"
  ];
  makeEntry[
    "scaled-" <> base["id"] <> "-by-" <> slug[displayOf[scale]],
    familyId,
    scaledValues,
    "scaled_copy_of_right_triangle",
    {"trig_ratio", "common_factor_cancellation", scaleTag},
    <|
      "base_entry_id" -> base["id"],
      "scale" -> lengthRecord[scale],
      "scale_numerator_max_prime" -> If[
        Numerator[scale[[1]]] == 1, 1,
        Max[FactorInteger[Numerator[scale[[1]]]][[All, 1]]]
      ],
      "scale_denominator_max_prime" -> If[
        Denominator[scale[[1]]] == 1, 1,
        Max[FactorInteger[Denominator[scale[[1]]]][[All, 1]]]
      ]
    |>
  ]
];

integerFractionEntries = Map[
  scaleTriangle["integer_right_triangles_fraction_scaled", #[[1]], #[[2]]] &,
  Tuples[{integerBaseTriangles, simpleFractionScales}]
];

radicalScalePairs = Flatten[
  Map[
    Function[base,
      Join[
        ({base, #} & /@ simpleFractionScales),
        ({base, #} & /@ Select[simpleRadicalScales, compatibleRadicalScaleQ[base, #] &])
      ]
    ],
    radicalBaseTriangles
  ],
  1
];
radicalSimpleEntries = Map[
  scaleTriangle["radical_right_triangles_simple_scaled", #[[1]], #[[2]]] &,
  radicalScalePairs
];

integerFractionEntries = DeleteDuplicatesBy[integerFractionEntries, # ["id"] &];
radicalSimpleEntries = DeleteDuplicatesBy[radicalSimpleEntries, # ["id"] &];

families = {
  family[
    "rational_multiple_pairs", "Rational multiple pairs",
    "Reduced fractions combined with common integer multipliers.", rationalEntries
  ],
  family[
    "radical_multiple_pairs", "sqrt(a) and sqrt(k a)",
    "Preserves source radicands and records normalized values and quotient.", sqrtKaEntries
  ],
  family[
    "noncoprime_radicand_pairs", "Non-coprime radicand pairs",
    "Uses non-coprime a,b with small integer coefficients x,y.", nonCoprimeEntries
  ],
  family[
    "right_triangle_integer_triples", "Primitive Pythagorean triples",
    "Complete primitive integer solution set with hypotenuse at most 100.", integerTripleEntries
  ],
  family[
    "right_triangle_special_angles", "Special-angle right triangles",
    "Exact side ratios for 30-60-90 and 45-45-90 triangles.", specialAngleEntries
  ],
  family[
    "right_triangle_sqrt_square_sums", "Square-root right triangles",
    "Uses x+y=z in 1..20 with normalized radicands below 10.", sqrtSquareEntries
  ],
  family[
    "integer_right_triangles_fraction_scaled", "Integer right triangles scaled by fractions",
    "Common integer triples scaled only by reduced fractions with numerator and denominator at most seven.", integerFractionEntries
  ],
  family[
    "radical_right_triangles_simple_scaled", "Radical right triangles with simple scales",
    "Special-angle radical triangles scaled by small fractions or compatible simple radicals.", radicalSimpleEntries
  ]
};

payload = <|
  "schema" -> "math_training_number_database/v1",
  "database" -> <|
    "id" -> "question-bank-training-numbers",
    "generator" -> "generate_training_numbers.wls",
    "bounds" -> <|
      "rational_numerator_max" -> 12,
      "rational_denominator_max" -> 12,
      "rational_largest_prime_factor_max" -> 7,
      "sqrt_a_max" -> 10,
      "sqrt_k_max" -> 10,
      "pythagorean_hypotenuse_max" -> 100,
      "sqrt_squared_length_max" -> 20,
      "scale_fraction_numerator_max" -> 7,
      "scale_fraction_denominator_max" -> 7,
      "scale_largest_prime_factor_max" -> 7
    |>
  |>,
  "families" -> families
|>;

If[Length[$ScriptCommandLine] < 2,
  Print["usage: wolframscript -file generate_training_numbers.wls OUTPUT.json"];
  Exit[2]
];
Export[Last[$ScriptCommandLine], payload, "RawJSON", "Compact" -> False];
Print[
  "generated " <>
  ToString[Total[(Length[# ["entries"]] &) /@ families]] <>
  " exact number groups"
];
