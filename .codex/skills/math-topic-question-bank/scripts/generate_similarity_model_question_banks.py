#!/usr/bin/env python3
"""Rebuild three 50-item similarity banks from clean integer/radical data."""

from __future__ import annotations

import argparse
import copy
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

from derive_student_assignment import derive as derive_student_assignment
from question_bank_repo import find_repo_root
from similarity_triangle_contracts import (
    SimilarityTriangleDatabase,
    SimilarityTriangleEntry,
)
from training_number_contracts import ExactLength, TrainingNumberEntry
from training_number_review_state import load_database, load_review


ROOT = find_repo_root()


NUMBER_DATABASE = ROOT / ".codex/skills/math-topic-question-bank/data/training-number-database.yaml"
NUMBER_REVIEW = ROOT / ".codex/skills/math-topic-question-bank/data/training-number-review.yaml"
GEOMETRY_DATABASE = ROOT / ".codex/skills/math-topic-question-bank/data/similarity-triangle-database.yaml"
NUMBER_DATABASE_ID = "question-bank-training-numbers"
GEOMETRY_DATABASE_ID = "similarity-triangle-realizations"

SIMILARITY_FAMILY = "noncoprime_radicand_pairs"
FAMILIES = (SIMILARITY_FAMILY,)
FAMILY_LABELS = {
    SIMILARITY_FAMILY: "整数与整系数根式",
}


@dataclass(frozen=True)
class ModelSpec:
    key: str
    bank_dir: str
    bank_id: str
    topic: str
    source_explanation: str
    similarity_statement: str
    pairs: tuple[tuple[str, str], ...]
    allowed_pair_routes: tuple[tuple[int, int], ...]
    base_stem: str
    scene_points: tuple[str, ...]
    anchor_points: tuple[str, ...]
    constructed_points: tuple[str, ...]
    scene_constraints: tuple[str, ...]
    segments: tuple[tuple[str, str], ...]
    labels: dict[str, str]
    caption: str
    given_constraints: tuple[str, ...]


MODELS = (
    ModelSpec(
        key="reverse_a",
        bank_dir="2026-07-16-反A形相似",
        bank_id="reverse_a-similarity-2026-07-16",
        topic="反A形相似",
        source_explanation="../../专题/2026-07-14-反A形相似求第四边/02-student-explanation.resolved.assignment.yaml",
        similarity_statement=r"\triangle PAB\sim\triangle PDC",
        pairs=(("PA", "PD"), ("PB", "PC"), ("AB", "DC")),
        allowed_pair_routes=((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)),
        base_stem=r"如图，$\angle PAB=\angle PDC$。",
        scene_points=("P", "A", "B", "C", "D"),
        anchor_points=("P", "C", "D"),
        constructed_points=("A", "B"),
        scene_constraints=(
            "Element[A, Line[{P, C}]]",
            "Element[B, Line[{P, D}]]",
            "EuclideanDistance[P, A] > 0",
            "EuclideanDistance[A, C] > 0",
            "EuclideanDistance[P, B] > 0",
            "EuclideanDistance[B, D] > 0",
            "EuclideanDistance[P, C] == EuclideanDistance[P, A] + EuclideanDistance[A, C]",
            "EuclideanDistance[P, D] == EuclideanDistance[P, B] + EuclideanDistance[B, D]",
            "PlanarAngle[{P, A, B}] == PlanarAngle[{P, D, C}]",
            'GeometricAssertion[Line[{P, D}], "Horizontal"]',
            'GeometricAssertion[Line[{P, D}], "Rightward"]',
            'GeometricAssertion[{P, D, C}, "Counterclockwise"]',
        ),
        segments=(("P", "C"), ("P", "D"), ("A", "B"), ("C", "D")),
        labels={"P": "below left", "A": "above left", "B": "below", "C": "above right", "D": "below right"},
        caption="沿题设等角的顶点顺序，找出两组三角形的对应边。",
        given_constraints=(
            "A lies strictly between P and C",
            "B lies strictly between P and D",
            "angle PAB equals angle PDC",
        ),
    ),
    ModelSpec(
        key="butterfly",
        bank_dir="2026-07-16-蝶形相似",
        bank_id="butterfly-similarity-2026-07-16",
        topic="蝶形相似",
        source_explanation="../../专题/2026-07-14-蝶形相似求第四边/02-student-explanation.resolved.assignment.yaml",
        similarity_statement=r"\triangle AOC\sim\triangle DOB",
        pairs=(("AO", "OD"), ("OC", "OB"), ("AC", "DB")),
        allowed_pair_routes=((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)),
        base_stem=r"如图，$\angle OAC=\angle ODB$。",
        scene_points=("A", "O", "B", "C", "D"),
        anchor_points=("A", "B", "C", "D"),
        constructed_points=("O",),
        scene_constraints=(
            "Element[O, Line[{A, B}]]",
            "Element[O, Line[{C, D}]]",
            "EuclideanDistance[A, O] > 0",
            "EuclideanDistance[O, B] > 0",
            "EuclideanDistance[C, O] > 0",
            "EuclideanDistance[O, D] > 0",
            "EuclideanDistance[A, B] == EuclideanDistance[A, O] + EuclideanDistance[O, B]",
            "EuclideanDistance[C, D] == EuclideanDistance[C, O] + EuclideanDistance[O, D]",
            "PlanarAngle[{O, A, C}] == PlanarAngle[{O, D, B}]",
            'GeometricAssertion[Line[{A, B}], "Horizontal"]',
            'GeometricAssertion[Line[{A, B}], "Rightward"]',
            'GeometricAssertion[{A, B, C}, "Counterclockwise"]',
        ),
        segments=(("A", "B"), ("C", "D"), ("A", "C"), ("D", "B")),
        labels={"A": "below left", "O": "below", "B": "below right", "C": "above right", "D": "below right"},
        caption="先用对顶角补齐第二组等角，再按顶点顺序配边。",
        given_constraints=(
            "A, O, B are collinear with O strictly between A and B",
            "C, O, D are collinear with O strictly between C and D",
            "angle OAC equals angle ODB",
        ),
    ),
    ModelSpec(
        key="nested",
        bank_dir="2026-07-16-子母型相似",
        bank_id="nested-similarity-2026-07-16",
        topic="子母型相似",
        source_explanation="../../专题/2026-07-14-子母型相似比与对应边/02-student-explanation.resolved.assignment.yaml",
        similarity_statement=r"\triangle ABD\sim\triangle ACB",
        pairs=(("AB", "AC"), ("AD", "AB"), ("BD", "BC")),
        allowed_pair_routes=((0, 2), (2, 0)),
        base_stem=r"如图，在 $\triangle ABC$ 中，$\angle ABD=\angle ACB$。",
        scene_points=("A", "B", "C", "D"),
        anchor_points=("A", "B", "C"),
        constructed_points=("D",),
        scene_constraints=(
            "Element[D, Line[{A, C}]]",
            "EuclideanDistance[A, D] > 0",
            "EuclideanDistance[D, C] > 0",
            "EuclideanDistance[A, C] == EuclideanDistance[A, D] + EuclideanDistance[D, C]",
            "PlanarAngle[{A, B, D}] == PlanarAngle[{A, C, B}]",
            'GeometricAssertion[Line[{A, C}], "Horizontal"]',
            'GeometricAssertion[Line[{A, C}], "Rightward"]',
            'GeometricAssertion[{A, C, B}, "Counterclockwise"]',
        ),
        segments=(("A", "B"), ("B", "C"), ("C", "A"), ("B", "D")),
        labels={"A": "below left", "B": "above", "C": "below right", "D": "below"},
        caption="先确认对应边，再判断题中的线段是否属于相似三角形。",
        given_constraints=(
            "D lies strictly between A and C",
            "angle ABD equals angle ACB",
        ),
    ),
)


