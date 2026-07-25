#!/usr/bin/env python3
"""Contracts for model-specific, Wolfram-verified similarity realizations."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from training_number_contracts import ExactLength, largest_prime_factor


class SimilarityQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_angle_deg: float = Field(ge=30)
    minimum_relative_side_gap: float = Field(ge=0.1)
    inradius_circumradius_ratio: float = Field(gt=0.1)
    minimum_height_perimeter_ratio: float = Field(gt=0.08)
    wolfram_verified: Literal[True]


class SimilarityTriangleEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    number_entry_id: str = Field(min_length=1)
    number_family_id: Literal["noncoprime_radicand_pairs"]
    model: Literal["reverse_a", "butterfly", "nested"]
    source_pair_index: int = Field(ge=0, le=2)
    target_pair_index: int = Field(ge=0, le=2)
    known_target_position: Literal["small", "large"]
    known_integer: int = Field(ge=1, le=20)
    unknown_value: ExactLength
    source_values: list[ExactLength] = Field(min_length=2, max_length=2)
    target_values: list[ExactLength] = Field(min_length=2, max_length=2)
    small_triangle_sides: list[ExactLength] = Field(min_length=3, max_length=3)
    hidden_pair_index: int = Field(ge=0, le=2)
    scene_constraints: list[str] = Field(min_length=1)
    quality: SimilarityQuality

    @field_validator("scene_constraints")
    @classmethod
    def validate_scene_constraints(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("scene constraints must be unique")
        return values

    @model_validator(mode="after")
    def validate_routes_and_values(self) -> "SimilarityTriangleEntry":
        if self.source_pair_index == self.target_pair_index:
            raise ValueError("source and target pair indices must differ")
        if self.hidden_pair_index in {self.source_pair_index, self.target_pair_index}:
            raise ValueError("hidden pair index must be the remaining pair")
        if (
            self.small_triangle_sides[self.source_pair_index].normalized_pair()
            != self.source_values[0].normalized_pair()
        ):
            raise ValueError("first database value must be a side of the base triangle")
        if (
            self.small_triangle_sides[self.target_pair_index].normalized_pair()
            != self.source_values[1].normalized_pair()
        ):
            raise ValueError("second database value must be another side of the base triangle")
        expected_unknown = (
            self.target_values[1]
            if self.known_target_position == "small"
            else self.target_values[0]
        )
        if self.unknown_value.normalized_pair() != expected_unknown.normalized_pair():
            raise ValueError("unknown value does not match target pair")
        known = (
            self.target_values[0]
            if self.known_target_position == "small"
            else self.target_values[1]
        )
        if known.radicand != 1 or known.coefficient_fraction.denominator != 1:
            raise ValueError("known target value must be an integer")
        if int(known.coefficient_fraction) != self.known_integer:
            raise ValueError("known integer does not match target values")
        for value in self.source_values:
            if value.coefficient_fraction.denominator != 1:
                raise ValueError("database source values cannot contain fractional coefficients")
            if max(
                largest_prime_factor(value.coefficient_fraction.numerator),
                largest_prime_factor(value.radicand),
            ) > 5:
                raise ValueError("database source value contains a prime factor above five")
        if max(
            largest_prime_factor(known.coefficient_fraction.numerator),
            largest_prime_factor(known.radicand),
        ) > 5:
            raise ValueError("known target integer contains a prime factor above five")
        for value in self.small_triangle_sides:
            if max(
                largest_prime_factor(value.coefficient_fraction.numerator),
                largest_prime_factor(value.coefficient_fraction.denominator),
                largest_prime_factor(value.radicand),
            ) > 5:
                raise ValueError("internal construction contains a prime factor above five")
        if not self.source_values[0].squared < self.source_values[1].squared:
            raise ValueError("source values must be strictly increasing")
        if not self.target_values[0].squared < self.target_values[1].squared:
            raise ValueError("target values must be strictly increasing")
        if self.source_values[1].squared > 3 * self.source_values[0].squared:
            raise ValueError("source ratio exceeds sqrt(3)")
        if (
            self.source_values[1].squared * self.target_values[0].squared
            != self.source_values[0].squared * self.target_values[1].squared
        ):
            raise ValueError("source and target pairs do not have the same exact ratio")
        scale_squared = self.target_values[0].squared / self.source_values[0].squared
        if scale_squared > 3 or 3 * scale_squared < 1:
            raise ValueError("similarity scale must be between 1/sqrt(3) and sqrt(3)")
        return self


class SimilarityTriangleMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["similarity-triangle-realizations"]
    source_number_database_id: str
    generator: str
    maximum_realizations_per_number_model: Literal[3]


class SimilarityTriangleDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal["math_similarity_triangle_database/v1"] = Field(alias="schema")
    database: SimilarityTriangleMetadata
    entries: list[SimilarityTriangleEntry]

    @model_validator(mode="after")
    def validate_unique_and_bounded(self) -> "SimilarityTriangleDatabase":
        ids = [entry.id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("similarity realization ids must be unique")
        counts: dict[tuple[str, str], int] = {}
        for entry in self.entries:
            key = (entry.number_entry_id, entry.model)
            counts[key] = counts.get(key, 0) + 1
        if any(count > 3 for count in counts.values()):
            raise ValueError("a number/model pair has more than three realizations")
        return self
