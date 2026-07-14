#!/usr/bin/env python3
"""Pydantic contracts and exact checks for training-number databases."""

from __future__ import annotations

from fractions import Fraction
from math import gcd, isqrt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RIGHT_TRIANGLE_FAMILIES = {
    "right_triangle_integer_triples",
    "right_triangle_special_angles",
    "right_triangle_sqrt_square_sums",
    "integer_right_triangles_fraction_scaled",
    "radical_right_triangles_simple_scaled",
}
SCALED_RIGHT_TRIANGLE_FAMILIES = {
    "integer_right_triangles_fraction_scaled",
    "radical_right_triangles_simple_scaled",
}


def parse_fraction(value: str) -> Fraction:
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"invalid exact rational {value!r}") from exc


def squarefree(value: int) -> bool:
    factor = 2
    while factor * factor <= value:
        if value % (factor * factor) == 0:
            return False
        factor += 1
    return True


def largest_prime_factor(value: int) -> int:
    value = abs(value)
    if value <= 1:
        return 1
    largest = 1
    factor = 2
    while factor * factor <= value:
        while value % factor == 0:
            largest = factor
            value //= factor
        factor += 1
    return max(largest, value)


def normalize_length(coefficient: Fraction, radicand: int) -> tuple[Fraction, int]:
    outside = 1
    remaining = radicand
    factor = 2
    while factor * factor <= remaining:
        while remaining % (factor * factor) == 0:
            outside *= factor
            remaining //= factor * factor
        factor += 1
    return coefficient * outside, remaining


class ExactLength(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coefficient: str
    radicand: int = Field(ge=1)
    latex: str = Field(min_length=1)
    display: str = Field(min_length=1)

    @field_validator("coefficient")
    @classmethod
    def validate_coefficient(cls, value: str) -> str:
        parsed = parse_fraction(value)
        if parsed <= 0:
            raise ValueError("length coefficient must be positive")
        return value

    @model_validator(mode="after")
    def validate_normal_form(self) -> "ExactLength":
        if not squarefree(self.radicand):
            raise ValueError(f"radicand {self.radicand} is not squarefree")
        return self

    @property
    def coefficient_fraction(self) -> Fraction:
        return parse_fraction(self.coefficient)

    @property
    def squared(self) -> Fraction:
        return self.coefficient_fraction**2 * self.radicand

    def multiply(self, other: "ExactLength") -> tuple[Fraction, int]:
        return normalize_length(
            self.coefficient_fraction * other.coefficient_fraction,
            self.radicand * other.radicand,
        )

    def normalized_pair(self) -> tuple[Fraction, int]:
        return self.coefficient_fraction, self.radicand


class TrainingNumberEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9-]*$")
    family: str = Field(min_length=1)
    label: str = Field(min_length=1)
    values: list[ExactLength] = Field(min_length=2, max_length=3)
    relation: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("tags must be unique")
        if any(not value.strip() for value in values):
            raise ValueError("tags cannot contain blanks")
        return values

    @model_validator(mode="after")
    def validate_math_relation(self) -> "TrainingNumberEntry":
        if self.family in RIGHT_TRIANGLE_FAMILIES:
            if len(self.values) != 3:
                raise ValueError("right-triangle entry requires three lengths")
            if self.values[0].squared + self.values[1].squared != self.values[2].squared:
                raise ValueError("right-triangle entry fails the Pythagorean identity")
        elif len(self.values) != 2:
            raise ValueError("pair family requires two lengths")

        if self.family == "rational_multiple_pairs":
            if any(value.radicand != 1 for value in self.values):
                raise ValueError("rational pair cannot contain a radical")
            multiplier = parse_fraction(str(self.parameters.get("multiplier", "")))
            if multiplier.denominator != 1 or multiplier <= 1:
                raise ValueError("rational pair multiplier must be an integer above one")
            first, second = self.values
            if first.coefficient_fraction * multiplier != second.coefficient_fraction:
                raise ValueError("rational multiplier does not reproduce the second value")
            for value in self.values:
                rational = value.coefficient_fraction
                if max(
                    largest_prime_factor(rational.numerator),
                    largest_prime_factor(rational.denominator),
                ) > 7:
                    raise ValueError("rational length contains a prime factor above seven")

        if self.family == "radical_multiple_pairs":
            a = int(self.parameters.get("a", 0))
            k = int(self.parameters.get("k", 0))
            expected_first = normalize_length(Fraction(1), a)
            expected_second = normalize_length(Fraction(1), a * k)
            if self.values[0].normalized_pair() != expected_first:
                raise ValueError("first radical is not normalized sqrt(a)")
            if self.values[1].normalized_pair() != expected_second:
                raise ValueError("second radical is not normalized sqrt(k*a)")

        if self.family == "noncoprime_radicand_pairs":
            a = int(self.parameters.get("a", 0))
            b = int(self.parameters.get("b", 0))
            if gcd(a, b) <= 1:
                raise ValueError("source radicands must not be coprime")

        if self.family == "right_triangle_sqrt_square_sums":
            squares = self.parameters.get("squared_lengths")
            if not isinstance(squares, list) or len(squares) != 3:
                raise ValueError("sqrt-square entry requires three source squared lengths")
            if not all(isinstance(value, int) and 1 <= value <= 20 for value in squares):
                raise ValueError("source squared lengths must be integers in 1..20")
            if squares[0] + squares[1] != squares[2]:
                raise ValueError("source squared lengths do not satisfy x+y=z")
            if any(value.radicand >= 10 for value in self.values):
                raise ValueError("simplified radicands must be below 10")
        return self