DIFFICULTY_SEQUENCE = (
    ["foundation"] * 16
    + ["standard"] * 20
    + ["challenge"] * 14
)
def exact_latex(value: ExactLength) -> str:
    return value.latex


def fraction_latex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\frac{{{value.numerator}}}{{{value.denominator}}}"


def radical_latex(coefficient: Fraction, radicand: int) -> str:
    if radicand == 1:
        return fraction_latex(coefficient)
    if coefficient == 1:
        return rf"\sqrt{{{radicand}}}"
    return rf"{fraction_latex(coefficient)}\sqrt{{{radicand}}}"


def nested_lengths(realization: SimilarityTriangleEntry) -> dict[str, tuple[Fraction, int, str]]:
    """Return the physical AB, AD, AC and CD lengths in a nested realization."""
    ab = realization.small_triangle_sides[0]
    ad = realization.small_triangle_sides[1]
    large_by_pair = {
        realization.source_pair_index: realization.target_values[0],
        realization.target_pair_index: realization.target_values[1],
    }
    ac = large_by_pair[0]
    if ad.radicand != ac.radicand:
        raise RuntimeError(f"{realization.id}: nested AD and AC must use the same radical basis")
    cd_coefficient = ac.coefficient_fraction - ad.coefficient_fraction
    if cd_coefficient <= 0:
        raise RuntimeError(f"{realization.id}: nested CD must be positive")
    return {
        "AB": (ab.coefficient_fraction, ab.radicand, ab.latex),
        "AD": (ad.coefficient_fraction, ad.radicand, ad.latex),
        "AC": (ac.coefficient_fraction, ac.radicand, ac.latex),
        "CD": (cd_coefficient, ac.radicand, radical_latex(cd_coefficient, ac.radicand)),
    }


def exact_wl(value: ExactLength) -> str:
    coefficient = str(value.coefficient_fraction)
    if value.radicand == 1:
        return coefficient
    return f"({coefficient}) Sqrt[{value.radicand}]"


def distance_constraint(segment: str, value: ExactLength) -> str:
    return f"EuclideanDistance[{segment[0]}, {segment[1]}] == {exact_wl(value)}"


def load_sources() -> tuple[dict[str, TrainingNumberEntry], list[SimilarityTriangleEntry]]:
    database = load_database(NUMBER_DATABASE)
    review = load_review(NUMBER_REVIEW, database)
    disabled = set(review.disabled_entry_ids)
    numbers = {
        entry.id: entry
        for entry in database.entries_by_id().values()
        if entry.family == SIMILARITY_FAMILY
        and entry.parameters.get("similarity_eligible", False)
        and entry.id not in disabled
    }
    geometry_payload = yaml.safe_load(GEOMETRY_DATABASE.read_text(encoding="utf-8"))
    geometries = SimilarityTriangleDatabase.model_validate(geometry_payload).entries
    geometries = [entry for entry in geometries if entry.number_entry_id in numbers]
    return numbers, geometries


def ratio_signature(entry: TrainingNumberEntry) -> tuple[int, int]:
    squared = sorted(value.squared for value in entry.values)
    ratio = squared[1] / squared[0]
    return ratio.numerator, ratio.denominator


