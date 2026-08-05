#!/usr/bin/env python3
"""Exact single-surd helpers shared by the triangle cosine pipeline."""

from __future__ import annotations

import hashlib
from fractions import Fraction
from math import gcd, lcm
from typing import Iterable

import sympy as sp

from training_number_contracts import normalize_length
from triangle_cosine_contracts import ExactSurd


def fraction_latex(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return rf"\frac{{{value.numerator}}}{{{value.denominator}}}"


def exact_surd(coefficient: Fraction, radicand: int = 1) -> ExactSurd:
    coefficient, radicand = normalize_length(coefficient, radicand)
    if coefficient == 0:
        radicand = 1
    if radicand == 1:
        latex = fraction_latex(coefficient)
        display = str(coefficient)
    else:
        sign = "-" if coefficient < 0 else ""
        magnitude = abs(coefficient)
        radical = rf"\sqrt{{{radicand}}}"
        if magnitude == 1:
            latex = f"{sign}{radical}"
        elif magnitude.denominator == 1:
            latex = f"{sign}{magnitude.numerator}{radical}"
        else:
            numerator = radical if magnitude.numerator == 1 else f"{magnitude.numerator}{radical}"
            latex = rf"{sign}\frac{{{numerator}}}{{{magnitude.denominator}}}"
        display = str(sp.Rational(coefficient.numerator, coefficient.denominator) * sp.sqrt(radicand))
    return ExactSurd(
        coefficient=str(coefficient),
        radicand=radicand,
        latex=latex,
        display=display,
    )


def to_expr(value: ExactSurd | object) -> sp.Expr:
    coefficient = Fraction(str(getattr(value, "coefficient")))
    radicand = int(getattr(value, "radicand"))
    return sp.Rational(coefficient.numerator, coefficient.denominator) * sp.sqrt(radicand)


def from_expr(expression: sp.Expr) -> ExactSurd | None:
    expression = sp.sqrtdenest(sp.radsimp(sp.simplify(expression)))
    if expression == 0:
        return exact_surd(Fraction(0))
    coefficient, remainder = expression.as_coeff_Mul(rational=True)
    if not coefficient.is_Rational:
        return None
    rational = Fraction(int(coefficient.p), int(coefficient.q))
    if remainder == 1:
        return exact_surd(rational)
    if remainder.func is sp.Pow and remainder.exp == sp.Rational(1, 2):
        radicand = remainder.base
        if radicand.is_Integer and int(radicand) > 0:
            return exact_surd(rational, int(radicand))
    return None


def normalize_side_ratio(expressions: Iterable[sp.Expr]) -> list[ExactSurd] | None:
    values = [from_expr(expression) for expression in expressions]
    if any(value is None for value in values):
        return None
    exact_values = [value for value in values if value is not None]
    denominator_lcm = lcm(*(value.coefficient_fraction.denominator for value in exact_values))
    integer_coefficients = [
        abs(value.coefficient_fraction.numerator)
        * (denominator_lcm // value.coefficient_fraction.denominator)
        for value in exact_values
    ]
    common = gcd(*integer_coefficients)
    scale = sp.Rational(denominator_lcm, common)
    normalized = [from_expr(to_expr(value) * scale) for value in exact_values]
    if any(value is None for value in normalized):
        return None
    return [value for value in normalized if value is not None]


def expression_key(expression: sp.Expr) -> str:
    return sp.srepr(sp.sqrtdenest(sp.radsimp(sp.simplify(expression))))


def stable_digest(*parts: object, length: int = 12, upper: bool = False) -> str:
    rendered = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()[:length]
    return digest.upper() if upper else digest