class TrainingNumberFamily(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    entries: list[TrainingNumberEntry]

    @model_validator(mode="after")
    def validate_entries(self) -> "TrainingNumberFamily":
        ids = [entry.id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError(f"family {self.id} has duplicate entry ids")
        mismatches = [entry.id for entry in self.entries if entry.family != self.id]
        if mismatches:
            raise ValueError(f"entries use wrong family id: {mismatches[:3]}")
        return self


class TrainingNumberMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    generator: str = Field(min_length=1)
    bounds: dict[str, int]


class TrainingNumberDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_training_number_database/v1"] = Field(alias="schema")
    database: TrainingNumberMetadata
    families: list[TrainingNumberFamily] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_database(self) -> "TrainingNumberDatabase":
        family_ids = [family.id for family in self.families]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("family ids must be unique")

        entries = [entry for family in self.families for entry in family.entries]
        entry_ids = [entry.id for entry in entries]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("entry ids must be globally unique")

        entries_by_id = {entry.id: entry for entry in entries}
        for entry in entries:
            if entry.family not in SCALED_RIGHT_TRIANGLE_FAMILIES:
                continue
            base_id = entry.parameters.get("base_entry_id")
            scale_payload = entry.parameters.get("scale")
            if not isinstance(base_id, str) or base_id not in entries_by_id:
                raise ValueError(f"{entry.id}: unknown base_entry_id {base_id!r}")
            scale = ExactLength.model_validate(scale_payload)
            base = entries_by_id[base_id]
            if len(base.values) != 3:
                raise ValueError(f"{entry.id}: scaled base must have three lengths")
            expected = [value.multiply(scale) for value in base.values]
            actual = [value.normalized_pair() for value in entry.values]
            if expected != actual:
                raise ValueError(f"{entry.id}: scaled values do not match base and scale")

            numerator = scale.coefficient_fraction.numerator
            denominator = scale.coefficient_fraction.denominator
            if max(largest_prime_factor(numerator), largest_prime_factor(denominator)) > 7:
                raise ValueError(f"{entry.id}: scale coefficient has a prime factor above seven")

            if entry.family == "integer_right_triangles_fraction_scaled":
                if scale.radicand != 1:
                    raise ValueError(f"{entry.id}: integer base cannot receive a radical scale")
                if numerator > 7 or denominator > 7 or denominator == 1:
                    raise ValueError(f"{entry.id}: fraction scale must use p/q with p<=7 and 2<=q<=7")
                if any(value.radicand != 1 for value in base.values):
                    raise ValueError(f"{entry.id}: integer-scaled family requires an integer base")

            if entry.family == "radical_right_triangles_simple_scaled":
                base_radicands = {value.radicand for value in base.values if value.radicand > 1}
                if not base_radicands:
                    raise ValueError(f"{entry.id}: radical-scaled family requires a radical base")
                if scale.radicand == 1:
                    if numerator > 7 or denominator > 7 or denominator == 1:
                        raise ValueError(f"{entry.id}: fraction scale must use p/q with p<=7 and 2<=q<=7")
                else:
                    if scale.radicand not in base_radicands:
                        raise ValueError(f"{entry.id}: radical scale must match a base radicand")
                    allowed_coefficients = {Fraction(1), Fraction(1, scale.radicand)}
                    if scale.coefficient_fraction not in allowed_coefficients:
                        raise ValueError(f"{entry.id}: radical scale is not simple")
        return self

    @property
    def entry_count(self) -> int:
        return sum(len(family.entries) for family in self.families)

    def entries_by_id(self) -> dict[str, TrainingNumberEntry]:
        return {
            entry.id: entry
            for family in self.families
            for entry in family.entries
        }


class TrainingNumberReview(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_training_number_review/v1"] = Field(alias="schema")
    database_id: str = Field(min_length=1)
    disabled_entry_ids: list[str] = Field(default_factory=list)
    retired_entry_ids: list[str] = Field(default_factory=list)
    updated_at: str = ""

    @field_validator("disabled_entry_ids")
    @classmethod
    def validate_disabled_ids(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("disabled_entry_ids must be unique")
        return values

    @model_validator(mode="after")
    def validate_review_sets(self) -> "TrainingNumberReview":
        overlap = set(self.disabled_entry_ids) & set(self.retired_entry_ids)
        if overlap:
            raise ValueError(f"entry ids cannot be both disabled and retired: {sorted(overlap)[:3]}")
        return self