def route_quotas(model: ModelSpec) -> list[tuple[int, int]]:
    routes = model.allowed_pair_routes
    if len(routes) == 2:
        counts = (25, 25)
    else:
        counts = (9, 9, 8, 8, 8, 8)
    return [route for route, count in zip(routes, counts, strict=True) for _ in range(count)]


def select_realizations(
    model: ModelSpec,
    numbers: dict[str, TrainingNumberEntry],
    geometries: list[SimilarityTriangleEntry],
    seed: int,
) -> list[SimilarityTriangleEntry]:
    rng = random.Random(seed)
    by_route: dict[tuple[int, int], dict[str, SimilarityTriangleEntry]] = defaultdict(dict)
    for geometry in geometries:
        if geometry.model != model.key:
            continue
        route = (geometry.source_pair_index, geometry.target_pair_index)
        current = by_route[route].get(geometry.number_entry_id)
        quality = lambda item: (
            item.quality.minimum_angle_deg,
            item.quality.minimum_relative_side_gap,
            item.quality.inradius_circumradius_ratio,
            item.quality.minimum_height_perimeter_ratio,
            -item.known_integer,
        )
        if current is None or quality(geometry) > quality(current):
            by_route[route][geometry.number_entry_id] = geometry

    route_remaining = Counter(route_quotas(model))
    route_candidates: dict[tuple[int, int], list[SimilarityTriangleEntry]] = {}
    for route, mapping in by_route.items():
        candidates = list(mapping.values())
        rng.shuffle(candidates)
        candidates.sort(
            key=lambda item: (
                item.quality.minimum_angle_deg,
                item.quality.minimum_relative_side_gap,
                item.quality.inradius_circumradius_ratio,
                item.quality.minimum_height_perimeter_ratio,
            ),
            reverse=True,
        )
        route_candidates[route] = candidates

    source = ("source",)
    sink = ("sink",)
    adjacency: dict[tuple[Any, ...], list[tuple[Any, ...]]] = defaultdict(list)
    capacity: dict[tuple[tuple[Any, ...], tuple[Any, ...]], int] = {}

    def add_edge(left: tuple[Any, ...], right: tuple[Any, ...], amount: int) -> None:
        adjacency[left].append(right)
        adjacency[right].append(left)
        capacity[(left, right)] = amount
        capacity[(right, left)] = 0

    signature_entries: dict[tuple[int, int], set[str]] = defaultdict(set)
    entry_routes: dict[str, set[tuple[int, int]]] = defaultdict(set)
    edge_geometry: dict[tuple[str, tuple[int, int]], SimilarityTriangleEntry] = {}
    for route, candidates in route_candidates.items():
        for candidate in candidates:
            entry_id = candidate.number_entry_id
            signature_entries[ratio_signature(numbers[entry_id])].add(entry_id)
            entry_routes[entry_id].add(route)
            edge_geometry[(entry_id, route)] = candidate

    for signature in sorted(signature_entries):
        signature_node = ("signature", *signature)
        add_edge(source, signature_node, 16)
        entry_ids = sorted(
            signature_entries[signature],
            key=lambda entry_id: (len(entry_routes[entry_id]), entry_id),
        )
        for entry_id in entry_ids:
            add_edge(signature_node, ("entry", entry_id), 1)
    for entry_id, routes in sorted(entry_routes.items()):
        entry_node = ("entry", entry_id)
        for route in sorted(routes, key=lambda value: (len(route_candidates[value]), value)):
            add_edge(entry_node, ("route", *route), 1)
    for route, quota in sorted(route_remaining.items()):
        add_edge(("route", *route), sink, quota)

    flow = 0
    while True:
        parent: dict[tuple[Any, ...], tuple[Any, ...] | None] = {source: None}
        queue = [source]
        for node in queue:
            for neighbor in adjacency[node]:
                if neighbor not in parent and capacity[(node, neighbor)] > 0:
                    parent[neighbor] = node
                    queue.append(neighbor)
                    if neighbor == sink:
                        break
            if sink in parent:
                break
        if sink not in parent:
            break
        node = sink
        while parent[node] is not None:
            previous = parent[node]
            capacity[(previous, node)] -= 1
            capacity[(node, previous)] += 1
            node = previous
        flow += 1

    if flow != 50:
        raise RuntimeError(f"{model.key}: clean-number max flow reached only {flow}/50")
    selected = [
        geometry
        for (entry_id, route), geometry in edge_geometry.items()
        if capacity[(("route", *route), ("entry", entry_id))] == 1
    ]
    if len(selected) != 50:
        raise RuntimeError(f"{model.key}: expected 50 selected flow edges, got {len(selected)}")
    rng.shuffle(selected)
    return selected


def difficulty_for_index(index: int) -> str:
    return DIFFICULTY_SEQUENCE[index]


def scaffold_text(difficulty: str, unknown: str) -> tuple[str, str, str, str]:
    if difficulty == "foundation":
        return (
            "求指定边",
            "changed_numbers",
            "用相似对应边直接求指定边",
            rf"求 ${unknown}$ 的长。",
        )
    if difficulty == "standard":
        return (
            "求指定边",
            "changed_representation",
            "独立确定对应关系并求指定边",
            rf"求 ${unknown}$ 的长。",
        )
    return (
        "判断可求边",
        "partially_hidden",
        "由三条已知边判断唯一可求边并计算",
        "判断还可以求出哪条边，并求出它的长度。",
    )


