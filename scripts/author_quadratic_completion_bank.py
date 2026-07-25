#!/usr/bin/env python3
"""Author a deterministic 30-item quadratic-completion question bank."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml


SOURCE_EXPLANATION = "../../专题/2026-07-17-二次函数配方/02-student-explanation.assignment.yaml"
ASSIGNMENT_SOURCE = "../../../../专题/2026-07-17-二次函数配方/02-student-explanation.assignment.yaml"


@dataclass(frozen=True)
class Case:
    category: str
    a: Fraction
    b: Fraction | None
    c: Fraction
    radical_coefficient: Fraction | None = None
    radicand: int | None = None

    @property
    def is_radical(self) -> bool:
        return self.radical_coefficient is not None

    @property
    def b_squared(self) -> Fraction:
        if self.is_radical:
            assert self.radical_coefficient is not None and self.radicand is not None
            return self.radical_coefficient**2 * self.radicand
        assert self.b is not None
        return self.b**2

    @property
    def inner_b(self) -> Fraction:
        assert self.b is not None
        return self.b / self.a

    @property
    def inner_radical_coefficient(self) -> Fraction:
        assert self.radical_coefficient is not None
        return self.radical_coefficient / self.a

    @property
    def m(self) -> Fraction:
        assert self.b is not None
        return self.b / (2 * self.a)

    @property
    def radical_m_coefficient(self) -> Fraction:
        assert self.radical_coefficient is not None
        return self.radical_coefficient / (2 * self.a)

    @property
    def m_squared(self) -> Fraction:
        if self.is_radical:
            assert self.radicand is not None
            return self.radical_m_coefficient**2 * self.radicand
        return self.m**2

    @property
    def k(self) -> Fraction:
        return self.c - self.b_squared / (4 * self.a)


F = Fraction
CASES = [
    # 一、a=1，括号内一次项系数为偶数。
    Case("首项系数为1", F(1), F(2), F(2)),
    Case("首项系数为1", F(1), F(-4), F(3)),
    Case("首项系数为1", F(1), F(6), F(10)),
    Case("首项系数为1", F(1), F(-8), F(15)),
    Case("首项系数为1", F(1), F(10), F(24)),
    Case("首项系数为1", F(1), F(-12), F(36)),
    # 二、a!=1，b/a 为偶数。
    Case("首项系数不为1", F(2), F(8), F(5)),
    Case("首项系数不为1", F(3), F(-12), F(10)),
    Case("首项系数不为1", F(4), F(8), F(3)),
    Case("首项系数不为1", F(5), F(-20), F(15)),
    Case("首项系数不为1", F(6), F(12), F(5)),
    Case("首项系数不为1", F(10), F(-20), F(9)),
    # 三、b/a 不是偶数。
    Case("b/a不是偶数", F(3), F(5), F(2)),
    Case("b/a不是偶数", F(2), F(3), F(1)),
    Case("b/a不是偶数", F(4), F(-6), F(2)),
    Case("b/a不是偶数", F(5), F(6), F(1)),
    Case("b/a不是偶数", F(6), F(-5), F(1)),
    Case("b/a不是偶数", F(10), F(9), F(2)),
    # 四、a、b 为分数；同式分数同分母或同分子。
    Case("a、b为同分母分数", F(1, 2), F(-3, 2), F(1)),
    Case("a、b为同分母分数", F(2, 3), F(5, 3), F(1)),
    Case("a、b为同分母分数", F(3, 4), F(-5, 4), F(0)),
    Case("a、b为同分子分数", F(2, 3), F(2, 5), F(0)),
    Case("a、b为同分子分数", F(3, 4), F(-3, 5), F(0)),
    Case("a、b为同分子分数", F(5, 6), F(5, 4), F(0)),
    # 五、a 为整数，b 含根号。
    Case("a为整数、b含根号", F(2), None, F(1), F(2), 3),
    Case("a为整数、b含根号", F(3), None, F(5), F(6), 2),
    Case("a为整数、b含根号", F(4), None, F(4), F(-4), 5),
    Case("a为整数、b含根号", F(5), None, F(10), F(10), 3),
    Case("a为整数、b含根号", F(6), None, F(2), F(-6), 2),
    Case("a为整数、b含根号", F(10), None, F(12), F(10), 5),
]


DIFFICULTIES = (
    ["foundation"] * 4 + ["standard"] * 2
    + ["foundation"] * 4 + ["standard"] * 2
    + ["foundation"] * 2 + ["standard"] * 4
    + ["standard"] * 2 + ["challenge"] * 4
    + ["standard"] * 2 + ["challenge"] * 4
)
VARIATIONS = [
    "changed_numbers",
    "changed_numbers",
    "changed_representation",
    "changed_question",
    "packaged_condition",
    "partially_hidden",
]


def largest_prime_factor(value: int) -> int:
    value = abs(value)
    if value <= 1:
        return 1
    largest = 1
    divisor = 2
    while divisor * divisor <= value:
        while value % divisor == 0:
            largest = divisor
            value //= divisor
        divisor += 1
    return max(largest, value)


def assert_smooth(value: Fraction, context: str) -> None:
    for part in (value.numerator, value.denominator):
        if largest_prime_factor(part) > 5:
            raise ValueError(f"{context}: {value} contains a prime factor larger than 5")


def validate_cases() -> None:
    if len(CASES) != 30 or len(DIFFICULTIES) != 30:
        raise ValueError("the bank must contain exactly 30 cases")
    for index, case in enumerate(CASES, 1):
        for label, value in (("a", case.a), ("c", case.c), ("m^2", case.m_squared), ("k", case.k)):
            assert_smooth(value, f"Q{index:03d} {label}")
        if case.is_radical:
            assert case.radical_coefficient is not None and case.radicand is not None
            assert_smooth(case.radical_coefficient, f"Q{index:03d} radical coefficient")
            assert_smooth(case.radical_m_coefficient, f"Q{index:03d} radical m coefficient")
            if largest_prime_factor(case.radicand) > 5:
                raise ValueError(f"Q{index:03d}: radicand violates prime-factor policy")
        else:
            assert case.b is not None
            assert_smooth(case.b, f"Q{index:03d} b")
            assert_smooth(case.m, f"Q{index:03d} m")
        if 19 <= index <= 24:
            assert case.b is not None
            fractions = [value for value in (case.a, case.b, case.c) if value.denominator != 1]
            same_denominator = len({value.denominator for value in fractions}) == 1
            same_numerator = len({abs(value.numerator) for value in fractions}) == 1
            if not (same_denominator or same_numerator):
                raise ValueError(f"Q{index:03d}: source fractions are neither same-denominator nor same-numerator")


def unsigned_fraction(value: Fraction) -> str:
    value = abs(value)
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\dfrac{{{value.numerator}}}{{{value.denominator}}}"


def signed_scalar(value: Fraction) -> str:
    return ("-" if value < 0 else "") + unsigned_fraction(value)


def rational_term(value: Fraction, variable: str, leading: bool = False) -> str:
    sign = "-" if value < 0 else ("" if leading else "+")
    magnitude = abs(value)
    coefficient = "" if magnitude == 1 else unsigned_fraction(magnitude)
    return f"{sign}{coefficient}{variable}"


def radical_term(coefficient: Fraction, radicand: int, variable: str, leading: bool = False) -> str:
    sign = "-" if coefficient < 0 else ("" if leading else "+")
    magnitude = abs(coefficient)
    scalar = "" if magnitude == 1 else unsigned_fraction(magnitude)
    return rf"{sign}{scalar}\sqrt{{{radicand}}}{variable}"


def constant_term(value: Fraction) -> str:
    if value == 0:
        return ""
    return ("+" if value > 0 else "-") + unsigned_fraction(value)


def polynomial(case: Case) -> str:
    result = rational_term(case.a, "x^2", leading=True)
    if case.is_radical:
        assert case.radical_coefficient is not None and case.radicand is not None
        result += radical_term(case.radical_coefficient, case.radicand, "x")
    else:
        assert case.b is not None
        result += rational_term(case.b, "x")
    return result + constant_term(case.c)


def m_latex(case: Case) -> str:
    if case.is_radical:
        assert case.radicand is not None
        coefficient = case.radical_m_coefficient
        sign = "-" if coefficient < 0 else ""
        magnitude = abs(coefficient)
        if magnitude == 1:
            return rf"{sign}\sqrt{{{case.radicand}}}"
        if magnitude.numerator == 1:
            return rf"{sign}\dfrac{{\sqrt{{{case.radicand}}}}}{{{magnitude.denominator}}}"
        return rf"{sign}\dfrac{{{magnitude.numerator}\sqrt{{{case.radicand}}}}}{{{magnitude.denominator}}}"
    return signed_scalar(case.m)


def inner_b_latex(case: Case) -> str:
    if case.is_radical:
        assert case.radicand is not None
        coefficient = case.inner_radical_coefficient
        return radical_term(coefficient, case.radicand, "", leading=True)
    return signed_scalar(case.inner_b)


def inner_polynomial(case: Case) -> str:
    if case.is_radical:
        assert case.radicand is not None
        return "x^2" + radical_term(case.inner_radical_coefficient, case.radicand, "x")
    return "x^2" + rational_term(case.inner_b, "x")


def binomial(case: Case) -> str:
    m = m_latex(case)
    if m.startswith("-"):
        return f"x-{m[1:]}"
    return f"x+{m}"


def vertex(case: Case) -> str:
    leading = "" if case.a == 1 else unsigned_fraction(case.a)
    base = rf"{leading}\left({binomial(case)}\right)^2"
    return base + constant_term(case.k)


def factored_first_step(case: Case, lhs: str) -> str:
    a = unsigned_fraction(case.a)
    return rf"${lhs}={a}\left({inner_polynomial(case)}\right){constant_term(case.c)}$。"


def completed_inner(case: Case) -> str:
    return rf"\left({binomial(case)}\right)^2-{unsigned_fraction(case.m_squared)}"


def question_shape(index_in_category: int, expression: str, case: Case) -> tuple[str, str, str]:
    question_type = "problem" if index_in_category in {0, 1, 4} else "short_answer"
    lhs = ("y", "y", "P(x)", "f(x)", "y", "Q(x)")[index_in_category]
    return question_type, lhs, rf"将 ${lhs}={expression}$ 配方。"


def teacher_assignment(item_id: str, case: Case, index_in_category: int) -> tuple[dict[str, Any], str, str]:
    expression = polynomial(case)
    question_type, lhs, stem = question_shape(index_in_category, expression, case)
    result = vertex(case)
    answer = rf"${lhs}={result}$，其中 $m={m_latex(case)}$。"
    block = {
        "type": question_type,
        "id": item_id,
        "points": 10,
        "label": case.category,
        "stem_latex": stem,
        "answer_space": {"type": "steps", "height": "42mm", "step_count": 3},
        "answer": answer,
        "explanation": "五类系数外观不同，但始终使用同一套三步配方。",
        "solution_steps": [
            {
                "title": "提二次项系数",
                "content_latex": factored_first_step(case, lhs),
            },
            {
                "title": "写成 $x^2+2mx$ 并配方",
                "content_latex": (
                    rf"$2m={inner_b_latex(case)}$，所以 $m={m_latex(case)}$，"
                    rf"${inner_polynomial(case)}={completed_inner(case)}$。"
                ),
            },
            {
                "title": "拆中括号并合并",
                "content_latex": (
                    rf"${lhs}={unsigned_fraction(case.a)}\left[{completed_inner(case)}\right]"
                    rf"{constant_term(case.c)}={result}$。"
                ),
            },
        ],
        "teaching": {
            "teaching_goal": "用统一三步完成二次函数配方",
            "category": case.category,
            "entry_point": "factor_a_then_match_2m_then_expand_brackets",
            "number_policy": {
                "largest_prime_factor_max": 5,
                "fraction_relation": "same_denominator_or_same_numerator_within_source_expression",
            },
        },
    }
    assignment = {
        "meta": {
            "title": f"二次函数配方 · {item_id} · 教师版",
            "grade": "九年级",
            "subject": "数学",
            "total_points": 10,
            "version": "teacher",
            "show_answers": True,
            "source_artifacts": {"explanation": ASSIGNMENT_SOURCE},
        },
        "render": {"template": "exam-zh-practice", "paper_size": "a4paper"},
        "sections": [
            {
                "id": "question",
                "title": "二次函数配方",
                "type": "practice",
                "visibility": "both",
                "blocks": [block],
            }
        ],
    }
    return assignment, question_type, stem


def write_yaml(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=1000),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    validate_cases()

    slots: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for index, (case, difficulty) in enumerate(zip(CASES, DIFFICULTIES, strict=True), 1):
        item_id = f"Q{index:03d}"
        index_in_category = (index - 1) % 6
        assignment, question_type, _ = teacher_assignment(item_id, case, index_in_category)
        item_root = output / "items" / item_id
        write_yaml(item_root / "teacher.plan.assignment.yaml", assignment)
        write_yaml(item_root / "teacher.resolved.assignment.yaml", assignment)
        variation = VARIATIONS[index_in_category]
        slots.append(
            {
                "id": item_id,
                "category": case.category,
                "difficulty": difficulty,
                "training_action": "提二次项系数；写成 x^2+2mx 并配方；拆中括号并合并",
                "question_type": question_type,
                "variation_dimension": variation,
                "diagram_requirement": "none",
            }
        )
        items.append(
            {
                "id": item_id,
                "title": f"{case.category}·统一三步配方",
                "question_type": question_type,
                "difficulty": difficulty,
                "skill_tags": ["二次函数配方", case.category, "x^2+2mx"],
                "variation_dimension": variation,
                "diagram_requirement": "none",
                "student_assignment": f"items/{item_id}/student.resolved.assignment.yaml",
                "teacher_assignment": f"items/{item_id}/teacher.resolved.assignment.yaml",
                "weight": 1.0,
                "enabled": True,
            }
        )

    write_yaml(
        output / "coverage-plan.yaml",
        {
            "topic": "二次函数配方",
            "source_explanation": SOURCE_EXPLANATION,
            "target_count": 30,
            "category_distribution": {
                "首项系数为1": 6,
                "首项系数不为1": 6,
                "b/a不是偶数": 6,
                "a、b为分数": 6,
                "a为整数、b含根号": 6,
            },
            "difficulty_distribution": {"foundation": 10, "standard": 12, "challenge": 8},
            "number_policy": {
                "largest_prime_factor_max": 5,
                "fraction_relation": "同一原式中的多个分数必须同分母或同分子",
                "applies_to": "原式系数、配方中的 m、m^2 与最终常数",
            },
            "unified_method": [
                "提二次项系数",
                "写成 x^2+2mx 并配方为 (x+m)^2-m^2",
                "拆中括号并合并",
            ],
            "slots": slots,
        },
    )
    write_yaml(
        output / "question-bank.yaml",
        {
            "schema": "math_topic_question_bank/v1",
            "bank": {
                "id": "quadratic-completion-2026-07-18",
                "topic": "二次函数配方",
                "grade": "九年级",
                "subject": "数学",
                "source_explanation": SOURCE_EXPLANATION,
                "status": "ready",
                "target_count": 30,
            },
            "items": items,
        },
    )
    print(f"authored {len(items)} teacher items at {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
