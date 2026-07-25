#!/usr/bin/env python3
"""Generate model-specific, Wolfram-verified similarity realizations."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import tempfile
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

from similarity_triangle_contracts import SimilarityTriangleDatabase
from training_number_contracts import largest_prime_factor, normalize_length
from training_number_review_state import available_entries, load_database, load_review


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_NUMBER_DATABASE = SCRIPT_DIR.parent / "data/training-number-database.yaml"
DEFAULT_REVIEW = SCRIPT_DIR.parent / "data/training-number-review.yaml"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "data/similarity-triangle-database.yaml"
WOLFRAM_VERIFIER = SCRIPT_DIR / "verify_similarity_triangles.wls"

FAMILIES = {"noncoprime_radicand_pairs"}
MODEL_ROUTES = {
    "reverse_a": ((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)),
    "butterfly": ((0, 1), (0, 2), (1, 0), (1, 2), (2, 0), (2, 1)),
    "nested": ((0, 2), (2, 0)),
}
MODEL_TRIANGLES = {
    "reverse_a": ("P", "A", "B"),
    "butterfly": ("A", "O", "C"),
    "nested": ("A", "B", "D"),
}
MODEL_SMALL_SEGMENTS = {
    "reverse_a": ("PA", "PB", "AB"),
    "butterfly": ("AO", "OC", "AC"),
    "nested": ("AB", "AD", "BD"),
}


def exact_payload(coefficient: Fraction, radicand: int = 1) -> dict[str, Any]:
    coefficient, radicand = normalize_length(coefficient, radicand)
    coefficient_text = str(coefficient)
    if radicand == 1:
        latex = str(coefficient.numerator) if coefficient.denominator == 1 else rf"\frac{{{coefficient.numerator}}}{{{coefficient.denominator}}}"
        display = coefficient_text
    else:
        radical = rf"\sqrt{{{radicand}}}"
        if coefficient == 1:
            latex = radical
            display = f"sqrt({radicand})"
        else:
            coeff_latex = str(coefficient.numerator) if coefficient.denominator == 1 else rf"\frac{{{coefficient.numerator}}}{{{coefficient.denominator}}}"
            latex = f"{coeff_latex}{radical}"
            display = f"{coefficient_text}*sqrt({radicand})"
    return {"coefficient": coefficient_text, "radicand": radicand, "latex": latex, "display": display}


def multiply_values(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return exact_payload(
        Fraction(left["coefficient"]) * Fraction(right["coefficient"]),
        int(left["radicand"]) * int(right["radicand"]),
    )


def divide_values(numerator: dict[str, Any], denominator: dict[str, Any]) -> dict[str, Any]:
    return exact_payload(
        Fraction(numerator["coefficient"])
        / Fraction(denominator["coefficient"])
        / int(denominator["radicand"]),
        int(numerator["radicand"]) * int(denominator["radicand"]),
    )


def allowed_similarity_value(value: dict[str, Any], coefficient_max: int = 36) -> bool:
    coefficient = Fraction(value["coefficient"])
    return (
        coefficient.denominator == 1
        and coefficient.numerator <= coefficient_max
        and largest_prime_factor(coefficient.numerator) <= 5
        and largest_prime_factor(int(value["radicand"])) <= 5
    )


def allowed_internal_value(value: dict[str, Any]) -> bool:
    coefficient = Fraction(value["coefficient"])
    return (
        coefficient.numerator <= 36
        and coefficient.denominator <= 20
        and largest_prime_factor(coefficient.numerator) <= 5
        and largest_prime_factor(coefficient.denominator) <= 5
        and largest_prime_factor(int(value["radicand"])) <= 5
    )


def balanced_similarity_scale(value: dict[str, Any]) -> bool:
    squared = Fraction(value["coefficient"]) ** 2 * int(value["radicand"])
    return squared <= 3 and 3 * squared >= 1


def numeric(value: dict[str, Any]) -> float:
    return float(Fraction(value["coefficient"])) * math.sqrt(int(value["radicand"]))


def triangle_metrics(sides: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    a, b, c = [numeric(value) for value in sides]
    if min(a, b, c) <= 0 or a + b <= c or a + c <= b or b + c <= a:
        return None
    perimeter = a + b + c
    semiperimeter = perimeter / 2
    area_squared = semiperimeter * (semiperimeter - a) * (semiperimeter - b) * (semiperimeter - c)
    if area_squared <= 0:
        return None
    area = math.sqrt(area_squared)
    angles = []
    for opposite, left, right in ((a, b, c), (b, a, c), (c, a, b)):
        cosine = (left * left + right * right - opposite * opposite) / (2 * left * right)
        angles.append(math.degrees(math.acos(max(-1.0, min(1.0, cosine)))))
    gaps = [abs(a - b) / max(a, b), abs(a - c) / max(a, c), abs(b - c) / max(b, c)]
    inradius = area / semiperimeter
    circumradius = a * b * c / (4 * area)
    heights = [2 * area / side for side in (a, b, c)]
    return min(angles), min(gaps), inradius / circumradius, min(heights) / perimeter


def passes_preflight(sides: list[dict[str, Any]]) -> bool:
    metrics = triangle_metrics(sides)
    if metrics is None:
        return False
    angle, gap, radius_ratio, height_ratio = metrics
    return angle >= 30 - 1e-9 and gap >= 0.1 - 1e-9 and radius_ratio > 0.1 and height_ratio > 0.08


def quality_constraints(model: str, hidden_segment: str, hidden_value: dict[str, Any] | None) -> list[str]:
    triangle = MODEL_TRIANGLES[model]
    triangle_wl = ", ".join(triangle)
    segments = MODEL_SMALL_SEGMENTS[model]
    constraints = [
        f'TriangleMeasurement[{{{triangle_wl}}}, {{"InteriorAngle", {point}}}] >= 30 Degree'
        for point in triangle
    ]
    constraints.extend(
        [
            f"10 Abs[EuclideanDistance[{a[0]}, {a[1]}] - EuclideanDistance[{b[0]}, {b[1]}]] >= Max[EuclideanDistance[{a[0]}, {a[1]}], EuclideanDistance[{b[0]}, {b[1]}]]"
            for a, b in ((segments[0], segments[1]), (segments[0], segments[2]), (segments[1], segments[2]))
        ]
    )
    constraints.append(
        f"10 TriangleMeasurement[Triangle[{{{triangle_wl}}}], \"Inradius\"] > TriangleMeasurement[Triangle[{{{triangle_wl}}}], \"Circumradius\"]"
    )
    constraints.extend(
        f"25 TriangleMeasurement[Triangle[{{{triangle_wl}}}], {{\"Height\", {point}}}] > 2 TriangleMeasurement[Triangle[{{{triangle_wl}}}], \"Perimeter\"]"
        for point in triangle
    )
    if hidden_value is not None:
        coefficient = hidden_value["coefficient"]
        radicand = hidden_value["radicand"]
        wl_value = coefficient if radicand == 1 else f"({coefficient}) Sqrt[{radicand}]"
        constraints.insert(0, f"EuclideanDistance[{hidden_segment[0]}, {hidden_segment[1]}] == {wl_value}")
    return constraints


def hidden_candidates(
    first: dict[str, Any],
    second: dict[str, Any],
    limit: int = 1,
) -> list[dict[str, Any]]:
    candidates = []
    for quarter in range(1, 145):
        hidden = exact_payload(Fraction(quarter, 4))
        if not allowed_internal_value(hidden):
            continue
        sides = [first, second, hidden]
        metrics = triangle_metrics(sides)
        if metrics and passes_preflight(sides):
            candidates.append((metrics, hidden))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [value for _, value in candidates[:limit]]


def candidate_records(database: Any, review: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for family_id in sorted(FAMILIES):
        for entry in available_entries(database, review, family_id=family_id):
            if not entry.parameters.get("similarity_eligible", False):
                continue
            source_values = sorted(
                (value.model_dump(mode="json") for value in entry.values),
                key=lambda value: Fraction(value["coefficient"]) ** 2 * int(value["radicand"]),
            )
            for model, routes in MODEL_ROUTES.items():
                model_candidates: list[dict[str, Any]] = []
                for source_index, target_index in routes:
                    hidden_index = ({0, 1, 2} - {source_index, target_index}).pop()
                    small_side_map: dict[int, dict[str, Any]] = {
                        source_index: source_values[0],
                        target_index: source_values[1],
                    }
                    if model == "nested":
                        # For the shared-edge model the similarity scale is
                        # AB/AD.  Derive AD from each permitted integer on the
                        # other triangle instead of hoping a generic grid hits
                        # an integral displayed value.
                        ab_value = small_side_map[0]
                        derived_hidden: dict[tuple[str, int], dict[str, Any]] = {}
                        for source_known in source_values:
                            for known_integer in range(1, 21):
                                known = exact_payload(Fraction(known_integer))
                                if not allowed_similarity_value(known):
                                    continue
                                hidden = divide_values(
                                    multiply_values(ab_value, source_known),
                                    known,
                                )
                                if allowed_internal_value(hidden):
                                    derived_hidden[(hidden["coefficient"], hidden["radicand"])] = hidden
                        hidden_options = list(derived_hidden.values())
                    else:
                        hidden_options = hidden_candidates(
                            source_values[0],
                            source_values[1],
                        )
                    for hidden_value in hidden_options:
                        small_side_map[hidden_index] = hidden_value
                        sides = [small_side_map[index] for index in range(3)]
                        metrics = triangle_metrics(sides)
                        if metrics is None or not passes_preflight(sides):
                            continue

                        target_options: list[tuple[str, int, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
                        if model == "nested":
                            # In triangle ABD ~ ACB, AB is both small side 0 and
                            # the large side corresponding to AD (small side 1).
                            scale = divide_values(sides[0], sides[1])
                            if numeric(scale) <= 1 or not balanced_similarity_scale(scale):
                                continue
                            target_small = multiply_values(source_values[0], scale)
                            target_large = multiply_values(source_values[1], scale)
                            for known_position, known_value, unknown in (
                                ("small", target_small, target_large),
                                ("large", target_large, target_small),
                            ):
                                coefficient = Fraction(known_value["coefficient"])
                                if known_value["radicand"] != 1 or coefficient.denominator != 1:
                                    continue
                                known_integer = coefficient.numerator
                                if not 1 <= known_integer <= 20:
                                    continue
                                if allowed_similarity_value(known_value):
                                    target_options.append(
                                        (known_position, known_integer, target_small, target_large, unknown)
                                    )
                        else:
                            for known_position in ("small", "large"):
                                source_known = source_values[0] if known_position == "small" else source_values[1]
                                for known_integer in range(1, 21):
                                    known = exact_payload(Fraction(known_integer))
                                    if not allowed_similarity_value(known):
                                        continue
                                    scale = divide_values(known, source_known)
                                    if not balanced_similarity_scale(scale):
                                        continue
                                    target_small = multiply_values(source_values[0], scale)
                                    target_large = multiply_values(source_values[1], scale)
                                    unknown = target_large if known_position == "small" else target_small
                                    if model == "reverse_a":
                                        small0, small1 = numeric(sides[0]), numeric(sides[1])
                                        scale_numeric = numeric(scale)
                                        if not (
                                            small0 <= 0.9 * scale_numeric * small1
                                            and small1 <= 0.9 * scale_numeric * small0
                                        ):
                                            continue
                                    target_options.append(
                                        (known_position, known_integer, target_small, target_large, unknown)
                                    )

                        for known_position, known_integer, target_small, target_large, unknown in target_options:
                            hidden_segment = MODEL_SMALL_SEGMENTS[model][hidden_index]
                            item_id = (
                                f"{model.replace('_', '-')}-{entry.id}-s{source_index}-t{target_index}-"
                                f"{known_position}-n{known_integer}"
                            )
                            model_candidates.append(
                                {
                                    "id": item_id,
                                    "number_entry_id": entry.id,
                                    "number_family_id": family_id,
                                    "model": model,
                                    "source_pair_index": source_index,
                                    "target_pair_index": target_index,
                                    "known_target_position": known_position,
                                    "known_integer": known_integer,
                                    "unknown_value": unknown,
                                    "source_values": source_values,
                                    "target_values": [target_small, target_large],
                                    "small_triangle_sides": sides,
                                    "hidden_pair_index": hidden_index,
                                    "scene_constraints": quality_constraints(
                                        model,
                                        hidden_segment,
                                        hidden_value,
                                    ),
                                    "_preflight_score": list(metrics),
                                }
                            )
                model_candidates.sort(
                    key=lambda record: (
                        tuple(record["_preflight_score"]),
                        -record["known_integer"],
                        -Fraction(record["unknown_value"]["coefficient"]).denominator,
                    ),
                    reverse=True,
                )
                chosen: list[dict[str, Any]] = []
                seen_routes: set[tuple[int, int]] = set()
                for record in model_candidates:
                    route = (record["source_pair_index"], record["target_pair_index"])
                    if route in seen_routes:
                        continue
                    chosen.append(record)
                    seen_routes.add(route)
                    if len(chosen) == 3:
                        break
                if len(chosen) < 3:
                    for record in model_candidates:
                        if record in chosen:
                            continue
                        chosen.append(record)
                        if len(chosen) == 3:
                            break
                candidates.extend(chosen)
    return candidates


def wolfram_verify(candidates: list[dict[str, Any]], wolframscript: str) -> dict[str, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="similarity-triangles-") as tmp:
        input_path = Path(tmp) / "candidates.json"
        output_path = Path(tmp) / "results.json"
        payload = {
            "candidates": [
                {"id": candidate["id"], "small_triangle_sides": candidate["small_triangle_sides"]}
                for candidate in candidates
            ]
        }
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            [wolframscript, "-file", str(WOLFRAM_VERIFIER), str(input_path), str(output_path)],
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0 or not output_path.exists():
            raise RuntimeError(f"Wolfram similarity verification failed: {completed.stdout}\n{completed.stderr}")
        result = json.loads(output_path.read_text(encoding="utf-8"))
    return {row["id"]: row for row in result["results"]}


def generate(output: Path, number_database: Path, review_path: Path, wolframscript: str) -> SimilarityTriangleDatabase:
    database = load_database(number_database)
    review = load_review(review_path, database)
    candidates = candidate_records(database, review)
    verified = wolfram_verify(candidates, wolframscript)
    entries = []
    for candidate in candidates:
        result = verified.get(candidate["id"])
        if not result or not result["valid"]:
            continue
        candidate.pop("_preflight_score", None)
        candidate["quality"] = result["quality"]
        entries.append(candidate)
    payload = {
        "schema": "math_similarity_triangle_database/v1",
        "database": {
            "id": "similarity-triangle-realizations",
            "source_number_database_id": database.database.id,
            "generator": "generate_similarity_triangle_database.py + verify_similarity_triangles.wls",
            "maximum_realizations_per_number_model": 3,
        },
        "entries": entries,
    }
    parsed = SimilarityTriangleDatabase.model_validate(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.safe_dump(parsed.model_dump(by_alias=True, mode="json"), allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--number-database", type=Path, default=DEFAULT_NUMBER_DATABASE)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--wolframscript", default="wolframscript")
    args = parser.parse_args()
    database = generate(
        args.output.resolve(),
        args.number_database.resolve(),
        args.review.resolve(),
        args.wolframscript,
    )
    counts: dict[str, int] = defaultdict(int)
    for entry in database.entries:
        counts[entry.model] += 1
    print(f"SIMILARITY TRIANGLE DATABASE GENERATED: {len(database.entries)} -> {args.output}")
    for model in MODEL_ROUTES:
        print(f"- {model}: {counts[model]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