def diagram_slot(
    model: ModelSpec,
    item_id: str,
    stem: str,
    realization: SimilarityTriangleEntry,
    seed: int,
) -> dict[str, Any]:
    first_pair = model.pairs[realization.source_pair_index]
    second_pair = model.pairs[realization.target_pair_index]
    known_segment = first_pair[1] if realization.known_target_position == "small" else second_pair[1]
    known_value = realization.target_values[0] if realization.known_target_position == "small" else realization.target_values[1]
    constraints = list(model.scene_constraints)
    constraints.extend(
        [
            distance_constraint(first_pair[0], realization.source_values[0]),
            distance_constraint(second_pair[0], realization.source_values[1]),
            distance_constraint(known_segment, known_value),
        ]
    )
    # The realization database already records Wolfram-verified quality metrics.
    # Repeating angle/radius/height inequalities in every render makes
    # GeometricScene solve the same expensive audit again.  Only the frozen
    # third-side equality is needed to reproduce the verified triangle shape.
    frozen_side_constraints = [
        constraint
        for constraint in realization.scene_constraints
        if constraint.startswith("EuclideanDistance[")
    ]
    constraints.extend(frozen_side_constraints[:1])
    points = ", ".join(model.scene_points)
    scene_code = f"GeometricScene[{{{points}}}, {{{', '.join(constraints)}}}]"
    slot_id = f"question_bank.{model.key}.v2.{item_id.lower()}.prompt"
    return {
        "slot_id": slot_id,
        "diagram_ref": slot_id,
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
            "scene_payload": {
                "scene_code": scene_code,
                "points": list(model.scene_points),
                "point_roles": {
                    "anchors": list(model.anchor_points),
                    "constructed": list(model.constructed_points),
                    "auxiliary": [],
                },
                "diagram_spec": {
                    "type": "synthetic_geometry",
                    "segments": [{"from": a, "to": b} for a, b in model.segments],
                    "markers": [],
                    "labels": {point: {"text": point, "placement": placement} for point, placement in model.labels.items()},
                    "constraints": list(model.given_constraints),
                    "teaching_focus": ["write the exact side ratio", "match vertices before matching sides"],
                },
                "rationale": "数库提供同一基准三角形的两条整数或整系数根式边；另一三角形冻结一条整数对应边。数库边最大素因数不超过 5、边长比不超过根号 3；未知对应边只要求精确派生，不限制为整数。构型实例已通过 Wolfram 质量门槛，图中不标数值。",
                "model_used": "deterministic-similarity-realization-database-v1",
                "model_attempts": [],
            },
            "seed": seed,
        },
        "teaching_intent": "practice_prompt",
        "problem_context": {
            "stem_latex": stem,
            "source_problem_text": "逐题独立生成干净题图。图中只保留点名和必要标记，不标边长数值、相似结论、比例式、化简过程或答案。",
        },
        "semantic_constraints": {
            "given_objects": list(model.scene_points),
            "given_constraints": list(model.given_constraints)
            + [
                "one reviewed integer/radical pair supplies two sides of the same base triangle",
                "one corresponding side in the other triangle is an integer",
                "the two database-supplied base-triangle sides have no fractional coefficient and no prime factor above five",
                "the derived unknown corresponding side may be any positive exact rational or radical value",
            ],
            "clean_forbidden": [
                "do not show the final answer",
                "do not label the derived triangle similarity",
                "do not draw numeric side-length labels",
                "do not show ratio simplification",
                "do not add auxiliary lines or solution annotations",
            ],
        },
    }


