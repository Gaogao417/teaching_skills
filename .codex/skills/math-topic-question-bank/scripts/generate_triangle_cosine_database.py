#!/usr/bin/env python3
"""Materialize exact triangle shapes and their one/two-solution SSA index."""

from __future__ import annotations

import argparse
import itertools
from pathlib import Path
from typing import Any

import sympy as sp
import yaml

from triangle_cosine_contracts import (
    ExactSurd,
    TrigRatioDatabase,
    TriangleDatabase,
    TriangleShape,
)
from triangle_cosine_exact import (
    expression_key,
    from_expr,
    normalize_side_ratio,
    stable_digest,
    to_expr,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
DEFAULT_TRIG_DATABASE = SCRIPT_DIR.parent / "data/triangle-trig-ratio-database.yaml"
DEFAULT_TRIG_REVIEW = SCRIPT_DIR.parent / "data/triangle-trig-ratio-review.yaml"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "data/triangle-cosine-database.yaml"
ANGLE_NAMES = ("A", "B", "C")
SIDE_NAMES = ("a", "b", "c")


def portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_trig_database(path: Path) -> TrigRatioDatabase:
    return TrigRatioDatabase.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def angle_kind(cosine: sp.Expr) -> str:
    cosine = sp.simplify(cosine)
    if cosine == 0:
        return "right"
    return "acute" if bool(cosine > 0) else "obtuse"


def angle_payload(name: str, sine: sp.Expr, cosine: sp.Expr) -> dict[str, Any] | None:
    sine_value = from_expr(sine)
    cosine_value = from_expr(cosine)
    tangent_value = None if sp.simplify(cosine) == 0 else from_expr(sine / cosine)
    cotangent_value = from_expr(cosine / sine)
    if any(value is None for value in (sine_value, cosine_value, cotangent_value)):
        return None
    if cosine != 0 and tangent_value is None:
        return None
    kind = angle_kind(cosine)
    reference_cosine = from_expr(abs(cosine))
    reference_tangent = None if tangent_value is None else from_expr(abs(sine / cosine))
    reference_cotangent = from_expr(abs(cosine / sine))
    if any(value is None for value in (reference_cosine, reference_cotangent)):
        return None
    return {
        "name": name,
        "kind": kind,
        "actual": {
            "sin": sine_value.model_dump(mode="json"),
            "cos": cosine_value.model_dump(mode="json"),
            "tan": tangent_value.model_dump(mode="json") if tangent_value else None,
            "cot": cotangent_value.model_dump(mode="json"),
        },
        "reference": {
            "sin": sine_value.model_dump(mode="json"),
            "cos": reference_cosine.model_dump(mode="json"),
            "tan": reference_tangent.model_dump(mode="json") if reference_tangent else None,
            "cot": reference_cotangent.model_dump(mode="json"),
        },
    }


def triangle_key(sides: list[ExactSurd], cosines: list[sp.Expr]) -> tuple[str, ...]:
    return tuple(
        [f"{value.coefficient}:{value.radicand}" for value in sides]
        + [expression_key(value) for value in cosines]
    )


def build_triangles(trig_database: TrigRatioDatabase) -> list[TriangleShape]:
    triangles: dict[str, TriangleShape] = {}
    entries = sorted(trig_database.entries, key=lambda value: value.id)
    for first, second in itertools.combinations_with_replacement(entries, 2):
        sin_a, cos_a = to_expr(first.ratios.sin), to_expr(first.ratios.cos)
        sin_b, cos_b = to_expr(second.ratios.sin), to_expr(second.ratios.cos)
        sin_c = sp.simplify(sin_a * cos_b + cos_a * sin_b)
        cos_c = sp.simplify(sin_a * sin_b - cos_a * cos_b)
        raw_sines = [sin_a, sin_b, sin_c]
        raw_cosines = [cos_a, cos_b, cos_c]
        normalized_sides = normalize_side_ratio(raw_sines)
        if normalized_sides is None:
            continue

        for permutation in itertools.permutations(range(3)):
            sides = [normalized_sides[index] for index in permutation]
            sines = [raw_sines[index] for index in permutation]
            cosines = [raw_cosines[index] for index in permutation]
            angle_records = [
                angle_payload(name, sine, cosine)
                for name, sine, cosine in zip(ANGLE_NAMES, sines, cosines, strict=True)
            ]
            if any(record is None for record in angle_records):
                continue
            key = triangle_key(sides, cosines)
            triangle_id = f"tri-{stable_digest(*key)}"
            if triangle_id in triangles:
                continue
            payload = {
                "id": triangle_id,
                "sides": {
                    name: value.model_dump(mode="json")
                    for name, value in zip(SIDE_NAMES, sides, strict=True)
                },
                "angles": angle_records,
                "source_trig_ratio_ids": [first.id, second.id],
            }
            triangle = TriangleShape.model_validate(payload)
            verify_triangle(triangle)
            triangles[triangle_id] = triangle
    return sorted(triangles.values(), key=lambda value: value.id)


def verify_triangle(triangle: TriangleShape) -> None:
    sides = [to_expr(getattr(triangle.sides, name)) for name in SIDE_NAMES]
    for index, angle in enumerate(triangle.angles):
        opposite = sides[index]
        adjacent = [sides[position] for position in range(3) if position != index]
        expected_cosine = sp.simplify(
            (adjacent[0] ** 2 + adjacent[1] ** 2 - opposite**2)
            / (2 * adjacent[0] * adjacent[1])
        )
        if sp.simplify(expected_cosine - to_expr(angle.actual.cos)) != 0:
            raise ValueError(f"{triangle.id}: cosine-law audit failed at {angle.name}")
        if sp.simplify(to_expr(angle.actual.sin) ** 2 + to_expr(angle.actual.cos) ** 2 - 1) != 0:
            raise ValueError(f"{triangle.id}: trigonometric identity audit failed")


def public_display(angle: Any) -> str:
    if angle.kind == "obtuse":
        return "supplement_cosine"
    if angle.kind == "right":
        return "right_cosine"
    return "acute_cosine"


def positive_triangle(sides: list[sp.Expr]) -> bool:
    numeric = [float(sp.N(value, 30)) for value in sides]
    return min(numeric) > 0 and all(
        numeric[left] + numeric[right] > numeric[opposite] + 1e-10
        for opposite, (left, right) in enumerate(((1, 2), (0, 2), (0, 1)))
    )


def shape_lookup_key(
    triangle: TriangleShape,
    angle_index: int,
    other_index: int,
    missing_index: int,
) -> tuple[str, ...]:
    angle = triangle.angles[angle_index]
    sides = [to_expr(getattr(triangle.sides, name)) for name in SIDE_NAMES]
    return (
        str(angle_index),
        str(other_index),
        str(missing_index),
        expression_key(to_expr(angle.actual.sin)),
        expression_key(to_expr(angle.actual.cos)),
        expression_key(sides[other_index] / sides[angle_index]),
        expression_key(sides[missing_index] / sides[angle_index]),
    )


def build_ssa_cases(triangles: list[TriangleShape]) -> list[dict[str, Any]]:
    lookup: dict[tuple[str, ...], list[str]] = {}
    for triangle in triangles:
        for angle_index in range(3):
            for other_index in range(3):
                if other_index == angle_index:
                    continue
                missing_index = ({0, 1, 2} - {angle_index, other_index}).pop()
                key = shape_lookup_key(triangle, angle_index, other_index, missing_index)
                lookup.setdefault(key, []).append(triangle.id)

    cases: dict[str, dict[str, Any]] = {}
    for triangle in triangles:
        side_values = [getattr(triangle.sides, name) for name in SIDE_NAMES]
        sides = [to_expr(value) for value in side_values]
        for angle_index in range(3):
            angle = triangle.angles[angle_index]
            sine = to_expr(angle.actual.sin)
            cosine = to_expr(angle.actual.cos)
            opposite = sides[angle_index]
            for other_index in range(3):
                if other_index == angle_index:
                    continue
                missing_index = ({0, 1, 2} - {angle_index, other_index}).pop()
                other = sides[other_index]
                discriminant = sp.simplify(opposite**2 - other**2 * sine**2)
                if bool(discriminant < 0):
                    continue
                root_term = sp.sqrtdenest(sp.sqrt(discriminant))
                roots = []
                for candidate in (other * cosine - root_term, other * cosine + root_term):
                    candidate = sp.sqrtdenest(sp.radsimp(sp.simplify(candidate)))
                    if candidate <= 0:
                        continue
                    branch_sides = list(sides)
                    branch_sides[missing_index] = candidate
                    if not positive_triangle(branch_sides):
                        continue
                    if all(sp.simplify(candidate - existing) != 0 for existing in roots):
                        roots.append(candidate)
                if not roots or len(roots) > 2:
                    continue
                printable_roots = [from_expr(root) for root in roots]
                if any(root is None for root in printable_roots):
                    continue

                triangle_ids: list[str] = []
                all_materialized = True
                for root in roots:
                    key = (
                        str(angle_index),
                        str(other_index),
                        str(missing_index),
                        expression_key(sine),
                        expression_key(cosine),
                        expression_key(other / opposite),
                        expression_key(root / opposite),
                    )
                    matches = sorted(lookup.get(key, []))
                    if not matches:
                        all_materialized = False
                        break
                    triangle_ids.append(matches[0])
                if not all_materialized:
                    continue

                root_values = sorted(
                    [root for root in printable_roots if root is not None],
                    key=lambda value: float(sp.N(to_expr(value), 30)),
                )
                key_parts = (
                    ANGLE_NAMES[angle_index],
                    SIDE_NAMES[angle_index],
                    SIDE_NAMES[other_index],
                    SIDE_NAMES[missing_index],
                    expression_key(cosine),
                    expression_key(opposite),
                    expression_key(other),
                )
                case_id = f"ssa-{stable_digest(*key_parts)}"
                cases[case_id] = {
                    "id": case_id,
                    "known_angle_name": ANGLE_NAMES[angle_index],
                    "known_angle": angle.model_dump(mode="json"),
                    "opposite_side_name": SIDE_NAMES[angle_index],
                    "opposite_side": side_values[angle_index].model_dump(mode="json"),
                    "other_known_side_name": SIDE_NAMES[other_index],
                    "other_known_side": side_values[other_index].model_dump(mode="json"),
                    "missing_side_name": SIDE_NAMES[missing_index],
                    "triangle_ids": triangle_ids,
                    "missing_side_answers": [value.model_dump(mode="json") for value in root_values],
                }
    return [cases[key] for key in sorted(cases)]


def generate(trig_database_path: Path, trig_review_path: Path | None = None) -> TriangleDatabase:
    trig_database = load_trig_database(trig_database_path)
    if trig_review_path and trig_review_path.is_file():
        review = yaml.safe_load(trig_review_path.read_text(encoding="utf-8")) or {}
        disabled = set(review.get("disabled_entry_ids") or [])
        trig_database = trig_database.model_copy(
            update={"entries": [entry for entry in trig_database.entries if entry.id not in disabled]}
        )
    triangles = build_triangles(trig_database)
    payload = {
        "schema": "math_triangle_cosine_database/v1",
        "database": {
            "id": "triangle-cosine-shapes",
            "source_trig_ratio_database_id": trig_database.database.id,
            "source_trig_ratio_database": portable_path(trig_database_path),
            "generator": "generate_triangle_cosine_database.py",
        },
        "triangles": [triangle.model_dump(mode="json") for triangle in triangles],
        "ssa_cases": build_ssa_cases(triangles),
    }
    result = TriangleDatabase.model_validate(payload)
    result.validate_trig_references(trig_database)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trig-database", type=Path, default=DEFAULT_TRIG_DATABASE)
    parser.add_argument("--trig-review", type=Path, default=DEFAULT_TRIG_REVIEW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = generate(args.trig_database.resolve(), args.trig_review.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(result.model_dump(by_alias=True, mode="json"), allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    one_solution = sum(len(case.triangle_ids) == 1 for case in result.ssa_cases)
    two_solutions = sum(len(case.triangle_ids) == 2 for case in result.ssa_cases)
    print(
        f"TRIANGLE DATABASE GENERATED: {len(result.triangles)} triangles, "
        f"SSA one={one_solution}, two={two_solutions} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
