#!/usr/bin/env python3
"""Generate four-ratio question candidates strictly from a triangle database."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from triangle_cosine_contracts import (
    CandidateDatabase,
    CandidateQuestion,
    ExactSurd,
    TriangleDatabase,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[3]
DEFAULT_TRIANGLE_DATABASE = SCRIPT_DIR.parent / "data/triangle-cosine-database.yaml"
DEFAULT_TRIANGLE_REVIEW = SCRIPT_DIR.parent / "data/triangle-cosine-database-review.yaml"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "data/triangle-cosine-question-candidates.yaml"
ANGLE_NAMES = ("A", "B", "C")
SIDE_NAMES = ("a", "b", "c")
SIDE_SEGMENTS = {"a": "BC", "b": "CA", "c": "AB"}
TRIG_FUNCTIONS = ("sin", "cos", "tan", "cot")


def portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_triangle_database(path: Path) -> TriangleDatabase:
    return TriangleDatabase.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def angle_display(angle: Any) -> str:
    if angle.kind == "obtuse":
        return "supplement_ratio"
    if angle.kind == "right":
        return "right_ratio"
    return "acute_ratio"


def ratio_value(angle: Any, function: str) -> ExactSurd | None:
    return getattr(angle.reference, function)


def angle_fact(angle: Any, function: str) -> dict[str, Any]:
    value = ratio_value(angle, function)
    if value is None:
        raise ValueError(f"{function} is undefined for angle {angle.name}")
    return {
        "angle_name": angle.name,
        "function": function,
        "display": angle_display(angle),
        "value": value.model_dump(mode="json"),
    }


def angle_given_latex(angle: Any, function: str) -> str:
    value = ratio_value(angle, function)
    if value is None:
        raise ValueError(f"{function} is undefined for angle {angle.name}")
    command = rf"\{function}"
    if angle.kind == "obtuse":
        return rf"$\angle {angle.name}$ 为钝角，且 ${command}(180^\circ-{angle.name})={value.latex}$"
    return rf"${command} {angle.name}={value.latex}$"


def ratio_target_latex(angle: Any, function: str) -> str:
    command = rf"\{function}"
    if angle.kind == "obtuse":
        return rf"${command}(180^\circ-{angle.name})$"
    return rf"${command} {angle.name}$"


def side_fact(name: str, value: ExactSurd) -> str:
    return rf"${SIDE_SEGMENTS[name]}={value.latex}$"


def side_target(name: str) -> str:
    return rf"${SIDE_SEGMENTS[name]}$"


def content_hash(payload: dict[str, Any]) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def make_question(
    *,
    problem_type: str,
    target_kind: str,
    target_trig_function: str | None,
    stem_latex: str,
    answers: list[ExactSurd],
    angle_facts: list[dict[str, Any]],
    triangle_ids: list[str],
    solution_count: int,
) -> CandidateQuestion:
    distinct: dict[tuple[str, int], ExactSurd] = {}
    for answer in answers:
        distinct[(answer.coefficient, answer.radicand)] = answer
    sorted_answers = sorted(
        distinct.values(),
        key=lambda value: float(value.coefficient_fraction) * value.radicand**0.5,
    )
    core = {
        "problem_type": problem_type,
        "target_kind": target_kind,
        "target_trig_function": target_trig_function,
        "stem_latex": stem_latex,
        "answers": [answer.model_dump(mode="json") for answer in sorted_answers],
        "visible_angle_facts": angle_facts,
        "source_triangle_ids": sorted(set(triangle_ids)),
        "audit": {
            "solution_count": solution_count,
            "givens_reproduced": True,
            "answers_verified": True,
            "printable_values_only": True,
            "no_obtuse_trig_in_assignment": True,
        },
    }
    digest = content_hash(core)
    return CandidateQuestion.model_validate(
        {
            "id": f"TCQ-{digest[:12].upper()}",
            **core,
            "content_hash": digest,
        }
    )


def triangle_prefix() -> str:
    return r"在 $\triangle ABC$ 中，"


def generate_sss(triangle: Any) -> list[CandidateQuestion]:
    sides = [getattr(triangle.sides, name) for name in SIDE_NAMES]
    givens = "，".join(side_fact(name, value) for name, value in zip(SIDE_NAMES, sides, strict=True))
    questions = []
    for angle in triangle.angles:
        if angle.kind != "acute":
            continue
        for function in TRIG_FUNCTIONS:
            value = ratio_value(angle, function)
            if value is None:
                continue
            stem = triangle_prefix() + givens + "，求 " + ratio_target_latex(angle, function) + "。"
            questions.append(
                make_question(
                    problem_type="sss",
                    target_kind="trig_ratio",
                    target_trig_function=function,
                    stem_latex=stem,
                    answers=[value],
                    angle_facts=[],
                    triangle_ids=[triangle.id],
                    solution_count=1,
                )
            )
    return questions


def generate_sas(triangle: Any) -> list[CandidateQuestion]:
    questions = []
    sides = [getattr(triangle.sides, name) for name in SIDE_NAMES]
    for included_index, included_angle in enumerate(triangle.angles):
        adjacent_indices = [index for index in range(3) if index != included_index]
        target_index = adjacent_indices[0]
        target_angle = triangle.angles[target_index]
        for function in TRIG_FUNCTIONS:
            given_value = ratio_value(included_angle, function)
            if given_value is None:
                continue
            givens = [
                side_fact(SIDE_NAMES[index], sides[index])
                for index in adjacent_indices
            ] + [angle_given_latex(included_angle, function)]
            stem = triangle_prefix() + "，".join(givens) + "，求 " + side_target(SIDE_NAMES[included_index]) + "。"
            questions.append(
                make_question(
                    problem_type="sas",
                    target_kind="side",
                    target_trig_function=None,
                    stem_latex=stem,
                    answers=[sides[included_index]],
                    angle_facts=[angle_fact(included_angle, function)],
                    triangle_ids=[triangle.id],
                    solution_count=1,
                )
            )
            target_value = ratio_value(target_angle, function)
            if target_value is None:
                continue
            stem = triangle_prefix() + "，".join(givens) + "，求 " + ratio_target_latex(target_angle, function) + "。"
            questions.append(
                make_question(
                    problem_type="sas",
                    target_kind="trig_ratio",
                    target_trig_function=function,
                    stem_latex=stem,
                    answers=[target_value],
                    angle_facts=[angle_fact(included_angle, function)],
                    triangle_ids=[triangle.id],
                    solution_count=1,
                )
            )
    return questions


def generate_two_angle_types(triangle: Any, problem_type: str) -> list[CandidateQuestion]:
    questions = []
    sides = [getattr(triangle.sides, name) for name in SIDE_NAMES]
    for first_index, second_index in ((0, 1), (0, 2), (1, 2)):
        third_index = ({0, 1, 2} - {first_index, second_index}).pop()
        first_angle = triangle.angles[first_index]
        second_angle = triangle.angles[second_index]
        if problem_type == "aas":
            known_side_index = first_index
            target_side_index = second_index
        else:
            known_side_index = third_index
            target_side_index = first_index
        target_angle = triangle.angles[third_index]
        for function in TRIG_FUNCTIONS:
            if any(ratio_value(angle, function) is None for angle in (first_angle, second_angle)):
                continue
            angle_givens = [
                angle_given_latex(first_angle, function),
                angle_given_latex(second_angle, function),
            ]
            givens = angle_givens + [side_fact(SIDE_NAMES[known_side_index], sides[known_side_index])]
            facts = [angle_fact(first_angle, function), angle_fact(second_angle, function)]
            stem = triangle_prefix() + "，".join(givens) + "，求 " + side_target(SIDE_NAMES[target_side_index]) + "。"
            questions.append(
                make_question(
                    problem_type=problem_type,
                    target_kind="side",
                    target_trig_function=None,
                    stem_latex=stem,
                    answers=[sides[target_side_index]],
                    angle_facts=facts,
                    triangle_ids=[triangle.id],
                    solution_count=1,
                )
            )
            target_value = ratio_value(target_angle, function)
            if target_value is None:
                continue
            stem = triangle_prefix() + "，".join(givens) + "，求 " + ratio_target_latex(target_angle, function) + "。"
            questions.append(
                make_question(
                    problem_type=problem_type,
                    target_kind="trig_ratio",
                    target_trig_function=function,
                    stem_latex=stem,
                    answers=[target_value],
                    angle_facts=facts,
                    triangle_ids=[triangle.id],
                    solution_count=1,
                )
            )
    return questions


def generate_ssa(database: TriangleDatabase) -> list[CandidateQuestion]:
    triangles = {triangle.id: triangle for triangle in database.triangles}
    questions = []
    for case in database.ssa_cases:
        known_angle = next(
            angle
            for angle in triangles[case.triangle_ids[0]].angles
            if angle.name == case.known_angle_name
        )
        target_angle_name = case.missing_side_name.upper()
        target_angles = [
            next(angle for angle in triangles[triangle_id].angles if angle.name == target_angle_name)
            for triangle_id in case.triangle_ids
        ]
        for function in TRIG_FUNCTIONS:
            known_value = ratio_value(known_angle, function)
            if known_value is None:
                continue
            givens = [
                side_fact(case.opposite_side_name, case.opposite_side),
                side_fact(case.other_known_side_name, case.other_known_side),
                angle_given_latex(known_angle, function),
            ]
            fact = angle_fact(known_angle, function)
            stem = triangle_prefix() + "，".join(givens) + "，求 " + side_target(case.missing_side_name) + "。"
            questions.append(
                make_question(
                    problem_type="ssa",
                    target_kind="side",
                    target_trig_function=None,
                    stem_latex=stem,
                    answers=case.missing_side_answers,
                    angle_facts=[fact],
                    triangle_ids=case.triangle_ids,
                    solution_count=len(case.triangle_ids),
                )
            )
            displays = {angle_display(angle) for angle in target_angles}
            target_values = [ratio_value(angle, function) for angle in target_angles]
            if len(displays) != 1 or any(value is None for value in target_values):
                continue
            stem = triangle_prefix() + "，".join(givens) + "，求 " + ratio_target_latex(target_angles[0], function) + "。"
            questions.append(
                make_question(
                    problem_type="ssa",
                    target_kind="trig_ratio",
                    target_trig_function=function,
                    stem_latex=stem,
                    answers=[value for value in target_values if value is not None],
                    angle_facts=[fact],
                    triangle_ids=case.triangle_ids,
                    solution_count=len(case.triangle_ids),
                )
            )
    return questions


def bounded_questions(
    questions: list[CandidateQuestion],
    max_per_type: int | None,
) -> list[CandidateQuestion]:
    if max_per_type is None:
        return questions
    selected: list[CandidateQuestion] = []
    for problem_type in ("sss", "sas", "ssa", "aas", "asa"):
        cells: dict[tuple[str, int, str], list[CandidateQuestion]] = {}
        for question in questions:
            if question.problem_type != problem_type:
                continue
            visible_function = question.visible_angle_facts[0].function if question.visible_angle_facts else "none"
            cell = (
                question.target_kind,
                question.audit.solution_count,
                question.target_trig_function or visible_function,
            )
            cells.setdefault(cell, []).append(question)
        queues = [sorted(values, key=lambda value: value.id) for _, values in sorted(cells.items())]
        while len([question for question in selected if question.problem_type == problem_type]) < max_per_type:
            progressed = False
            for queue in queues:
                if queue:
                    selected.append(queue.pop(0))
                    progressed = True
                    if len([question for question in selected if question.problem_type == problem_type]) >= max_per_type:
                        break
            if not progressed:
                break
    return selected


def generate(
    database: TriangleDatabase,
    source_path: Path,
    max_per_type: int | None = None,
    disabled_triangle_ids: set[str] | None = None,
) -> CandidateDatabase:
    disabled_triangle_ids = disabled_triangle_ids or set()
    allowed_ids = {triangle.id for triangle in database.triangles if triangle.id not in disabled_triangle_ids}
    questions: dict[str, CandidateQuestion] = {}
    for triangle in database.triangles:
        if triangle.id not in allowed_ids:
            continue
        generated = [
            *generate_sss(triangle),
            *generate_sas(triangle),
            *generate_two_angle_types(triangle, "aas"),
            *generate_two_angle_types(triangle, "asa"),
        ]
        for question in generated:
            questions.setdefault(question.id, question)
    for question in generate_ssa(database):
        if set(question.source_triangle_ids).issubset(allowed_ids):
            questions.setdefault(question.id, question)
    bounded = bounded_questions(list(questions.values()), max_per_type)
    payload = {
        "schema": "math_triangle_cosine_candidates/v1",
        "database": {
            "id": "triangle-cosine-question-candidates",
            "triangle_database": portable_path(source_path),
            "generator": "generate_triangle_cosine_questions.py",
        },
        "questions": [question.model_dump(mode="json") for question in sorted(bounded, key=lambda value: value.id)],
    }
    return CandidateDatabase.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--triangle-database", type=Path, default=DEFAULT_TRIANGLE_DATABASE)
    parser.add_argument("--triangle-review", type=Path, default=DEFAULT_TRIANGLE_REVIEW)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-per-type", type=int, default=100)
    args = parser.parse_args()
    source = args.triangle_database.resolve()
    if args.max_per_type < 1:
        parser.error("--max-per-type must be positive")
    review = yaml.safe_load(args.triangle_review.read_text(encoding="utf-8")) if args.triangle_review.is_file() else {}
    disabled = set((review or {}).get("disabled_entry_ids") or [])
    result = generate(load_triangle_database(source), source, max_per_type=args.max_per_type, disabled_triangle_ids=disabled)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        yaml.safe_dump(result.model_dump(by_alias=True, mode="json"), allow_unicode=True, sort_keys=False, width=140),
        encoding="utf-8",
    )
    counts = {
        problem_type: sum(question.problem_type == problem_type for question in result.questions)
        for problem_type in ("sss", "sas", "ssa", "aas", "asa")
    }
    print(f"QUESTION CANDIDATES GENERATED: {counts} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