def make_problem(
    model: ModelSpec,
    item_id: str,
    number_entry: TrainingNumberEntry,
    realization: SimilarityTriangleEntry,
    difficulty: str,
    item_index: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    first_pair = model.pairs[realization.source_pair_index]
    second_pair = model.pairs[realization.target_pair_index]
    source_pair = (first_pair[0], second_pair[0])
    source_small = realization.source_values[0].latex
    source_large = realization.source_values[1].latex
    if realization.known_target_position == "small":
        known_name = first_pair[1]
        unknown_name = second_pair[1]
    else:
        known_name = second_pair[1]
        unknown_name = first_pair[1]
    title, variation, training_action, ending = scaffold_text(difficulty, unknown_name)
    knowns = (
        rf"${source_pair[0]}={source_small}$，${source_pair[1]}={source_large}$，"
        rf"${known_name}={realization.known_integer}$"
    )
    stem = f"{model.base_stem}\n\n已知 {knowns}。{ending}"
    ratio_equation = (
        rf"\dfrac{{{first_pair[0]}}}{{{first_pair[1]}}}="
        rf"\dfrac{{{second_pair[0]}}}{{{second_pair[1]}}}"
    )
    answer = rf"${unknown_name}={exact_latex(realization.unknown_value)}$。"
    solution_steps = [
        {
            "title": "整理已知边长比",
            "content": rf"题中给出的两边均为整数或整系数根式，因此可直接写成 ${source_pair[0]}:{source_pair[1]}={source_small}:{source_large}$。",
        },
        {
            "title": "由等角判相似",
            "content": f"由题设等角和构型自带的另一组等角，得 ${model.similarity_statement}$。",
        },
        {
            "title": "按顶点确认对应边",
            "content": "三组小三角形边与大三角形边依次为：" + "，".join(rf"${a}\leftrightarrow {b}$" for a, b in model.pairs) + "。",
        },
        {
            "title": "保持比例方向一致",
            "content": rf"统一保持两组对应边的方向，可列 ${ratio_equation}$，再代入 ${known_name}={realization.known_integer}$。",
        },
        {
            "title": "求值并验算",
            "content": rf"解得 ${unknown_name}={exact_latex(realization.unknown_value)}$；代回后两组对应边的比完全相等。",
        },
    ]
    number_selection = {
        "database_id": NUMBER_DATABASE_ID,
        "family_id": number_entry.family,
        "entry_id": number_entry.id,
        "values_latex": [value.latex for value in realization.source_values],
        "squared_ratio": list(ratio_signature(number_entry)),
        "largest_prime_factor_max": 5,
        "max_ratio": "sqrt(3)",
        "source_fractional_coefficients_allowed": False,
        "unknown_value_restrictions": "none_beyond_positive_exact_value",
    }
    geometry_selection = {
        "database_id": GEOMETRY_DATABASE_ID,
        "entry_id": realization.id,
        "model": realization.model,
        "source_pair_index": realization.source_pair_index,
        "target_pair_index": realization.target_pair_index,
        "known_target_position": realization.known_target_position,
        "number_side_indices": [realization.source_pair_index, realization.target_pair_index],
        "known_correspondence_index": (
            realization.source_pair_index
            if realization.known_target_position == "small"
            else realization.target_pair_index
        ),
        "unknown_correspondence_index": (
            realization.target_pair_index
            if realization.known_target_position == "small"
            else realization.source_pair_index
        ),
    }
    block = {
        "type": "problem",
        "id": item_id,
        "points": 10,
        "label": title,
        "stem_latex": stem,
        "answer_space": {"type": "steps", "height": "54mm", "step_count": 5},
        "answer": answer,
        "clue": f"使用{FAMILY_LABELS[number_entry.family]}写出精确比例，再完成相似判定、对应和计算。",
        "solution_steps": solution_steps,
        "teaching": {
            "teaching_goal": training_action,
            "source_relations": [f"explanation:{model.key}", "similar_triangles_corresponding_sides", "exact_integer_radical_ratio"],
            "expected_blocker": "两组比例的对应顺序不一致，或根式乘除没有保持精确形式。",
            "entry_point": "exact_ratio_then_equal_angles_to_similarity",
            "scaffold_level": "high" if difficulty == "foundation" else "medium" if difficulty == "standard" else "low",
            "variation_depth": variation,
            "complexity_note": "数库提供同一基准三角形的两条整数/整系数根式边；另一三角形只给一条整数对应边。数库边受素因数与比例限制，精确派生的未知边不限制为整数或小素因数。",
            "upgrade_rule": "能在题干不提示时主动写出精确边长比并保持对应方向。",
            "fallback_move": "先圈出一组完整对应边，再用同一方向写另一组对应边。",
            "number_selection": number_selection,
            "geometry_selection": geometry_selection,
        },
        "diagram_slot": diagram_slot(model, item_id, stem, realization, 718000 + item_index),
    }
    slot = {
        "id": item_id,
        "difficulty": difficulty,
        "training_action": training_action,
        "question_type": "problem",
        "variation_dimension": variation,
        "diagram_requirement": "prompt_only",
        "number_selection": number_selection,
        "geometry_selection": geometry_selection,
        "source_pair": list(source_pair),
        "target_pair": [known_name, unknown_name],
        "title": title,
    }
    return block, slot


def make_nested_problem(
    model: ModelSpec,
    item_id: str,
    number_entry: TrainingNumberEntry,
    realization: SimilarityTriangleEntry,
    difficulty: str,
    item_index: int,
    condition_route: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Author the nested model as corresponding-side <=> collinear-segment transfer."""
    lengths = nested_lengths(realization)
    ab = lengths["AB"][2]
    ad = lengths["AD"][2]
    ac = lengths["AC"][2]
    cd = lengths["CD"][2]
    if condition_route == "collinear_segments_to_corresponding_side":
        knowns = rf"$AC={ac}$，$CD={cd}$"
        unknown_name = "AB"
        answer = rf"$AB={ab}$。"
        training_action = "由共线整段与分段求对应边"
        solution_steps = [
            {
                "title": "先求小三角形的共线边",
                "content": rf"因为点 $D$ 在线段 $AC$ 上，所以 $AD=AC-CD={ac}-{cd}={ad}$。",
            },
            {
                "title": "由等角判相似",
                "content": rf"由题设等角以及 $A$ 点的公共角，得 ${model.similarity_statement}$。",
            },
            {
                "title": "锁定重复出现的对应边",
                "content": r"对应关系为 $AB\leftrightarrow AC$、$AD\leftrightarrow AB$，因此线段 $AB$ 在比例链中重复出现。",
            },
            {
                "title": "把共线边转成对应边",
                "content": rf"由 $\dfrac{{AC}}{{AB}}=\dfrac{{AB}}{{AD}}$，得 $AB^2=AC\cdot AD={ac}\times {ad}$。",
            },
            {
                "title": "求值并验算",
                "content": rf"边长取正，得 $AB={ab}$；代回可得 $\dfrac{{AC}}{{AB}}=\dfrac{{AB}}{{AD}}$。",
            },
        ]
        source_pair = ["AC", "CD"]
        target_pair = ["AB"]
        fallback_move = "先用 $AD=AC-CD$ 把共线分段换成小三角形的边。"
    elif condition_route == "corresponding_sides_to_collinear_segment":
        knowns = rf"$AC={ac}$，$AB={ab}$"
        unknown_name = "CD"
        answer = rf"$CD={cd}$。"
        training_action = "由对应边反求共线分段"
        solution_steps = [
            {
                "title": "由等角判相似",
                "content": rf"由题设等角以及 $A$ 点的公共角，得 ${model.similarity_statement}$。",
            },
            {
                "title": "锁定重复出现的对应边",
                "content": r"对应关系为 $AB\leftrightarrow AC$、$AD\leftrightarrow AB$，因此可用 $AB$ 连接两组对应边。",
            },
            {
                "title": "由对应边反求共线边",
                "content": rf"由 $\dfrac{{AC}}{{AB}}=\dfrac{{AB}}{{AD}}$，即 $AB^2=AC\cdot AD$，得 $AD=\dfrac{{AB^2}}{{AC}}={ad}$。",
            },
            {
                "title": "处理同一直线上的整段与分段",
                "content": rf"点 $D$ 在线段 $AC$ 上，所以 $CD=AC-AD={ac}-{ad}$。",
            },
            {
                "title": "求值并验算",
                "content": rf"化简得 $CD={cd}$；并且 $AD+CD=AC$。",
            },
        ]
        source_pair = ["AC", "AB"]
        target_pair = ["CD"]
        fallback_move = r"先由 $AB^2=AC\cdot AD$ 求 $AD$，再用 $CD=AC-AD$。"
    elif condition_route == "collinear_triangle_sides_to_corresponding_side":
        knowns = rf"$AC={ac}$，$AD={ad}$"
        unknown_name = "AB"
        answer = rf"$AB={ab}$。"
        training_action = "由两条共线三角形边求对应边"
        solution_steps = [
            {
                "title": "由等角判相似",
                "content": rf"由题设等角以及 $A$ 点的公共角，得 ${model.similarity_statement}$。",
            },
            {
                "title": "锁定重复出现的对应边",
                "content": r"对应关系为 $AB\leftrightarrow AC$、$AD\leftrightarrow AB$，因此线段 $AB$ 在比例链中重复出现。",
            },
            {
                "title": "把共线边转成对应边",
                "content": r"由 $\dfrac{AC}{AB}=\dfrac{AB}{AD}$，得 $AB^2=AC\cdot AD$。",
            },
            {
                "title": "代入已知边长",
                "content": rf"代入得 $AB^2={ac}\times {ad}$。",
            },
            {
                "title": "求值并验算",
                "content": rf"边长取正，得 $AB={ab}$；代回后两组对应边的比相等。",
            },
        ]
        source_pair = ["AC", "AD"]
        target_pair = ["AB"]
        fallback_move = "把 $AC,AD$ 看成同一直线上的大、小三角形边，再观察比例链中重复的 $AB$。"
    elif condition_route == "corresponding_sides_to_inner_collinear_segment":
        knowns = rf"$AC={ac}$，$AB={ab}$"
        unknown_name = "AD"
        answer = rf"$AD={ad}$。"
        training_action = "由对应边反求内侧共线边"
        solution_steps = [
            {
                "title": "由等角判相似",
                "content": rf"由题设等角以及 $A$ 点的公共角，得 ${model.similarity_statement}$。",
            },
            {
                "title": "锁定对应关系",
                "content": r"对应关系为 $AB\leftrightarrow AC$、$AD\leftrightarrow AB$。",
            },
            {
                "title": "写出中间边平方关系",
                "content": r"由 $\dfrac{AC}{AB}=\dfrac{AB}{AD}$，得 $AB^2=AC\cdot AD$。",
            },
            {
                "title": "反求共线边",
                "content": rf"所以 $AD=\dfrac{{AB^2}}{{AC}}={ad}$。",
            },
            {
                "title": "验算",
                "content": rf"代回可得 $\dfrac{{AC}}{{AB}}=\dfrac{{AB}}{{AD}}$，故 $AD={ad}$。",
            },
        ]
        source_pair = ["AC", "AB"]
        target_pair = ["AD"]
        fallback_move = r"直接把比例式交叉相乘，先得到 $AB^2=AC\cdot AD$。"
    elif condition_route == "corresponding_inner_side_to_outer_collinear_side":
        knowns = rf"$AB={ab}$，$AD={ad}$"
        unknown_name = "AC"
        answer = rf"$AC={ac}$。"
        training_action = "由对应中间边与内侧共线边求整段"
        solution_steps = [
            {
                "title": "由等角判相似",
                "content": rf"由题设等角以及 $A$ 点的公共角，得 ${model.similarity_statement}$。",
            },
            {
                "title": "锁定对应关系",
                "content": r"对应关系为 $AB\leftrightarrow AC$、$AD\leftrightarrow AB$。",
            },
            {
                "title": "写出中间边平方关系",
                "content": r"由 $\dfrac{AC}{AB}=\dfrac{AB}{AD}$，得 $AB^2=AC\cdot AD$。",
            },
            {
                "title": "反求共线整段",
                "content": rf"所以 $AC=\dfrac{{AB^2}}{{AD}}={ac}$。",
            },
            {
                "title": "验算",
                "content": rf"代回后两组对应边的比相等，故 $AC={ac}$。",
            },
        ]
        source_pair = ["AB", "AD"]
        target_pair = ["AC"]
        fallback_move = r"直接由 $AB^2=AC\cdot AD$ 解出 $AC$。"
    else:
        raise RuntimeError(f"unsupported nested condition route: {condition_route}")

    stem = f"{model.base_stem}\n\n已知 {knowns}。求 ${unknown_name}$ 的长。"
    number_selection = {
        "database_id": NUMBER_DATABASE_ID,
        "family_id": number_entry.family,
        "entry_id": number_entry.id,
        "values_latex": [value.latex for value in realization.source_values],
        "squared_ratio": list(ratio_signature(number_entry)),
        "largest_prime_factor_max": 5,
        "max_ratio": "sqrt(3)",
        "source_fractional_coefficients_allowed": False,
        "unknown_value_restrictions": "none_beyond_positive_exact_value",
    }
    geometry_selection = {
        "database_id": GEOMETRY_DATABASE_ID,
        "entry_id": realization.id,
        "model": realization.model,
        "source_pair_index": realization.source_pair_index,
        "target_pair_index": realization.target_pair_index,
        "known_target_position": realization.known_target_position,
        "number_side_indices": [realization.source_pair_index, realization.target_pair_index],
        "condition_route": condition_route,
        "physical_lengths": {name: value[2] for name, value in lengths.items()},
    }
    resolved_slot = diagram_slot(model, item_id, stem, realization, 718000 + item_index)
    resolved_slot["engine_options"]["scene_payload"]["rationale"] = (
        "沿用已通过 Wolfram 校验的子母形构型；本次只把题目条件改为对应边与共线整段、分段之间的转换，不重画题图。"
    )
    resolved_slot["semantic_constraints"]["given_constraints"] = list(model.given_constraints) + [
        "AC equals AD plus CD",
        "AB squared equals AC times AD",
        "the prompt transfers between corresponding-side data and collinear-segment data",
    ]
    block = {
        "type": "problem",
        "id": item_id,
        "points": 10,
        "label": "对应边与共线边互化",
        "stem_latex": stem,
        "answer_space": {"type": "steps", "height": "54mm", "step_count": 5},
        "answer": answer,
        "clue": "利用子母形中间边重复对应的特点，在对应边关系与共线整段、分段之间转换。",
        "solution_steps": solution_steps,
        "teaching": {
            "teaching_goal": training_action,
            "source_relations": ["explanation:nested", "nested_middle_side_geometric_mean", "collinear_segment_difference"],
            "expected_blocker": "仍按普通构型寻找两组彼此分离的对应边，忽略 $AB$ 在比例链中重复出现。",
            "entry_point": "corresponding_side_bidirectional_collinear_segment",
            "scaffold_level": "high" if difficulty == "foundation" else "medium" if difficulty == "standard" else "low",
            "variation_depth": "changed_numbers" if difficulty == "foundation" else "changed_representation",
            "complexity_note": "条件只在 $AB,AC$ 这组对应关系与 $AD,CD,AC$ 这组共线关系之间切换。",
            "upgrade_rule": r"能主动写出 $AB^2=AC\cdot AD$，并根据已知方向决定先乘方还是先作差。",
            "fallback_move": fallback_move,
            "number_selection": number_selection,
            "geometry_selection": geometry_selection,
        },
        "diagram_slot": resolved_slot,
    }
    slot = {
        "id": item_id,
        "difficulty": difficulty,
        "training_action": training_action,
        "question_type": "problem",
        "variation_dimension": block["teaching"]["variation_depth"],
        "diagram_requirement": "prompt_only",
        "number_selection": number_selection,
        "geometry_selection": geometry_selection,
        "source_pair": source_pair,
        "target_pair": target_pair,
        "condition_route": condition_route,
        "title": "对应边与共线边互化",
    }
    return block, slot


def assignment(model: ModelSpec, item_id: str, block: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": {
            "title": f"{model.topic} · {item_id} · 教师版",
            "grade": "八年级",
            "subject": "数学",
            "total_points": 10,
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {
                "explanation": model.source_explanation,
                "number_database": str(NUMBER_DATABASE.relative_to(ROOT)),
                "geometry_database": str(GEOMETRY_DATABASE.relative_to(ROOT)),
                "diagram_policy": "一题一张独立 prompt 图；题图不泄露化简、相似结论或答案",
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


NESTED_ROUTE_SPECS = {
    "collinear_segments_to_corresponding_side": (("AC", "CD"), "AB"),
    "corresponding_sides_to_collinear_segment": (("AC", "AB"), "CD"),
    "collinear_triangle_sides_to_corresponding_side": (("AC", "AD"), "AB"),
    "corresponding_sides_to_inner_collinear_segment": (("AC", "AB"), "AD"),
    "corresponding_inner_side_to_outer_collinear_side": (("AB", "AD"), "AC"),
}


def nested_task_signature(
    condition_route: str,
    realization: SimilarityTriangleEntry,
) -> tuple[tuple[tuple[str, str], ...], str]:
    lengths = nested_lengths(realization)
    known_names, target_name = NESTED_ROUTE_SPECS[condition_route]
    knowns = tuple((name, lengths[name][2]) for name in known_names)
    return knowns, f"{target_name}={lengths[target_name][2]}"


def choose_nested_condition_route(
    item_index: int,
    realization: SimilarityTriangleEntry,
    used_signatures: set[tuple[tuple[tuple[str, str], ...], str]],
    reserved_signatures: set[tuple[tuple[tuple[str, str], ...], str]],
) -> str:
    preferred = (
        "collinear_segments_to_corresponding_side"
        if item_index % 2 == 0
        else "corresponding_sides_to_collinear_segment"
    )
    preferred_signature = nested_task_signature(preferred, realization)
    if preferred_signature not in used_signatures:
        used_signatures.add(preferred_signature)
        return preferred
    for route in NESTED_ROUTE_SPECS:
        if route == preferred:
            continue
        signature = nested_task_signature(route, realization)
        if signature not in used_signatures and signature not in reserved_signatures:
            used_signatures.add(signature)
            return route
    raise RuntimeError(f"{realization.id}: no unique nested condition route remains")


def write_yaml(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


def sync_existing_resolved(item_root: Path, block: dict[str, Any]) -> None:
    """Refresh wording without rerendering an already resolved prompt diagram."""
    teacher_path = item_root / "teacher.resolved.assignment.yaml"
    if not teacher_path.exists():
        return
    teacher = yaml.safe_load(teacher_path.read_text(encoding="utf-8"))
    old_block = teacher["sections"][0]["blocks"][0]
    resolved_diagrams = {
        key: copy.deepcopy(value)
        for key, value in old_block.items()
        if key in {"diagram_col", "diagram_row", "image_path"}
    }
    resolved_block = copy.deepcopy(block)
    resolved_block.pop("diagram_slot", None)
    resolved_block.update(resolved_diagrams)
    teacher["sections"][0]["blocks"][0] = resolved_block
    write_yaml(teacher_path, teacher)
    write_yaml(item_root / "student.resolved.assignment.yaml", derive_student_assignment(teacher))


def generate_model(
    model: ModelSpec,
    output_root: Path,
    numbers: dict[str, TrainingNumberEntry],
    geometries: list[SimilarityTriangleEntry],
    seed: int,
) -> None:
    bank_root = output_root / model.bank_dir
    ordered = select_realizations(model, numbers, geometries, seed)
    if len(ordered) != 50:
        raise RuntimeError(f"{model.key}: expected 50 selected realizations")
    slots = []
    items = []
    nested_signatures: set[tuple[tuple[tuple[str, str], ...], str]] = set()
    nested_reserved_signatures = {
        nested_task_signature(
            (
                "collinear_segments_to_corresponding_side"
                if index % 2 == 0
                else "corresponding_sides_to_collinear_segment"
            ),
            realization,
        )
        for index, realization in enumerate(ordered)
    } if model.key == "nested" else set()
    for index, realization in enumerate(ordered):
        item_id = f"Q{index + 1:03d}"
        difficulty = difficulty_for_index(index)
        number_entry = numbers[realization.number_entry_id]
        if model.key == "nested":
            condition_route = choose_nested_condition_route(
                index,
                realization,
                nested_signatures,
                nested_reserved_signatures,
            )
            block, slot = make_nested_problem(
                model,
                item_id,
                number_entry,
                realization,
                difficulty,
                index,
                condition_route,
            )
        else:
            block, slot = make_problem(model, item_id, number_entry, realization, difficulty, index)
        slots.append(slot)
        item_root = bank_root / "items" / item_id
        write_yaml(item_root / "teacher.plan.assignment.yaml", assignment(model, item_id, block))
        sync_existing_resolved(item_root, block)
        items.append(
            {
                "id": item_id,
                "title": slot["title"],
                "question_type": "problem",
                "difficulty": difficulty,
                "skill_tags": (
                    ["子母形", "对应边与共线边互化", "线段和差", "中间边平方关系"]
                    if model.key == "nested"
                    else ["化最简整数比", "等角找相似", "对应顶点", FAMILY_LABELS[number_entry.family]]
                ),
                "variation_dimension": slot["variation_dimension"],
                "diagram_requirement": "prompt_only",
                "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
                "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
                "weight": 1.0,
                "enabled": True,
            }
        )
    route_counts = Counter((slot["geometry_selection"]["source_pair_index"], slot["geometry_selection"]["target_pair_index"]) for slot in slots)
    family_counts = Counter(slot["number_selection"]["family_id"] for slot in slots)
    difficulty_counts = Counter(slot["difficulty"] for slot in slots)
    if family_counts != Counter({SIMILARITY_FAMILY: 50}):
        raise RuntimeError(f"{model.key}: incorrect family distribution {family_counts}")
    if difficulty_counts != Counter({"foundation": 16, "standard": 20, "challenge": 14}):
        raise RuntimeError(f"{model.key}: incorrect difficulty distribution {difficulty_counts}")
    if max(route_counts.values()) - min(route_counts.values()) > 1:
        raise RuntimeError(f"{model.key}: routes are not balanced {route_counts}")
    coverage = {
        "topic": model.topic,
        "source_explanation": model.source_explanation,
        "target_count": 50,
        "difficulty_distribution": dict(difficulty_counts),
        "number_distribution": dict(family_counts),
        "route_distribution": {f"{a}->{b}": count for (a, b), count in sorted(route_counts.items())},
        "design_note": (
            "子母形不沿用普通构型的“两组对应边”模板；题目在对应边与共线整段、分段之间双向转换，并确保数值条件与所求量的组合不重复。核心关系为 AB^2=AC·AD 与 AC=AD+CD。"
            if model.key == "nested"
            else "数库数对作为同一基准三角形的两条边：无分数、最大素因数不超过 5、边长比不超过根号 3。另一三角形只给一条整数对应边；精确派生的未知边允许是分数或含更大素因数。相似缩放控制在 1/根号3 到根号3。"
        ),
        "slots": slots,
    }
    manifest = {
        "schema": "math_topic_question_bank/v1",
        "bank": {
            "id": model.bank_id,
            "topic": model.topic,
            "grade": "八年级",
            "subject": "数学",
            "source_explanation": model.source_explanation,
            "status": "ready" if all(
                (bank_root / "items" / f"Q{index:03d}" / version).exists()
                for index in range(1, 51)
                for version in ("teacher.resolved.assignment.yaml", "student.resolved.assignment.yaml")
            ) else "plan",
            "target_count": 50,
        },
        "items": items,
    }
    write_yaml(bank_root / "coverage-plan.yaml", coverage)
    write_yaml(bank_root / "question-bank.yaml", manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=ROOT / "artifacts/题库")
    parser.add_argument("--model", choices=[model.key for model in MODELS])
    args = parser.parse_args()
    numbers, geometries = load_sources()
    for offset, model in enumerate(MODELS):
        if args.model and model.key != args.model:
            continue
        generate_model(model, args.output_root.resolve(), numbers, geometries, 718 + 97 * offset)
        print(f"generated {model.topic}: 50 plans")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
