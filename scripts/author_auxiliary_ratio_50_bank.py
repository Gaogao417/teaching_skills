#!/usr/bin/env python3
"""Author the 50-slot two-ratio auxiliary-line question bank plans.

This script is an authoring scaffold only: it freezes a reviewed coverage plan
and serializes the main Agent's approved single-item plan assignments.  Every
given ratio uses coprime integers from 1 through 5.  It does not call Wolfram,
compile TikZ, run an audit, resolve an assignment, or mark the bank ready.
"""

from __future__ import annotations

import argparse
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
        },
        # Missing BC ratio: AC, AD and BE surround triangle AEP.
        "w": {
            "description": "过 A 作 AF 平行 EP，交直线 BC 于 F",
            "f_region": ("B", "C"),
            "parallel": (("A", "F"), ("E", "P")),
            "f_placement": "below left",
        },
        # Missing AD ratio: AC, BE and BC surround triangle ECB.
        "y": {
            "description": "过 E 作 EF 平行 CB，交直线 AD 于 F",
            "f_region": ("A", "D"),
            "parallel": (("E", "F"), ("C", "B")),
            "f_placement": "above left",
        },
        # Missing AC ratio: AD, BE and BC surround triangle PDB.
        "x": {
            "description": "过 P 作 PF 平行 DB，交直线 AC 于 F",
            "f_region": ("A", "C"),
            "parallel": (("P", "F"), ("D", "B")),
            "f_placement": "right",
        },
    }
    return routes[missing]


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


def solution_scene(route: dict[str, Any]) -> dict[str, Any]:
    f0, f1 = route["f_region"]
    (p0, p1), (q0, q1) = route["parallel"]
    spec = base_diagram_spec()
    spec["segments"].append([p0, p1])
    spec["markers"] = [
        {"type": "parallel", "segments": [[p0, p1], [q0, q1]]}
    ]
    spec["labels"]["F"] = {"text": "F", "placement": route["f_placement"]}
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
    solution: bool,
) -> dict[str, Any]:
    item_key = item_id.lower()
    prompt_id = f"question_bank.auxiliary50.{item_key}.prompt"
    if not solution:
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
            "caption": f"{item_id} 原题图：只显示原始构型与点名。",
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
    solution_id = f"question_bank.auxiliary50.{item_key}.solution"
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
        "caption": f"{item_id} 解答图：{route['description']}。",
        "engine": "geometric_scene",
        "diagram_kind": "synthetic_geometry",
        "engine_options": {"scene_payload": solution_scene(route), "seed": 727000 + int(item_id[1:])},
        "teaching_intent": "practice_solution",
        "problem_context": {
            "stem_latex": stem,
            "source_problem_text": f"复用本题 prompt 的全部点位，只新增 F：{route['description']}。显示一组平行标记，不写最终答案。",
        },
        "semantic_constraints": {
            "given_objects": ["A", "B", "C", "D", "E", "P", "F"],
            "given_constraints": [
                f"reuse the complete geometry from {prompt_id}",
                route["description"],
            ],
            "solution_allowed_annotations": ["the auxiliary line", "one parallel marker"],
        },
        "visual_requirements": {
            "required_visible_annotations": {
                "markers": [{"type": "parallel", "segments": [[p0, p1], [q0, q1]]}],
                "texts": [],
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
        r"如图，在 $\triangle ABC$ 中，点 $D$ 在线段 $BC$ 上，点 $E$ 在线段 $AC$ 上，"
        r"线段 $AD$ 与 $BE$ 交于点 $P$。已知 "
        + rf"${first_condition}$，${second_condition}$，求 ${target_first}:{target_second}$。"
    )
    relation = relation_for(known)
    substitution = r",\ ".join(
        rf"{key}={fraction_latex(values[key])}" for key in known
    )
    target_result = fraction_latex(values[target])
    steps = [
        {
            "title": "找三条比例线并作辅助线",
            "content": "把两组已知条件与所求量所在的三条直线围成三角形，按讲解规则作唯一的平行辅助线，得到两组相似三角形。",
        },
        {
            "title": "统一记号并列关系",
            "content": rf"记 $x=AE/EC$、$w=BD/DC$、$y=AP/PD$、$z=BP/PE$。本题可用 ${relation}$。",
        },
        {
            "title": "代入两个整数比",
            "content": rf"由题意得到 ${substitution}$，化简得 ${target}={target_result}$。",
        },
        {"title": "写成最简整数比", "content": f"约去公因数，得到 {answer}"},
    ]

    prompt_slot = diagram_slot(item_id, stem, values, known, target, solution=False)
    solution_slot = diagram_slot(item_id, stem, values, known, target, solution=True)
    block = {
        "type": "problem",
        "id": item_id,
        "points": 10,
        "label": title,
        "stem_latex": stem,
        "diagram_slot": prompt_slot,
        "answer_space": {
            "type": "steps",
            "height": "48mm",
            "step_count": 4,
            "diagram_slot": solution_slot,
        },
        "answer": answer,
        "explanation": "两组已知整数比先统一为 x、w、y、z 的关系，再求第三组并写成最简整数比。",
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
