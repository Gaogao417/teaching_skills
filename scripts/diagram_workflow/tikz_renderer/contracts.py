from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from diagram_contracts import DiagramModel, DiagramVariant, JsonObject, NonEmptyStr


class TikzCoordinate(DiagramModel):
    name: NonEmptyStr
    x: float
    y: float
    source_x: float | None = None
    source_y: float | None = None


class TikzStyleRole(DiagramModel):
    name: NonEmptyStr
    options: str


class TikzCommand(DiagramModel):
    kind: NonEmptyStr
    order: int = 0
    tex: NonEmptyStr


class TikzCompilerAudit(DiagramModel):
    bbox_source: JsonObject = Field(default_factory=dict)
    natural_width_cm: float = Field(default=0, ge=0)
    natural_height_cm: float = Field(default=0, ge=0)
    coordinate_count: int = Field(default=0, ge=0)
    command_count: int = Field(default=0, ge=0)
    point_label_count: int = Field(default=0, ge=0)
    condition_label_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class TikzDiagramSpec(DiagramModel):
    schema_version: Literal["tikz-diagram-spec/v1"] = "tikz-diagram-spec/v1"
    job_id: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    diagram_type: str = "synthetic_geometry"
    libraries: list[str] = Field(default_factory=list)
    natural_width_cm: float = Field(gt=0)
    natural_height_cm: float = Field(gt=0)
    styles: list[TikzStyleRole] = Field(default_factory=list)
    coordinates: list[TikzCoordinate] = Field(default_factory=list)
    commands: list[TikzCommand] = Field(default_factory=list)
    audit: TikzCompilerAudit = Field(default_factory=TikzCompilerAudit)

    @model_validator(mode="after")
    def validate_commands(self) -> TikzDiagramSpec:
        if not self.commands:
            raise ValueError("TikzDiagramSpec requires at least one generated command")
        return self
