#!/usr/bin/env python3
"""Author the 50-slot two-ratio auxiliary-line question bank plans.

This script is an authoring scaffold only: it freezes a reviewed coverage plan
and serializes the main Agent's approved single-item plan assignments.  Every
given ratio uses coprime integers from 1 through 5.  It does not call Wolfram,
compile TikZ, run an audit, resolve an assignment, or mark the bank ready.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from fractions import Fraction
from itertools import product
from math import gcd
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE_EXPLANATION = (
    "../../专题/2026-07-12-比例辅助线两组比例-待审核/"
    "02-student-explanation.plan.assignment.yaml"
)

RATIO_SEGMENTS = {
    "x": ("AE", "EC"),
    "w": ("BD", "DC"),
    "y": ("AP", "PD"),
    "z": ("BP", "PE"),
}
RATIO_LATEX = {
    "x": r"\dfrac{AE}{EC}",
    "w": r"\dfrac{BD}{DC}",
    "y": r"\dfrac{AP}{PD}",
    "z": r"\dfrac{BP}{PE}",
}

BLUE = "#2563eb"
RED = "#dc2626"
GREEN = "#059669"
DEFAULT_INTEGER_NORMAL_OFFSET_CM = 0.22
DEFAULT_FRACTION_NORMAL_OFFSET_CM = 0.30

ANNOTATION_PLACEMENTS = {
    "AE": "above left",
    "EC": "above right",
    "BD": "below",
    "DC": "below",
    "AP": "left",
    "PD": "right",
    "BP": "above left",
    "PE": "above right",
    "CF": "right",
    "AF": "above left",
    "BE": "above",
    "EF": "above",
    "PF": "above",
    "BC": "below",
}

# Direction is read from the two endpoint names in each annotation target.
# counterclockwise means (-dy, dx); clockwise means (dy, -dx).
ANNOTATION_NORMAL_SIDES = {
    "AE": "counterclockwise",
    "EC": "counterclockwise",
    "BD": "clockwise",
    "DC": "clockwise",
    "AP": "counterclockwise",
    "PD": "counterclockwise",
    "BP": "counterclockwise",
    "PE": "clockwise",
    "CF": "clockwise",
    "AF": "clockwise",
    "BE": "clockwise",
    "EF": "clockwise",
    "PF": "clockwise",
    "BC": "clockwise",
}

ANNOTATION_NORMAL_OFFSETS_CM = {
    # The midpoint of BE is close to P in this construction. A compact offset
    # keeps the value between P and D instead of pushing it onto either label.
    "BE": 0.18,
}

# Per-item exceptions for segments whose surrounding region is too narrow for
# an unambiguous offset value. The renderer writes the complete relation in a
# free legend area instead of placing a number on the geometry.
GLOBAL_LEGEND_SEGMENTS = {"BE", "BC"}
LEGEND_OVERRIDES = {
    "Q004": {"BP", "PE"},
    "Q016": {"BP", "PE"},
    "Q028": {"BP", "PE"},
    "Q040": {"BP", "PE"},
}

# One user-reviewed layout fixture shared by the complete bank.  With
# B=(0,0), C=(8,0), these coordinates give angles A=70°, B=60°, C=50°.
# Only A/B/C are fixed; D/E/P remain native GeometricScene constructions.
BASE_TRIANGLE_COORDINATES = {
    "A": (3.260829876384, 5.647923020735),
    "B": (0.0, 0.0),
    "C": (8.0, 0.0),
}

# Each route is (known ratios, requested ratio).  All twelve ways to choose two
# known ratio lines and a third requested line are cycled evenly.
BASE_ROUTES = (
    (("x", "w"), "y"),
    (("x", "w"), "z"),
    (("x", "y"), "w"),
    (("x", "y"), "z"),
    (("x", "z"), "w"),
    (("x", "z"), "y"),
    (("w", "y"), "x"),
    (("w", "y"), "z"),
    (("w", "z"), "x"),
    (("w", "z"), "y"),
    (("y", "z"), "x"),
    (("y", "z"), "w"),
)
ROUTES = BASE_ROUTES * 4 + BASE_ROUTES[:2]


def fraction_plain(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def fraction_latex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\frac{{{value.numerator}}}{{{value.denominator}}}"


def ratio_text(value: Fraction) -> str:
    return f"{value.numerator}:{value.denominator}"


def ratio_constraint(key: str, value: Fraction) -> str:
    first, second = RATIO_SEGMENTS[key]
    return (
        f"{value.denominator} EuclideanDistance[{first[0]}, {first[1]}] == "
        f"{value.numerator} EuclideanDistance[{second[0]}, {second[1]}]"
    )


def ratio_values(x: Fraction, w: Fraction) -> dict[str, Fraction]:
    return {
        "x": x,
        "w": w,
        "y": x * (w + 1) / w,
        "z": w * (x + 1) / x,
    }


def small_integer_ratios() -> set[Fraction]:
    return {
        Fraction(numerator, denominator)
        for numerator in range(1, 6)
        for denominator in range(1, 6)
        if gcd(numerator, denominator) == 1
    }


def select_cases() -> list[dict[str, Fraction]]:
    """Choose 50 distinct base geometries whose two displayed ratios are small."""

    allowed = small_integer_ratios()
    used_base: set[tuple[Fraction, Fraction]] = set()
    cases: list[dict[str, Fraction]] = []
    for known, target in ROUTES:
        candidates: list[dict[str, Fraction]] = []
        for x, w in product(allowed, repeat=2):
            values = ratio_values(x, w)
            answer = values[target]
            if not all(values[key] in allowed for key in known):
                continue
            if answer.numerator > 8 or answer.denominator > 8:
                continue
            candidates.append(values)
        candidates.sort(
            key=lambda values: (
                abs(float(values["x"]) - 1) + abs(float(values["w"]) - 1),
                values[target].numerator + values[target].denominator,
                values[known[0]].numerator + values[known[0]].denominator,
                values[known[1]].numerator + values[known[1]].denominator,
            )
        )
        chosen = next(
            values
            for values in candidates
            if (values["x"], values["w"]) not in used_base
        )
        used_base.add((chosen["x"], chosen["w"]))
        cases.append(chosen)
    return cases


def difficulty(index: int) -> str:
    if index < 25:
        return "foundation"
    return "standard"


def variation(index: int) -> str:
    return "changed_question" if index % 2 == 0 else "changed_numbers"


def relation_for(known: tuple[str, str]) -> str:
    key = frozenset(known)
    relations = {
        frozenset(("x", "w")): r"y=\dfrac{x(w+1)}{w},\quad z=\dfrac{w(x+1)}{x}",
        frozenset(("x", "y")): r"w=\dfrac{x}{y-x},\quad z=\dfrac{x+1}{y-x}",
        frozenset(("x", "z")): r"w=\dfrac{zx}{x+1},\quad y=x+\dfrac{x+1}{z}",
        frozenset(("w", "y")): r"x=\dfrac{yw}{w+1},\quad z=w+\dfrac{w+1}{y}",
        frozenset(("w", "z")): r"x=\dfrac{w}{z-w},\quad y=\dfrac{w+1}{z-w}",
        frozenset(("y", "z")): r"x=\dfrac{yz-1}{z+1},\quad w=\dfrac{yz-1}{y+1}",
    }
    return relations[key]


def auxiliary_route(involved: set[str]) -> dict[str, Any]:
    missing = ({"x", "w", "y", "z"} - involved).pop()
    routes = {
        # Missing BE ratio: AC, AD and BC surround triangle ACD.
        "z": {
            "description": "过 C 作 CF 平行 AD，交直线 BE 于 F",
            "f_region": ("B", "E"),
            "parallel": (("C", "F"), ("A", "D")),
            "f_placement": "right",
            "connection": "y",
            "models": [
                {
                    "shape": "8字",
                    "triangles": r"\triangle EAP\sim\triangle ECF",
                    "anchor": "x",
                    "output": ("AP", "CF"),
                    "highlight": (("E", "A", "P"), ("E", "C", "F")),
                },
                {
                    "shape": "A字",
                    "triangles": r"\triangle BDP\sim\triangle BCF",
                    "anchor": "w",
                    "output": ("DP", "CF"),
                    "highlight": (("B", "D", "P"), ("B", "C", "F")),
                },
            ],
        },
        # Missing BC ratio: AC, AD and BE surround triangle AEP.
        "w": {
            "description": "过 A 作 AF 平行 EP，交直线 BC 于 F",
            "f_region": ("B", "C"),
            "parallel": (("A", "F"), ("E", "P")),
            "f_placement": "below left",
            "connection": "z",
            "models": [
                {
                    "shape": "A字",
                    "triangles": r"\triangle CAF\sim\triangle CEB",
                    "anchor": "x",
                    "output": ("AF", "BE"),
                    "highlight": (("C", "A", "F"), ("C", "E", "B")),
                },
                {
                    "shape": "A字",
                    "triangles": r"\triangle DAF\sim\triangle DPB",
                    "anchor": "y",
                    "output": ("AF", "BP"),
                    "highlight": (("D", "A", "F"), ("D", "P", "B")),
                },
            ],
        },
        # Missing AD ratio: AC, BE and BC surround triangle ECB.
        "y": {
            "description": "过 E 作 EF 平行 CB，交直线 AD 于 F",
            "f_region": ("A", "D"),
            "parallel": (("E", "F"), ("C", "B")),
            "f_placement": "above left",
            "connection": "w",
            "models": [
                {
                    "shape": "A字",
                    "triangles": r"\triangle AEF\sim\triangle ACD",
                    "anchor": "x",
                    "output": ("EF", "DC"),
                    "highlight": (("A", "E", "F"), ("A", "C", "D")),
                },
                {
                    "shape": "8字",
                    "triangles": r"\triangle PEF\sim\triangle PBD",
                    "anchor": "z",
                    "output": ("EF", "BD"),
                    "highlight": (("P", "E", "F"), ("P", "B", "D")),
                },
            ],
        },
        # Missing AC ratio: AD, BE and BC surround triangle PDB.
        "x": {
            "description": "过 P 作 PF 平行 DB，交直线 AC 于 F",
            "f_region": ("A", "C"),
            "parallel": (("P", "F"), ("D", "B")),
            "f_placement": "right",
            "connection": "w",
            "models": [
                {
                    "shape": "A字",
                    "triangles": r"\triangle APF\sim\triangle ADC",
                    "anchor": "y",
                    "output": ("PF", "DC"),
                    "highlight": (("A", "P", "F"), ("A", "D", "C")),
                },
                {
                    "shape": "A字",
                    "triangles": r"\triangle EFP\sim\triangle ECB",
                    "anchor": "z",
                    "output": ("PF", "BC"),
                    "highlight": (("E", "F", "P"), ("E", "C", "B")),
                },
            ],
        },
    }
    return routes[missing]


def model_output_ratio(model: dict[str, Any], values: dict[str, Fraction]) -> Fraction:
    anchor = model["anchor"]
    value = values[anchor]
    first, second = model["output"]
    formulas = {
        ("x", "AP", "CF"): value,
        ("w", "DP", "CF"): value / (value + 1),
        ("x", "AF", "BE"): value + 1,
        ("y", "AF", "BP"): value + 1,
        ("x", "EF", "DC"): value / (value + 1),
        ("z", "EF", "BD"): 1 / value,
        ("y", "PF", "DC"): value / (value + 1),
        ("z", "PF", "BC"): 1 / (value + 1),
    }
    return formulas[(anchor, first, second)]


def segment_annotation(
    segment: str,
    shares: int | Fraction,
    *,
    color: str,
    suffix: str,
    opposite: bool = False,
) -> dict[str, Any]:
    normalized = "PD" if segment == "DP" else segment
    share_value = Fraction(shares)
    placement = ANNOTATION_PLACEMENTS.get(normalized, "above")
    if opposite:
        opposites = {
            "above": "below",
            "below": "above",
            "left": "right",
            "right": "left",
            "above left": "below right",
            "above right": "below left",
        }
        placement = opposites.get(placement, "below")
    annotation = {
        "id": f"{suffix}-{segment.lower()}",
        "target": list(segment),
        "text": f"{fraction_plain(share_value)}份",
        "placement": placement,
        "normal_side": ANNOTATION_NORMAL_SIDES.get(normalized, "auto"),
        "segment_position": "auto",
        "normal_offset_cm": (
            DEFAULT_INTEGER_NORMAL_OFFSET_CM
            if share_value.denominator == 1
            else DEFAULT_FRACTION_NORMAL_OFFSET_CM
        ),
        "color": color,
    }
    if normalized in ANNOTATION_NORMAL_OFFSETS_CM:
        annotation["normal_offset_cm"] = ANNOTATION_NORMAL_OFFSETS_CM[normalized]
    return annotation


def known_annotations(
    values: dict[str, Fraction],
    known: tuple[str, str],
    item_id: str = "",
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for key in known:
        first, second = RATIO_SEGMENTS[key]
        ratio = values[key]
        annotations.extend(
            [
                segment_annotation(first, ratio.numerator, color=BLUE, suffix=f"known-{key}"),
                segment_annotation(second, ratio.denominator, color=BLUE, suffix=f"known-{key}"),
            ]
        )
    return apply_annotation_layout_overrides(item_id, annotations)


def apply_annotation_layout_overrides(
    item_id: str,
    annotations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    legend_segments = GLOBAL_LEGEND_SEGMENTS | LEGEND_OVERRIDES.get(item_id, set())
    for annotation in annotations:
        segment = "".join(annotation["target"])
        normalized = "PD" if segment == "DP" else segment
        if normalized in legend_segments:
            annotation["segment_position"] = "legend"
            annotation["legend_placement"] = "top_left"
    return annotations


def staged_model_share_additions(
    models: list[dict[str, Any]],
    values: dict[str, Fraction],
    known: tuple[str, str],
    target: str | None = None,
) -> list[list[tuple[str, Fraction]]]:
    """Compute cumulative, non-duplicated shares added by each model.

    The final model must leave both requested target segments readable on the
    diagram.  Those labels are the visible result of solving the second A/8
    model, not a third algebra-only step.
    """

    visible: dict[str, Fraction] = {}
    for key in known:
        first, second = RATIO_SEGMENTS[key]
        ratio = values[key]
        visible["".join(sorted(first))] = Fraction(ratio.numerator)
        visible["".join(sorted(second))] = Fraction(ratio.denominator)

    additions_by_stage: list[list[tuple[str, Fraction]]] = []
    for stage_index, model in enumerate(models):
        first, second = model["output"]
        first_key = "".join(sorted(first))
        second_key = "".join(sorted(second))
        ratio = model_output_ratio(model, values)
        first_share = visible.get(first_key)
        second_share = visible.get(second_key)
        additions: list[tuple[str, Fraction]] = []
        if first_share is None and second_share is None:
            first_share = Fraction(ratio.numerator)
            second_share = Fraction(ratio.denominator)
            additions = [(first, first_share), (second, second_share)]
        elif first_share is None:
            first_share = ratio * second_share
            additions = [(first, first_share)]
        elif second_share is None:
            second_share = first_share / ratio
            additions = [(second, second_share)]
        visible[first_key] = first_share
        visible[second_key] = second_share

        if target is not None and stage_index == len(models) - 1:
            target_first, target_second = RATIO_SEGMENTS[target]
            target_first_key = "".join(sorted(target_first))
            target_second_key = "".join(sorted(target_second))
            target_ratio = values[target]
            target_first_share = visible.get(target_first_key)
            target_second_share = visible.get(target_second_key)
            if target_first_share is None and target_second_share is None:
                target_first_share = Fraction(target_ratio.numerator)
                target_second_share = Fraction(target_ratio.denominator)
                additions.extend(
                    [
                        (target_first, target_first_share),
                        (target_second, target_second_share),
                    ]
                )
            elif target_first_share is None:
                target_first_share = target_ratio * target_second_share
                additions.append((target_first, target_first_share))
            elif target_second_share is None:
                target_second_share = target_first_share / target_ratio
                additions.append((target_second, target_second_share))
            visible[target_first_key] = target_first_share
            visible[target_second_key] = target_second_share
        additions_by_stage.append(additions)
    return additions_by_stage


def derived_annotations(
    models: list[dict[str, Any]],
    values: dict[str, Fraction],
    known: tuple[str, str],
    target: str,
    visible_stage_count: int,
) -> list[dict[str, Any]]:
    annotations: list[dict[str, Any]] = []
    for stage_index, additions in enumerate(
        staged_model_share_additions(models, values, known, target), start=1
    ):
        if stage_index > visible_stage_count:
            break
        for segment, share in additions:
            annotations.append(
                segment_annotation(
                    segment,
                    share,
                    color=RED if stage_index == 1 else GREEN,
                    suffix=f"model-{stage_index}",
                )
            )
    return annotations


def base_diagram_spec() -> dict[str, Any]:
    return {
        "segments": [["A", "B"], ["B", "C"], ["C", "A"], ["A", "D"], ["B", "E"]],
        "polygons": [],
        "markers": [],
        "labels": {
            "A": {"text": "A", "placement": "above"},
            "B": {"text": "B", "placement": "below left"},
            "C": {"text": "C", "placement": "below right"},
            "D": {"text": "D", "placement": "below"},
            "E": {"text": "E", "placement": "above right"},
            "P": {"text": "P", "placement": "left"},
        },
        "annotations": [],
    }


def prompt_scene(
    values: dict[str, Fraction],
    known: tuple[str, str],
) -> dict[str, Any]:
    hypotheses = [
        "Triangle[{A, B, C}]",
        "A == {3.260829876384, 5.647923020735}",
        "B == {0, 0}",
        "C == {8, 0}",
        "Element[D, Line[{B, C}]]",
        "Element[E, Line[{A, C}]]",
        "Element[P, Line[{A, D}]]",
        "Element[P, Line[{B, E}]]",
        *(ratio_constraint(key, values[key]) for key in known),
    ]
    return {
        "scene_code": f"GeometricScene[{{A, B, C, D, E, P}}, {{{', '.join(hypotheses)}}}]",
        "points": ["A", "B", "C", "D", "E", "P"],
        "point_roles": {
            "anchors": ["A", "B", "C"],
            "constructed": ["D", "E", "P"],
            "auxiliary": [],
        },
        "fixed_layout_points": {
            name: list(coordinates)
            for name, coordinates in BASE_TRIANGLE_COORDINATES.items()
        },
        "diagram_spec": base_diagram_spec(),
        "rationale": "显式声明 Triangle[{A,B,C}]；A、B、C 使用全题库统一且经人工确认的 70°/60°/50° 版式坐标，只翻译题面的两组整数比、在线点和交点。",
        "model_used": "main-agent-reviewed-authoring",
        "model_attempts": [],
    }


def solution_scene(
    route: dict[str, Any],
    annotations: list[dict[str, Any]],
    model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    f0, f1 = route["f_region"]
    (p0, p1), (q0, q1) = route["parallel"]
    spec = base_diagram_spec()
    spec["segments"].append(
        {"from": p0, "to": p1, "dash": "dashed", "role": "auxiliary"}
    )
    spec["auxiliary_constructions"] = [
        {
            "point": "F",
            "constructed_segment": [p0, p1],
            "carrier_segment": [f0, f1],
            "dash": "dashed",
            "extend_carrier_if_needed": True,
        }
    ]
    spec["markers"] = [
        {"type": "parallel", "segments": [[p0, p1], [q0, q1]]}
    ]
    spec["labels"]["F"] = {"text": "F", "placement": route["f_placement"]}
    spec["annotations"] = annotations
    if model is not None:
        first_triangle, second_triangle = model["highlight"]
        spec["polygons"] = [
            {"points": list(first_triangle), "fill": "#eff6ff", "stroke": "#93c5fd"},
            {"points": list(second_triangle), "fill": "#fef2f2", "stroke": "#fca5a5"},
        ]
    hypotheses = [
        f"Element[F, InfiniteLine[{{{f0}, {f1}}}]]",
        f'GeometricAssertion[{{Line[{{{p0}, {p1}}}], Line[{{{q0}, {q1}}}]}}, "Parallel"]',
    ]
    return {
        "scene_code": f"GeometricScene[{{A, B, C, D, E, P, F}}, {{{', '.join(hypotheses)}}}]",
        "points": ["A", "B", "C", "D", "E", "P", "F"],
        "point_roles": {
            "anchors": ["A", "B", "C", "D", "E", "P"],
            "constructed": [],
            "auxiliary": ["F"],
        },
        "diagram_spec": spec,
        "rationale": f"复用 prompt 坐标后只添加题解辅助构造：{route['description']}。",
        "model_used": "main-agent-reviewed-authoring",
        "model_attempts": [],
    }


def diagram_slot(
    item_id: str,
    stem: str,
    values: dict[str, Fraction],
    known: tuple[str, str],
    target: str,
    *,
    stage: str,
    ordered_models: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    item_key = item_id.lower()
    prompt_id = f"question_bank.auxiliary50.{item_key}.prompt"
    if stage == "prompt":
        return {
            "slot_id": prompt_id,
            "diagram_ref": prompt_id,
            "variant": "prompt",
            "disclosure_policy": "clean",
            "required": True,
            "on_failure": "fail_assignment",
            "placement": "diagram_col",
            "layout_role": "question_sidecar",
            "display_profile": "worksheet_geometry_sidecar",
            "engine": "geometric_scene",
            "diagram_kind": "synthetic_geometry",
            "engine_options": {
                "scene_payload": prompt_scene(values, known),
                "seed": 717000 + int(item_id[1:]),
            },
            "teaching_intent": "practice_prompt",
            "problem_context": {
                "stem_latex": stem,
                "source_problem_text": "逐字翻译题面给出的两组整数比。原题图只画 ABC、D、E、P 与两条交线；不得画 F、辅助平行线、相似标记、推导或答案。",
            },
            "semantic_constraints": {
                "given_objects": ["A", "B", "C", "D", "E", "P"],
                "given_constraints": [
                    "D lies on segment BC",
                    "E lies on segment AC",
                    "P is the intersection of segments AD and BE",
                    *(f"given ratio {key}={ratio_text(values[key])}" for key in known),
                ],
                "clean_forbidden": [
                    "do not draw F or an auxiliary parallel line",
                    "do not show similar triangles, derived ratios, or the answer",
                    "do not draw numeric labels on the geometry",
                ],
            },
            "visual_requirements": {"required_visible_annotations": {"markers": [], "texts": []}},
        }

    route = auxiliary_route(set(known) | {target})
    (p0, p1), (q0, q1) = route["parallel"]
    if ordered_models is None:
        raise ValueError("solution stages require ordered_models")
    stage_index = {"helper": 0, "model1": 1, "model2": 2}[stage]
    visible_models = ordered_models[:stage_index]
    annotations = known_annotations(values, known, item_id) + derived_annotations(
        ordered_models,
        values,
        known,
        target,
        stage_index,
    )
    annotations = apply_annotation_layout_overrides(item_id, annotations)
    current_model = visible_models[-1] if visible_models else None
    solution_id = f"question_bank.auxiliary50.{item_key}.{stage}"
    if current_model is None:
        caption = "蓝字标出题目给出的两组比；先完成辅助线。"
    elif stage == "model1":
        additions = staged_model_share_additions(ordered_models, values, known, target)[0]
        if len(additions) == 2:
            caption = f"解第一组{current_model['shape']}：两条边都未标，补出一对红色份数。"
        elif len(additions) == 1:
            segment, share = additions[0]
            segment = "PD" if segment == "DP" else segment
            caption = (
                f"解第一组{current_model['shape']}：沿用已标边，只新增"
                f" {segment}={fraction_plain(share)}份。"
            )
        else:
            caption = f"解第一组{current_model['shape']}：两条对应边已有份数，不重复标注。"
    else:
        additions = staged_model_share_additions(ordered_models, values, known, target)[1]
        if additions:
            additions_text = "、".join(
                f"{('PD' if segment == 'DP' else segment)}={fraction_plain(share)}份"
                for segment, share in additions
            )
            caption = (
                f"解第二组{current_model['shape']}：已有份数保持不变；本步补出"
                f"绿色 {additions_text}，所求两边均已标清。"
            )
        else:
            caption = f"解第二组{current_model['shape']}：两条对应边已有份数，不重复标注。"
    return {
        "slot_id": solution_id,
        "diagram_ref": solution_id,
        "variant": "solution",
        "disclosure_policy": "annotated",
        "reuse_geometry_from": prompt_id,
        "required": True,
        "on_failure": "fail_assignment",
        "placement": "diagram_col",
        "layout_role": "solution_annotation",
        "display_profile": "worksheet_geometry_sidecar",
        "caption": caption,
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "engine_options": {
            "scene_payload": solution_scene(route, annotations, current_model),
            # model2 reuses the exact model1 geometry; keeping the same solver
            # seed prevents an under-constrained auxiliary point from drifting
            # merely because another text annotation was added.
            "seed": 727000 + int(item_id[1:]) * 10 + min(stage_index, 1),
        },
        "teaching_intent": "practice_solution",
        "problem_context": {
            "stem_latex": stem,
            "source_problem_text": f"复用本题 prompt 的全部点位，只新增 F：{route['description']}。蓝字始终标出题设两组比；第一组模型新增红色份数，第二组模型保留前图并新增绿色份数；已经标过的边不换数、不换色。",
        },
        "semantic_constraints": {
            "given_objects": ["A", "B", "C", "D", "E", "P", "F"],
            "given_constraints": [
                f"reuse the complete geometry from {prompt_id}",
                route["description"],
            ],
            "solution_allowed_annotations": [
                "the auxiliary line",
                "one parallel marker",
                "blue given-ratio share labels",
                "red first-model corresponding-side share labels",
                "green second-model corresponding-side share labels",
            ],
        },
        "visual_requirements": {
            "required_visible_annotations": {
                "markers": [{"type": "parallel", "segments": [[p0, p1], [q0, q1]]}],
                "texts": deepcopy(annotations),
            }
        },
    }


def author_item(
    item_index: int,
    values: dict[str, Fraction],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    item_id = f"Q{item_index + 1:03d}"
    known, target = ROUTES[item_index]
    first_known, second_known = known
    first_a, first_b = RATIO_SEGMENTS[first_known]
    second_a, second_b = RATIO_SEGMENTS[second_known]
    target_first, target_second = RATIO_SEGMENTS[target]
    first_condition = rf"{first_a}:{first_b}={ratio_text(values[first_known])}"
    second_condition = rf"{second_a}:{second_b}={ratio_text(values[second_known])}"
    answer_value = values[target]
    answer = rf"${target_first}:{target_second}={ratio_text(answer_value)}$。"
    title = f"由两组对应边比求 {target_first}:{target_second}"
    stem = (
        r"如图，点 $D$ 在线段 $BC$ 上，点 $E$ 在线段 $AC$ 上，$AD$ 与 $BE$ 交于点 $P$。已知 "
        + rf"${first_condition}$，${second_condition}$，求 ${target_first}:{target_second}$。"
    )
    route = auxiliary_route(set(known) | {target})
    models = list(route["models"])
    if models[0]["anchor"] not in known:
        models.reverse()
    staged_additions = staged_model_share_additions(models, values, known, target)

    def model_step_content(model: dict[str, Any], stage_index: int) -> str:
        output_first, output_second = model["output"]
        output_ratio = model_output_ratio(model, values)
        similarity = f"${model['triangles']}$"
        additions = staged_additions[stage_index]
        if stage_index == 1 and additions:
            additions_text = "，".join(
                f"${('PD' if segment == 'DP' else segment)}={fraction_latex(share)}$ 份"
                for segment, share in additions
            )
            return (
                f"由蓝色已知比解 {model['shape']} {similarity}。保留前一步全部份数，"
                f"本步用绿色补出 {additions_text}，使所求两边的份数同时显示。"
            )
        if len(additions) == 2:
            return (
                f"由蓝色已知比解 {model['shape']} {similarity}，"
                f"得红色 ${output_first}:{output_second}={ratio_text(output_ratio)}$。"
            )
        if len(additions) == 1:
            new_segment, new_share = additions[0]
            new_segment = "PD" if new_segment == "DP" else new_segment
            return (
                f"由蓝色已知比解 {model['shape']} {similarity}。沿用图中已有份数，"
                f"只新增红色 ${new_segment}={fraction_latex(new_share)}$ 份。"
            )
        return (
            f"由 {model['shape']} {similarity} 读取图中已有份数；"
            "两条对应边都已标过，本步不重复标注。"
        )

    first_model, second_model = models
    steps = [
        {
            "title": "作辅助线",
            "content": f"{route['description']}。蓝字标出题目给出的两组比。",
        },
        {
            "title": f"解第一组{first_model['shape']}",
            "content": model_step_content(first_model, 0),
        },
        {
            "title": f"解第二组{second_model['shape']}",
            "content": model_step_content(second_model, 1),
        },
        {
            "title": "比较份数，写出答案",
            "content": f"直接比较图中所求两条边的份数并化简，因此 {answer}",
        },
    ]

    prompt_slot = diagram_slot(item_id, stem, values, known, target, stage="prompt")
    steps[0]["diagram_slot"] = diagram_slot(
        item_id, stem, values, known, target, stage="helper", ordered_models=models
    )
    steps[1]["diagram_slot"] = diagram_slot(
        item_id, stem, values, known, target, stage="model1", ordered_models=models
    )
    steps[2]["diagram_slot"] = diagram_slot(
        item_id, stem, values, known, target, stage="model2", ordered_models=models
    )
    block = {
        "type": "problem",
        "id": item_id,
        "points": 10,
        "label": title,
        "stem_latex": stem,
        "diagram_slot": prompt_slot,
        "answer_space": {
            "type": "steps",
            "height": "36mm",
            "step_count": 4,
        },
        "answer": answer,
        "explanation": "第一组相似标共同边，第二组沿用它，只给另一条目标边新增份数。",
        "solution_steps": steps,
        "teaching": {
            "teaching_goal": "由两组对应边整数比求第三组整数比",
            "source_relations": ["two-ratio-auxiliary-line", "two-similar-triangles"],
            "expected_blocker": "只找到一组相似，或把分段比和整段比混用。",
            "entry_point": "identify_three_ratio_lines",
            "scaffold_level": "medium",
            "variation_depth": variation(item_index),
            "complexity_note": "题干中的四个比数均为 1 到 5 的互质整数；不出现分数、长度、面积或角度。",
            "upgrade_rule": "先写出两组相似中的共同中间边，再消元求第三组。",
            "fallback_move": "在 AC、AD、BE、BC 四条比例线上圈出两条已知线和一条所求线。",
            "number_policy": "each given ratio uses coprime integers from 1 through 5",
        },
    }
    slot = {
        "id": item_id,
        "difficulty": difficulty(item_index),
        "training_action": "由两组对应边整数比求第三组整数比",
        "question_type": "problem",
        "variation_dimension": variation(item_index),
        "diagram_requirement": "prompt_and_solution",
        "number_policy": {
            "allowed_components": [1, 2, 3, 4, 5],
            "coprime_required": True,
            "values": {key: ratio_text(value) for key, value in values.items()},
        },
        "known_ratios": list(known),
        "target_ratio": target,
        "target_form": "ratio",
    }
    item = {
        "id": item_id,
        "title": title,
        "question_type": "problem",
        "difficulty": difficulty(item_index),
        "skill_tags": ["比例辅助线", "两组相似", "整数比", "求比例"],
        "variation_dimension": variation(item_index),
        "diagram_requirement": "prompt_and_solution",
        "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
        "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
        "weight": 1.0,
        "enabled": True,
    }
    return block, slot, item


def assignment(item_id: str, block: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {
            "title": f"比例辅助线两组整数比 · {item_id} · 教师版",
            "grade": "八年级",
            "subject": "数学",
            "total_points": 10,
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {
                "explanation": SOURCE_EXPLANATION,
                "diagram_policy": "每题独立 prompt/solution；新三阶段流程逐图审核",
            },
        },
        "render": {
            "template": "exam-zh-practice",
            "paper_size": "a4paper",
            "answer_key_position": "after_page_break",
        },
        "sections": [
            {
                "id": "question",
                "title": "专题题",
                "type": "practice",
                "visibility": "both",
                "blocks": [block],
            }
        ],
    }


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    cases = select_cases()
    slots: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for index, values in enumerate(cases):
        block, slot, item = author_item(index, values)
        item_id = item["id"]
        write_yaml(output / "items" / item_id / "teacher.plan.assignment.yaml", assignment(item_id, block))
        slots.append(slot)
        items.append(item)

    write_yaml(
        output / "coverage-plan.yaml",
        {
            "topic": "比例辅助线两组整数比",
            "source_explanation": SOURCE_EXPLANATION,
            "target_count": 50,
            "difficulty_distribution": {"foundation": 25, "standard": 25, "challenge": 0},
            "target_form_distribution": {"ratio": 50, "length": 0},
            "number_policy": "题干中的每个比只使用 1 到 5 的两个互质整数，包括 1；题干不出现分数或长度。",
            "design_note": "50 题只改变两组已知比例线、所求第三组比例线和小整数，不引入其他题型。",
            "slots": slots,
        },
    )
    write_yaml(
        output / "question-bank.yaml",
        {
            "schema": "math_topic_question_bank/v1",
            "bank": {
                "id": "auxiliary-two-small-integer-ratios-50-2026-07-17",
                "topic": "比例辅助线两组整数比",
                "grade": "八年级",
                "subject": "数学",
                "source_explanation": SOURCE_EXPLANATION,
                "status": "plan",
                "target_count": 50,
            },
            "items": items,
        },
    )
    print(f"authored {len(items)} reviewed plan items at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
