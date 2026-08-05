#!/usr/bin/env python3
"""Validate all three materialized layers of the triangle cosine pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from generate_triangle_cosine_database import verify_triangle
from triangle_cosine_contracts import CandidateDatabase, TrigRatioDatabase, TriangleDatabase


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"


def load(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: YAML root must be a mapping")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trig-database",
        type=Path,
        default=DATA_DIR / "triangle-trig-ratio-database.yaml",
    )
    parser.add_argument(
        "--triangle-database",
        type=Path,
        default=DATA_DIR / "triangle-cosine-database.yaml",
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=DATA_DIR / "triangle-cosine-question-candidates.yaml",
    )
    args = parser.parse_args()

    trig = TrigRatioDatabase.model_validate(load(args.trig_database.resolve()))
    triangles = TriangleDatabase.model_validate(load(args.triangle_database.resolve()))
    candidates = CandidateDatabase.model_validate(load(args.candidates.resolve()))
    triangles.validate_trig_references(trig)
    for triangle in triangles.triangles:
        verify_triangle(triangle)

    triangle_ids = {triangle.id for triangle in triangles.triangles}
    for case in triangles.ssa_cases:
        if not set(case.triangle_ids).issubset(triangle_ids):
            raise ValueError(f"{case.id}: SSA case references an unknown triangle")
    for question in candidates.questions:
        if not set(question.source_triangle_ids).issubset(triangle_ids):
            raise ValueError(f"{question.id}: question references an unknown triangle")
        if any(character in question.stem_latex for character in ("\a", "\b", "\t", "\v", "\f", "\r")):
            raise ValueError(f"{question.id}: question stem contains a control character")
        if r"\triangle ABC" not in question.stem_latex:
            raise ValueError(f"{question.id}: question stem lost its triangle LaTeX command")
        for fact in question.visible_angle_facts:
            if fact.display == "supplement_ratio":
                expected = rf"\{fact.function}(180^\circ-{fact.angle_name})"
                if expected not in question.stem_latex:
                    raise ValueError(f"{question.id}: obtuse angle is not displayed through its supplement")

    counts = {
        problem_type: sum(question.problem_type == problem_type for question in candidates.questions)
        for problem_type in ("sss", "sas", "ssa", "aas", "asa")
    }
    covered_functions = {
        fact.function
        for question in candidates.questions
        for fact in question.visible_angle_facts
    } | {
        question.target_trig_function
        for question in candidates.questions
        if question.target_trig_function is not None
    }
    if covered_functions != {"sin", "cos", "tan", "cot"}:
        raise ValueError(f"question bank does not cover all four ratios: {sorted(covered_functions)}")
    one_solution = sum(len(case.triangle_ids) == 1 for case in triangles.ssa_cases)
    two_solutions = sum(len(case.triangle_ids) == 2 for case in triangles.ssa_cases)
    print(
        "TRIANGLE TRIG PIPELINE VALID: "
        f"trig={len(trig.entries)} triangles={len(triangles.triangles)} "
        f"ssa_one={one_solution} ssa_two={two_solutions} "
        f"ratios={sorted(covered_functions)} questions={counts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
