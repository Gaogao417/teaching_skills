#!/usr/bin/env python3
"""Pydantic contracts for the two-stage diagram workflow.

The models in this module mirror docs/diagram-workflow-architecture.md:
assignment plan YAML declares diagram slots, the batch layer turns those slots
into single-image jobs, workflow.py executes one job, renderer produces images,
and resolver binds artifacts back into assignment.resolved.yaml.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Annotated, Literal, TypeAlias

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator


NonEmptyStr = Annotated[str, Field(min_length=1)]
JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = object
JsonObject: TypeAlias = dict[str, object]
Point2D: TypeAlias = tuple[float, float]
Point3D: TypeAlias = tuple[float, float, float]
TikzAnchor: TypeAlias = Literal[
    "",
    "center",
    "north",
    "south",
    "east",
    "west",
    "north east",
    "north west",
    "south east",
    "south west",
]
MIN_FUNCTION_SAMPLE_COUNT = 80


class DiagramVariant(str, Enum):
    PROMPT = "prompt"
    SOLUTION = "solution"


class DisclosurePolicy(str, Enum):
    CLEAN = "clean"
    ANNOTATED = "annotated"


class DiagramEngine(str, Enum):
    GEOMETRIC_SCENE = "geometric_scene"
    WOLFRAM_CLIENT = "wolfram_client"
    WOLFRAM_PLOT = "wolfram_plot"
    COORDINATE_RENDERER = "coordinate_renderer"
    SPATIAL_RENDERER = "spatial_renderer"
    RENDERER_SPEC = "renderer_spec"


class DiagramArtifactKind(str, Enum):
    TIKZ = "tikz"


class TikzSourceMode(str, Enum):
    INLINE_FRAGMENT = "inline_fragment"
    SOURCE_FILE = "source_file"


class TikzCompileEngine(str, Enum):
    NONE = "none"
    TECTONIC = "tectonic"
    XELATEX = "xelatex"
    PDFLATEX = "pdflatex"


class TikzExportTool(str, Enum):
    NONE = "none"
    PDFTOCAIRO = "pdftocairo"
    DVISVGM = "dvisvgm"


class DiagramKind(str, Enum):
    SYNTHETIC_GEOMETRY = "synthetic_geometry"
    COORDINATE_GEOMETRY = "coordinate_geometry"
    SPATIAL_GEOMETRY = "spatial_geometry"
    FUNCTION_GRAPH = "function_graph"
    HYBRID = "hybrid"
    AUTO = "auto"


class SpatialProjectionMode(str, Enum):
    """Printed projection families for solid-geometry diagrams."""

    TEXTBOOK_OBLIQUE = "textbook_oblique"
    HINGE_PLANES = "hinge_planes"
    ORTHOGRAPHIC_3D = "orthographic_3d"
    AXIAL_SOLID = "axial_solid"


class SpatialObjectRole(str, Enum):
    MAIN = "main"
    SECONDARY = "secondary"
    AUXILIARY = "auxiliary"
    HIDDEN = "hidden"
    INTERSECTION = "intersection"
    PROJECTION = "projection"


class DiagramOnFailure(str, Enum):
    FAIL_ASSIGNMENT = "fail_assignment"
    OMIT_DIAGRAM = "omit_diagram"
    TEXTUAL_FALLBACK = "textual_fallback"


class DiagramLayoutRole(str, Enum):
    QUESTION_SIDECAR = "question_sidecar"
    ANSWER_AREA_SIDECAR = "answer_area_sidecar"
    DIAGRAM_ROW_ITEM = "diagram_row_item"
    CENTER_BLOCK = "center_block"
    SOLUTION_ANNOTATION = "solution_annotation"


class DiagramOrientation(str, Enum):
    AUTO = "auto"
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


class DiagramDisplayProfile(str, Enum):
    AUTO = "auto"
    WORKSHEET_GEOMETRY_SIDECAR = "worksheet_geometry_sidecar"
    WORKSHEET_GEOMETRY_CENTER = "worksheet_geometry_center"


class DiagramBodyScale(str, Enum):
    NORMAL = "normal"
    LARGE = "large"


class DiagramLabelDensity(str, Enum):
    NORMAL = "normal"
    DENSE = "dense"


class DiagramLabelPlacement(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    LEFT = "left"
    RIGHT = "right"
    ABOVE_LEFT = "above left"
    ABOVE_RIGHT = "above right"
    BELOW_LEFT = "below left"
    BELOW_RIGHT = "below right"
    CENTER = "center"


class DiagramConditionLabelStyle(str, Enum):
    VALUE_ONLY = "value_only"
    FULL = "full"


class DiagramRunStatus(str, Enum):
    PLANNED = "planned"
    COLLECTED = "collected"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"
    BOUND = "bound"


class DiagramSlotStatus(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    FAILED = "failed"
    OMITTED = "omitted"
    FALLBACK = "fallback"
    BLOCKED = "blocked"


class DiagramModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class DiagramLooseModel(BaseModel):
    """Contract for external tool outputs that may carry extra diagnostic fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


_LATEX_DIMENSION_PATTERN = re.compile(
    r"^\s*(?:"
    r"(?:\d+(?:\.\d+)?|\.\d+)\s*(?:mm|cm|pt|in)"
    r"|(?:\d+(?:\.\d+)?|\.\d+)?\s*\\linewidth"
    r"|\\linewidth"
    r")\s*$"
)


def validate_latex_dimension(value: str, *, field_name: str) -> str:
    if not value:
        return value
    if not _LATEX_DIMENSION_PATTERN.match(value):
        raise ValueError(
            f"{field_name} must be a TeX dimension in mm/cm/pt/in or a \\linewidth expression"
        )
    return value


class DiagramNumericDomain(DiagramModel):
    min: float
    max: float

    @model_validator(mode="after")
    def validate_order(self) -> DiagramNumericDomain:
        if self.min >= self.max:
            raise ValueError("domain min must be < max")
        return self


class DiagramCoordinateViewport(DiagramModel):
    x_min: float | None = None
    x_max: float | None = None
    y_min: float | None = None
    y_max: float | None = None
    preserve_aspect: bool = True
    padding_ratio: float = Field(default=0.08, ge=0, le=0.5)

    @model_validator(mode="after")
    def validate_viewport_pairs(self) -> DiagramCoordinateViewport:
        pairs = (("x_min", "x_max"), ("y_min", "y_max"))
        for low_name, high_name in pairs:
            low = getattr(self, low_name)
            high = getattr(self, high_name)
            if (low is None) != (high is None):
                raise ValueError(f"{low_name} and {high_name} must be provided together")
            if low is not None and high is not None and low >= high:
                raise ValueError(f"{low_name} must be < {high_name}")
        return self


class DiagramAxisTickLabel(DiagramModel):
    value: float
    label: str = ""
    at: Point2D | None = Field(default=None, validation_alias=AliasChoices("at", "label_at"))
    anchor: TikzAnchor = ""
    dx_pt: float | None = Field(default=None, validation_alias=AliasChoices("dx_pt", "dx"))
    dy_pt: float | None = Field(default=None, validation_alias=AliasChoices("dy_pt", "dy"))
    show: bool = True


class DiagramAxesSpec(DiagramModel):
    x: bool = True
    y: bool = True
    grid: bool = True
    show_ticks: bool = True
    x_label: str = "x"
    y_label: str = "y"
    x_tick_step: float | None = Field(default=None, gt=0)
    y_tick_step: float | None = Field(default=None, gt=0)
    x_ticks: list[float] | None = Field(default=None, validation_alias=AliasChoices("x_ticks", "x_tick_values"))
    y_ticks: list[float] | None = Field(default=None, validation_alias=AliasChoices("y_ticks", "y_tick_values"))
    x_tick_labels: list[DiagramAxisTickLabel] = Field(default_factory=list)
    y_tick_labels: list[DiagramAxisTickLabel] = Field(default_factory=list)

    @field_validator("x_ticks", "y_ticks")
    @classmethod
    def validate_unique_tick_values(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("tick value list must not be empty")
        normalized = [float(item) for item in value]
        if len(set(normalized)) != len(normalized):
            raise ValueError("tick values must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_unique_manual_tick_labels(self) -> DiagramAxesSpec:
        for axis, labels in (("x", self.x_tick_labels), ("y", self.y_tick_labels)):
            values = [float(item.value) for item in labels if item.show]
            if len(set(values)) != len(values):
                raise ValueError(f"{axis}_tick_labels values must be unique")
        return self


class DiagramFunctionSpec(DiagramModel):
    id: NonEmptyStr
    variable: str = "x"
    expression_latex: str = ""
    expression_wl: str = ""
    domain: DiagramNumericDomain | None = None
    label: str = ""
    sample_count: int = Field(default=160, ge=MIN_FUNCTION_SAMPLE_COUNT)
    style: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_expression(self) -> DiagramFunctionSpec:
        if not self.expression_latex and not self.expression_wl:
            raise ValueError("function specs require expression_latex or expression_wl")
        return self


class CoordinatePoint(DiagramModel):
    type: Literal["point"] = "point"
    id: NonEmptyStr
    x: float
    y: float
    label: str = ""
    style: JsonObject = Field(default_factory=dict)

    def render_object(self) -> JsonObject:
        return self.model_dump(mode="json")


class CoordinateLine(DiagramModel):
    type: Literal["line"] = "line"
    id: NonEmptyStr
    equation: str = ""
    slope: float | None = None
    intercept: float | None = None
    label: str = ""
    style: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_line_definition(self) -> CoordinateLine:
        if not self.equation and (self.slope is None or self.intercept is None):
            raise ValueError("line objects require equation or slope/intercept")
        return self

    def render_object(self) -> JsonObject:
        payload = self.model_dump(mode="json", exclude_none=True)
        if not payload.get("label"):
            payload.pop("label", None)
        return payload


class CoordinateSegment(DiagramModel):
    type: Literal["segment"] = "segment"
    id: NonEmptyStr
    start: str | Point2D = Field(validation_alias=AliasChoices("from", "start", "a"), serialization_alias="from")
    end: str | Point2D = Field(validation_alias=AliasChoices("to", "end", "b"), serialization_alias="to")
    label: str = ""
    style: JsonObject = Field(default_factory=dict)

    def render_object(self) -> JsonObject:
        return {
            "type": "polyline",
            "id": self.id,
            "points": [
                self.start if isinstance(self.start, str) else list(self.start),
                self.end if isinstance(self.end, str) else list(self.end),
            ],
            "style": self.style,
        }


class CoordinatePolyline(DiagramModel):
    type: Literal["polyline"] = "polyline"
    id: NonEmptyStr
    points: list[str | Point2D] = Field(min_length=2)
    style: JsonObject = Field(default_factory=dict)
    purpose: Literal["explicit_polyline", "sample_trace"] = "explicit_polyline"

    def render_object(self) -> JsonObject:
        return {
            "type": "polyline",
            "id": self.id,
            "points": [point if isinstance(point, str) else list(point) for point in self.points],
            "style": self.style,
        }


class CoordinatePolygonRegion(DiagramModel):
    type: Literal["polygon_region"] = "polygon_region"
    id: NonEmptyStr
    points: list[str | Point2D] = Field(min_length=3)
    label: str = ""
    style: JsonObject = Field(default_factory=dict)

    def render_object(self) -> JsonObject:
        return {
            "type": "polygon",
            "id": self.id,
            "points": [point if isinstance(point, str) else list(point) for point in self.points],
            "label": self.label,
            "style": self.style,
        }


class CoordinateCircle(DiagramModel):
    type: Literal["circle"] = "circle"
    id: NonEmptyStr
    center: str | Point2D | JsonObject
    radius: float = Field(gt=0)
    label: str = ""
    style: JsonObject = Field(default_factory=dict)

    def render_object(self) -> JsonObject:
        center: object = self.center
        if isinstance(center, tuple):
            center = list(center)
        return {
            "type": "circle",
            "id": self.id,
            "center": center,
            "radius": self.radius,
            "label": self.label,
            "style": self.style,
        }


class CoordinateGuideLine(DiagramModel):
    type: Literal["guide_line"] = "guide_line"
    id: NonEmptyStr
    equation: str = ""
    slope: float | None = None
    intercept: float | None = None
    style: JsonObject = Field(default_factory=lambda: {"dash": "5 4"})

    @model_validator(mode="after")
    def require_guide_definition(self) -> CoordinateGuideLine:
        if not self.equation and (self.slope is None or self.intercept is None):
            raise ValueError("guide_line objects require equation or slope/intercept")
        return self

    def render_object(self) -> JsonObject:
        payload: JsonObject = {
            "type": "line",
            "id": self.id,
            "style": self.style,
        }
        if self.equation:
            payload["equation"] = self.equation
        else:
            payload["slope"] = self.slope
            payload["intercept"] = self.intercept
        return payload


class CoordinateProjectionLabelStyle(DiagramModel):
    show: bool = True
    label: str = ""
    at: Point2D | None = Field(default=None, validation_alias=AliasChoices("at", "label_at"))
    anchor: TikzAnchor = ""
    dx_pt: float | None = Field(default=None, validation_alias=AliasChoices("dx_pt", "dx"))
    dy_pt: float | None = Field(default=None, validation_alias=AliasChoices("dy_pt", "dy"))


class CoordinateProjectionGuide(DiagramModel):
    type: Literal["projection_guide"] = "projection_guide"
    id: NonEmptyStr
    point: str = Field(validation_alias=AliasChoices("point", "from", "source"))
    to_axis: Literal["x", "y"]
    style: JsonObject = Field(default_factory=lambda: {"dash": "5 4"})
    label_style: CoordinateProjectionLabelStyle = Field(default_factory=CoordinateProjectionLabelStyle)
    show_axis_tick: bool = True

    def render_object(self) -> JsonObject:
        return {
            "type": "projection_guide",
            "id": self.id,
            "point": self.point,
            "to_axis": self.to_axis,
            "style": self.style,
            "label_style": self.label_style.model_dump(mode="json", exclude_none=True),
            "show_axis_tick": self.show_axis_tick,
        }


class CoordinateTextLabel(DiagramModel):
    type: Literal["text_label"] = "text_label"
    id: str = ""
    text: NonEmptyStr
    x: float
    y: float
    style: JsonObject = Field(default_factory=dict)

    def render_object(self) -> JsonObject:
        return {
            "type": "text",
            "id": self.id,
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "style": self.style,
        }


class CoordinateFunctionCurve(DiagramModel):
    type: Literal["function_curve"] = "function_curve"
    id: NonEmptyStr
    variable: str = "x"
    expression_latex: str = ""
    expression_wl: str = ""
    domain_segments: list[DiagramNumericDomain] = Field(default_factory=list, min_length=1)
    label: str = ""
    sample_count: int = Field(default=160, ge=MIN_FUNCTION_SAMPLE_COUNT)
    style_role: str = "function"
    style: JsonObject = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_domain(cls, value: object) -> object:
        if isinstance(value, dict):
            payload = dict(value)
            if "domain_segments" not in payload and "domain" in payload:
                payload["domain_segments"] = [payload.pop("domain")]
            return payload
        return value

    @model_validator(mode="after")
    def require_function_payload(self) -> CoordinateFunctionCurve:
        if not self.expression_latex and not self.expression_wl:
            raise ValueError("function_curve objects require expression_latex or expression_wl")
        if not self.domain_segments:
            raise ValueError("function_curve objects require domain_segments")
        return self

    def function_specs(self) -> list[DiagramFunctionSpec]:
        specs: list[DiagramFunctionSpec] = []
        multi_segment = len(self.domain_segments) > 1
        for index, domain in enumerate(self.domain_segments, start=1):
            specs.append(
                DiagramFunctionSpec(
                    id=self.id if not multi_segment else f"{self.id}__seg{index}",
                    variable=self.variable,
                    expression_latex=self.expression_latex,
                    expression_wl=self.expression_wl,
                    domain=domain,
                    label=self.label if index == 1 else "",
                    sample_count=self.sample_count,
                    style=self.style,
                )
            )
        return specs

    def compute_function_spec(self) -> DiagramFunctionSpec:
        return DiagramFunctionSpec(
            id=self.id,
            variable=self.variable,
            expression_latex=self.expression_latex,
            expression_wl=self.expression_wl,
            domain=self.domain_segments[0],
            label=self.label,
            sample_count=self.sample_count,
            style=self.style,
        )


class CoordinateDerivedPoint(DiagramModel):
    type: Literal["derived_point"] = "derived_point"
    id: NonEmptyStr
    derive: Literal["intersection", "zero", "root", "x_intercept"]
    of: str | list[str]
    label: str = ""
    style: JsonObject = Field(default_factory=dict)

    def compute_object(self) -> JsonObject:
        kind = "intersection" if self.derive == "intersection" else self.derive
        return {
            "type": kind,
            "id": self.id,
            "of": self.of,
            "label": self.label,
            "style": self.style,
        }


CoordinateObject: TypeAlias = Annotated[
    CoordinatePoint
    | CoordinateFunctionCurve
    | CoordinateLine
    | CoordinateSegment
    | CoordinatePolygonRegion
    | CoordinateDerivedPoint
    | CoordinateGuideLine
    | CoordinateProjectionGuide
    | CoordinateTextLabel
    | CoordinateCircle
    | CoordinatePolyline,
    Field(discriminator="type"),
]


def _object_refs(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return []


class CoordinateDiagramIR(DiagramModel):
    """Typed plan/request IR for coordinate-plane diagrams."""

    viewport: DiagramCoordinateViewport = Field(default_factory=DiagramCoordinateViewport)
    axes: DiagramAxesSpec = Field(default_factory=DiagramAxesSpec)
    objects: list[CoordinateObject] = Field(default_factory=list)
    annotations: list[JsonObject] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_object_references(self) -> CoordinateDiagramIR:
        if not self.viewport.preserve_aspect:
            raise ValueError("coordinate diagram IR requires viewport.preserve_aspect=true")
        known: set[str] = set()
        for obj in self.objects:
            obj_id = getattr(obj, "id", "")
            if obj_id:
                if obj_id in known:
                    raise ValueError(f"coordinate object id must be unique: {obj_id}")
                known.add(obj_id)

        function_ids = {obj.id for obj in self.objects if isinstance(obj, CoordinateFunctionCurve)}
        for obj in self.objects:
            refs: list[str] = []
            if isinstance(obj, CoordinateSegment):
                refs.extend(_object_refs(obj.start))
                refs.extend(_object_refs(obj.end))
            elif isinstance(obj, CoordinatePolyline):
                for point in obj.points:
                    refs.extend(_object_refs(point))
            elif isinstance(obj, CoordinatePolygonRegion):
                for point in obj.points:
                    refs.extend(_object_refs(point))
            elif isinstance(obj, CoordinateCircle):
                refs.extend(_object_refs(obj.center))
            elif isinstance(obj, CoordinateProjectionGuide):
                refs.append(obj.point)
            elif isinstance(obj, CoordinateDerivedPoint):
                refs.extend(_object_refs(obj.of))
                if obj.derive != "intersection":
                    ref = refs[0] if refs else ""
                    if ref not in function_ids:
                        raise ValueError(f"{obj.derive} derived_point requires a function_curve ref")
                elif len(refs) != 2:
                    raise ValueError("intersection derived_point requires exactly two object refs")

            missing = [ref for ref in refs if ref not in known]
            if missing:
                raise ValueError(f"coordinate object '{getattr(obj, 'id', '')}' references missing object(s): {missing}")
        return self

    def function_specs(self) -> list[DiagramFunctionSpec]:
        specs: list[DiagramFunctionSpec] = []
        for obj in self.objects:
            if isinstance(obj, CoordinateFunctionCurve):
                specs.extend(obj.function_specs())
        return specs

    def compute_function_specs(self) -> list[DiagramFunctionSpec]:
        return [obj.compute_function_spec() for obj in self.objects if isinstance(obj, CoordinateFunctionCurve)]

    def render_objects(self) -> list[JsonObject]:
        rendered: list[JsonObject] = []
        for obj in self.objects:
            if isinstance(obj, CoordinateFunctionCurve | CoordinateDerivedPoint):
                continue
            rendered.append(obj.render_object())
        return rendered

    def compute_objects(self) -> list[JsonObject]:
        return [obj.compute_object() for obj in self.objects if isinstance(obj, CoordinateDerivedPoint)]


class DiagramCoordinateObject(DiagramLooseModel):
    type: NonEmptyStr
    id: str = ""
    label: str = ""
    style: JsonObject = Field(default_factory=dict)


class DiagramAnalyticRequirements(DiagramModel):
    viewport: DiagramCoordinateViewport = Field(default_factory=DiagramCoordinateViewport)
    axes: DiagramAxesSpec = Field(default_factory=DiagramAxesSpec)
    coordinate_ir: CoordinateDiagramIR | None = Field(
        default=None,
        validation_alias=AliasChoices("coordinate_ir", "ir", "coordinate_diagram"),
    )
    functions: list[DiagramFunctionSpec] = Field(default_factory=list)
    objects: list[DiagramCoordinateObject] = Field(default_factory=list)
    annotations: list[JsonObject] = Field(default_factory=list)
    wolfram_client_options: JsonObject = Field(default_factory=dict)
    wolfram_plot_options: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_plot_options(self) -> DiagramAnalyticRequirements:
        if not self.wolfram_client_options and self.wolfram_plot_options:
            self.wolfram_client_options = dict(self.wolfram_plot_options)
        if self.coordinate_ir is None and (self.functions or self.objects):
            self.coordinate_ir = CoordinateDiagramIR(
                viewport=self.viewport,
                axes=self.axes,
                objects=_legacy_coordinate_objects(self.functions, self.objects),
                annotations=self.annotations,
            )
        if self.coordinate_ir is not None:
            self.viewport = self.coordinate_ir.viewport
            self.axes = self.coordinate_ir.axes
        return self


def _legacy_coordinate_objects(
    functions: list[DiagramFunctionSpec],
    objects: list[DiagramCoordinateObject],
) -> list[CoordinateObject]:
    converted: list[object] = []
    for func in functions:
        payload = func.model_dump(mode="json", exclude_none=True)
        payload["type"] = "function_curve"
        if "domain" in payload:
            payload["domain_segments"] = [payload.pop("domain")]
        converted.append(payload)
    for obj in objects:
        data = obj.model_dump(mode="json", by_alias=True)
        if not data.get("label"):
            data.pop("label", None)
        kind = data.get("type")
        if kind in {"point", "line", "function_curve", "guide_line", "circle", "polyline"}:
            converted.append(data)
        elif kind == "polygon":
            data["type"] = "polygon_region"
            converted.append(data)
        elif kind == "segment":
            converted.append(data)
        elif kind == "text":
            data["type"] = "text_label"
            data["text"] = data.get("text") or data.pop("label", "")
            converted.append(data)
        elif kind in {"intersection", "zero", "root", "x_intercept"}:
            data["type"] = "derived_point"
            data["derive"] = "intersection" if kind == "intersection" else kind
            converted.append(data)
        else:
            raise ValueError(f"unsupported coordinate object type in plan IR: {kind}")
    return [TypeAdapter(CoordinateObject).validate_python(item) for item in converted]


class DiagramSemanticConstraints(DiagramModel):
    given_objects: list[str] = Field(default_factory=list)
    given_constraints: list[str] = Field(default_factory=list)
    derived_objects: list[str] = Field(default_factory=list)
    derived_constraints: list[str] = Field(default_factory=list)
    clean_forbidden: list[str] = Field(default_factory=list)
    solution_allowed_annotations: list[str] = Field(default_factory=list)
    annotate: list[str] = Field(default_factory=list)


class DiagramProblemContext(DiagramModel):
    stem_latex: str = ""
    subquestion_latex: str = ""
    grade_or_topic: str = ""
    source_problem_text: str = ""


class DiagramVisualRequirements(DiagramModel):
    show_labels: bool = True
    show_given_markers: bool = True
    show_axes: bool = False
    preferred_orientation: DiagramOrientation = DiagramOrientation.AUTO
    label_density: DiagramLabelDensity = DiagramLabelDensity.NORMAL
    caption: str = ""


class DiagramRenderProfile(DiagramModel):
    """Resolved renderer/display defaults for printable worksheet diagrams."""

    display_profile: DiagramDisplayProfile = DiagramDisplayProfile.AUTO
    width: str = ""
    canvas_width_px: int | None = Field(default=None, ge=1)
    canvas_height_px: int | None = Field(default=None, ge=1)
    png_size_px: int | None = Field(default=None, ge=1)
    body_scale: DiagramBodyScale | None = None
    point_label_px: int | None = Field(default=None, ge=1)
    condition_label_px: int | None = Field(default=None, ge=1)
    axis_label_px: int | None = Field(default=None, ge=1)
    tick_label_px: int | None = Field(default=None, ge=1)
    point_radius_px: float | None = Field(default=None, gt=0)
    label_outline_width_px: float | None = Field(default=None, ge=0)
    point_label_offset_px: float | None = Field(default=None, ge=0)
    font_family: str = ""
    point_label_font_style: str = ""
    point_label_font_weight: str = ""
    condition_label_font_style: str = ""
    condition_label_font_weight: str = ""
    condition_label_style: DiagramConditionLabelStyle | None = None

    @model_validator(mode="after")
    def validate_width(self) -> DiagramRenderProfile:
        if self.width:
            validate_latex_dimension(self.width, field_name="render_profile.width")
        return self


def default_render_profile(
    display_profile: DiagramDisplayProfile,
    layout_role: DiagramLayoutRole | None = None,
    label_density: DiagramLabelDensity = DiagramLabelDensity.NORMAL,
) -> DiagramRenderProfile:
    if display_profile == DiagramDisplayProfile.AUTO:
        if layout_role == DiagramLayoutRole.CENTER_BLOCK:
            display_profile = DiagramDisplayProfile.WORKSHEET_GEOMETRY_CENTER
        else:
            display_profile = DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR

    point_label_px = 52 if label_density == DiagramLabelDensity.DENSE else 44
    width = "70mm" if display_profile == DiagramDisplayProfile.WORKSHEET_GEOMETRY_CENTER else "60mm"
    return DiagramRenderProfile(
        display_profile=display_profile,
        width=width,
        canvas_width_px=720,
        canvas_height_px=360,
        png_size_px=1024,
        body_scale=DiagramBodyScale.LARGE,
        point_label_px=point_label_px,
        condition_label_px=36,
        axis_label_px=18,
        tick_label_px=13,
        point_radius_px=5.2,
        label_outline_width_px=0,
        point_label_offset_px=34,
        font_family="Times New Roman, Georgia, serif",
        point_label_font_style="italic",
        point_label_font_weight="normal",
        condition_label_font_style="normal",
        condition_label_font_weight="normal",
        condition_label_style=DiagramConditionLabelStyle.VALUE_ONLY,
    )


class DiagramReuseSpec(DiagramModel):
    reuse_geometry_from: str = ""
    base_job_dir: str = ""


class DiagramModelConfig(DiagramLooseModel):
    """Codex SDK runtime config consumed by geometric_scene workflow.py."""

    model: str = ""
    codex_model: str = ""
    codex_bin: str = ""
    codex_timeout_s: float | None = Field(default=None, gt=0)

    def get(self, key: str, default: JsonValue | None = None) -> JsonValue | None:
        return self.model_dump(mode="python").get(key, default)

    def __getitem__(self, key: str) -> JsonValue:
        data = self.model_dump(mode="python")
        return data[key]


class DiagramEngineOptions(DiagramModel):
    seed: int | None = None
    max_retries: int = Field(default=0, ge=0)
    wolfram_timeout_s: int = Field(default=30, ge=1)
    wolfram_hard_timeout_s: int = Field(default=60, ge=1)
    renderer_spec: JsonObject = Field(default_factory=dict)
    # A deterministic GeometricScene payload.  When present on a
    # geometric_scene job, the batch runner skips the LLM scene-authoring
    # agent but still executes the Wolfram solve/validation stage.
    scene_payload: JsonObject = Field(default_factory=dict)
    spatial_spec: JsonObject = Field(default_factory=dict)
    engine_model_config: DiagramModelConfig = Field(
        default_factory=DiagramModelConfig,
        validation_alias=AliasChoices("engine_model_config", "model_config"),
    )

    @model_validator(mode="after")
    def hard_timeout_not_shorter(self) -> DiagramEngineOptions:
        if self.wolfram_hard_timeout_s < self.wolfram_timeout_s:
            raise ValueError("wolfram_hard_timeout_s must be >= wolfram_timeout_s")
        return self


class DiagramSlotBase(DiagramModel):
    """Shared plan-stage declaration fields for one diagram slot."""

    slot_id: NonEmptyStr
    diagram_ref: str = ""
    problem_id: str = ""
    source_problem_ref: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    required: bool = True
    on_failure: DiagramOnFailure = DiagramOnFailure.FAIL_ASSIGNMENT
    placement: NonEmptyStr
    layout_role: DiagramLayoutRole
    width_hint: str = ""
    display_profile: DiagramDisplayProfile = DiagramDisplayProfile.AUTO
    render_profile: DiagramRenderProfile | None = None
    caption: str = ""
    teaching_intent: str = "practice_prompt"
    problem_context: DiagramProblemContext = Field(default_factory=DiagramProblemContext)
    semantic_constraints: DiagramSemanticConstraints = Field(default_factory=DiagramSemanticConstraints)
    visual_requirements: DiagramVisualRequirements = Field(default_factory=DiagramVisualRequirements)
    reuse_geometry_from: str = ""
    engine_options: DiagramEngineOptions = Field(default_factory=DiagramEngineOptions)

    @model_validator(mode="after")
    def enforce_slot_policy(self) -> DiagramSlotBase:
        if not self.diagram_ref:
            self.diagram_ref = self.slot_id
        if self.width_hint:
            validate_latex_dimension(self.width_hint, field_name="width_hint")
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt diagrams must use disclosure_policy='clean'")
        if self.required and self.on_failure != DiagramOnFailure.FAIL_ASSIGNMENT:
            raise ValueError("required diagrams must use on_failure='fail_assignment'")
        if self.variant == DiagramVariant.SOLUTION and not self.reuse_geometry_from:
            raise ValueError("solution diagram slots must declare reuse_geometry_from")
        if self.caption and not self.visual_requirements.caption:
            self.visual_requirements.caption = self.caption
        return self

    def resolved_display_profile(self) -> DiagramDisplayProfile:
        if self.display_profile != DiagramDisplayProfile.AUTO:
            return self.display_profile
        if self.render_profile and self.render_profile.display_profile != DiagramDisplayProfile.AUTO:
            return self.render_profile.display_profile
        if self.layout_role == DiagramLayoutRole.CENTER_BLOCK:
            return DiagramDisplayProfile.WORKSHEET_GEOMETRY_CENTER
        return DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR

    def resolved_render_profile(self) -> DiagramRenderProfile:
        base = default_render_profile(
            self.resolved_display_profile(),
            self.layout_role,
            self.visual_requirements.label_density,
        )
        if self.render_profile is not None:
            overrides = self.render_profile.model_dump(exclude_unset=True, mode="python")
            for key, value in overrides.items():
                if value not in (None, ""):
                    setattr(base, key, value)
        if self.width_hint:
            base.width = self.width_hint
        base.display_profile = self.resolved_display_profile()
        return base


class SyntheticGeometryDiagramSlot(DiagramSlotBase):
    """Slot payload for synthetic geometry solved through GeometricScene."""

    engine: Literal["geometric_scene", "renderer_spec"] = "geometric_scene"
    diagram_kind: Literal["synthetic_geometry"] = "synthetic_geometry"


class SpatialGeometryDiagramSlot(DiagramSlotBase):
    """Slot payload for solid-geometry diagrams drawn from hidden 3D coordinates."""

    engine: Literal["spatial_renderer"] = "spatial_renderer"
    diagram_kind: Literal["spatial_geometry"] = "spatial_geometry"

    @model_validator(mode="after")
    def require_spatial_payload(self) -> SpatialGeometryDiagramSlot:
        if not self.engine_options.spatial_spec:
            raise ValueError("spatial_geometry diagram slots require engine_options.spatial_spec")
        return self


class CoordinatePlaneDiagramSlot(DiagramSlotBase):
    """Slot payload for coordinate-plane diagrams, including function curves."""

    engine: Literal["wolfram_client", "wolfram_plot", "coordinate_renderer", "renderer_spec"] = "coordinate_renderer"
    diagram_kind: Literal["coordinate_geometry"] = "coordinate_geometry"
    analytic_requirements: DiagramAnalyticRequirements = Field(default_factory=DiagramAnalyticRequirements)

    @model_validator(mode="after")
    def require_coordinate_payload(self) -> CoordinatePlaneDiagramSlot:
        if self.engine == DiagramEngine.RENDERER_SPEC.value and self.engine_options.renderer_spec:
            return self
        if self.analytic_requirements.coordinate_ir is None:
            raise ValueError(
                "coordinate_geometry diagram slots require a valid analytic_requirements.coordinate_ir"
            )
        return self


DiagramSlot: TypeAlias = Annotated[
    SyntheticGeometryDiagramSlot | SpatialGeometryDiagramSlot | CoordinatePlaneDiagramSlot,
    Field(discriminator="diagram_kind"),
]
DiagramSlotAdapter = TypeAdapter(DiagramSlot)


def validate_diagram_slot(data: object) -> DiagramSlot:
    """Validate one diagram_slot payload outside an assignment model."""
    return DiagramSlotAdapter.validate_python(data)


class DiagramJob(DiagramModel):
    """Executable single-image job collected from one DiagramSlot."""

    job_id: NonEmptyStr = Field(validation_alias=AliasChoices("job_id", "diagram_job_id"))
    slot_id: NonEmptyStr
    diagram_ref: NonEmptyStr
    slot_path: NonEmptyStr
    problem_id: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    required: bool = True
    on_failure: DiagramOnFailure = DiagramOnFailure.FAIL_ASSIGNMENT
    engine: DiagramEngine = DiagramEngine.GEOMETRIC_SCENE
    diagram_kind: DiagramKind = DiagramKind.SYNTHETIC_GEOMETRY
    teaching_intent: str = "practice_prompt"
    request_path: NonEmptyStr
    out_dir: NonEmptyStr
    public_image_dir: NonEmptyStr
    depends_on: list[str] = Field(default_factory=list)
    content_hash: str = ""
    reuse_geometry_from: str = ""

    @model_validator(mode="after")
    def enforce_job_policy(self) -> DiagramJob:
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt jobs must use disclosure_policy='clean'")
        if self.required and self.on_failure != DiagramOnFailure.FAIL_ASSIGNMENT:
            raise ValueError("required jobs must use on_failure='fail_assignment'")
        if self.variant == DiagramVariant.SOLUTION:
            if not self.reuse_geometry_from:
                raise ValueError("solution jobs must declare reuse_geometry_from")
            if self.reuse_geometry_from not in self.depends_on:
                self.depends_on.append(self.reuse_geometry_from)
        if self.job_id in self.depends_on:
            raise ValueError("job cannot depend on itself")
        return self


class DiagramJobsManifest(DiagramModel):
    schema_version: Literal["diagram-jobs/v1"] = "diagram-jobs/v1"
    assignment_id: NonEmptyStr
    source_assignment: NonEmptyStr
    jobs: list[DiagramJob] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_job_graph(self) -> DiagramJobsManifest:
        job_ids = [job.job_id for job in self.jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("diagram job ids must be unique")

        slot_ids = [job.slot_id for job in self.jobs]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("diagram slot ids must be unique in one jobs manifest")

        known = set(job_ids)
        graph = {job.job_id: list(job.depends_on) for job in self.jobs}
        for job in self.jobs:
            missing = [dep for dep in job.depends_on if dep not in known]
            if missing:
                raise ValueError(f"job '{job.job_id}' depends on unknown job(s): {missing}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(job_id: str) -> None:
            if job_id in visited:
                return
            if job_id in visiting:
                raise ValueError(f"diagram job graph contains a cycle at '{job_id}'")
            visiting.add(job_id)
            for dep in graph.get(job_id, []):
                visit(dep)
            visiting.remove(job_id)
            visited.add(job_id)

        for job_id in job_ids:
            visit(job_id)
        return self

    def topological_job_ids(self) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        graph = {job.job_id: list(job.depends_on) for job in self.jobs}

        def visit(job_id: str) -> None:
            if job_id in seen:
                return
            for dep in graph.get(job_id, []):
                visit(dep)
            seen.add(job_id)
            ordered.append(job_id)

        for job in self.jobs:
            visit(job.job_id)
        return ordered


class DiagramHumanRevision(DiagramModel):
    """One human-triggered revision of an existing diagram candidate."""

    action_id: NonEmptyStr
    review_id: NonEmptyStr
    feedback: NonEmptyStr
    base_round: int = Field(ge=0)
    requested_round: int = Field(ge=0)

    @model_validator(mode="after")
    def requested_round_follows_base(self) -> DiagramHumanRevision:
        if self.requested_round <= self.base_round:
            raise ValueError("requested_round must be greater than base_round")
        return self


class DiagramJobRequest(DiagramModel):
    """workflow.py input. It describes one image, never a whole assignment."""

    schema_version: Literal["diagram-job-request/v2"] = "diagram-job-request/v2"
    job_id: NonEmptyStr = Field(validation_alias=AliasChoices("job_id", "diagram_job_id"))
    assignment_id: NonEmptyStr
    problem_id: str = ""
    slot_id: NonEmptyStr
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    engine: DiagramEngine = DiagramEngine.GEOMETRIC_SCENE
    diagram_kind: DiagramKind = DiagramKind.SYNTHETIC_GEOMETRY
    teaching_intent: str = "practice_prompt"
    problem_context: DiagramProblemContext = Field(default_factory=DiagramProblemContext)
    semantic_constraints: DiagramSemanticConstraints = Field(default_factory=DiagramSemanticConstraints)
    analytic_requirements: DiagramAnalyticRequirements = Field(default_factory=DiagramAnalyticRequirements)
    visual_requirements: DiagramVisualRequirements = Field(default_factory=DiagramVisualRequirements)
    render_profile: DiagramRenderProfile = Field(
        default_factory=lambda: default_render_profile(DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR)
    )
    reuse: DiagramReuseSpec = Field(default_factory=DiagramReuseSpec)
    engine_options: DiagramEngineOptions = Field(default_factory=DiagramEngineOptions)
    human_revision: DiagramHumanRevision | None = None

    @model_validator(mode="after")
    def enforce_request_policy(self) -> DiagramJobRequest:
        if self.human_revision is not None:
            # A human submission authorizes exactly one new candidate Round.
            # It must never re-enable the legacy autonomous repair loop.
            self.engine_options.max_retries = 0
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt requests must use disclosure_policy='clean'")
        if self.variant == DiagramVariant.SOLUTION and not self.reuse.reuse_geometry_from:
            raise ValueError("solution requests must declare reuse.reuse_geometry_from")
        if (
            self.diagram_kind == DiagramKind.COORDINATE_GEOMETRY
            and self.engine != DiagramEngine.RENDERER_SPEC
            and self.analytic_requirements.coordinate_ir is None
        ):
            raise ValueError("coordinate_geometry requests require analytic_requirements.coordinate_ir")
        if (
            self.diagram_kind == DiagramKind.SPATIAL_GEOMETRY
            and self.engine == DiagramEngine.SPATIAL_RENDERER
            and not self.engine_options.spatial_spec
        ):
            raise ValueError("spatial_geometry requests require engine_options.spatial_spec")
        return self


class ModelAttempt(DiagramModel):
    role: Literal["text", "vision", "workflow", "renderer", "wolfram"] | str
    model: str = ""
    status: Literal["ok", "failed", "skipped"] = "failed"
    error_type: str = ""
    error: str = ""
    raw_response: str = ""


class RenderCanvas(DiagramLooseModel):
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    padding_px: int | None = Field(default=None, ge=0)
    background: str = "#ffffff"


class RenderSegment(DiagramLooseModel):
    id: str = ""
    start: NonEmptyStr = Field(
        validation_alias=AliasChoices("from", "start", "a"),
        serialization_alias="from",
    )
    end: NonEmptyStr = Field(
        validation_alias=AliasChoices("to", "end", "b"),
        serialization_alias="to",
    )
    stroke: str = "#111827"
    stroke_width: float = Field(default=2.6, gt=0)
    dash: str | None = None
    role: SpatialObjectRole = SpatialObjectRole.MAIN

    @model_validator(mode="before")
    @classmethod
    def normalize_shorthand(cls, value: object) -> object:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return {"from": str(value[0]), "to": str(value[1])}
        return value


class RenderPolygon(DiagramLooseModel):
    id: str = ""
    points: list[NonEmptyStr] = Field(min_length=3)
    stroke: str = "#374151"
    stroke_width: float = Field(default=2.0, gt=0)
    fill: str = "none"
    fill_opacity: float = Field(default=1.0, ge=0, le=1)
    role: SpatialObjectRole = SpatialObjectRole.SECONDARY

    @model_validator(mode="before")
    @classmethod
    def normalize_shorthand(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return {"points": [str(item) for item in value]}
        return value


class RenderMarker(DiagramLooseModel):
    type: NonEmptyStr
    vertex: str = Field(default="", validation_alias=AliasChoices("vertex", "at"))
    arms: list[str] = Field(default_factory=list)
    segments: list[tuple[str, str]] = Field(default_factory=list)
    stroke: str = ""

    @model_validator(mode="after")
    def normalize_marker_type(self) -> RenderMarker:
        marker_type = self.type.lower()
        if marker_type == "equal_tick":
            marker_type = "equal_ticks"
        if marker_type in {"parallel_mark", "parallel_marks"}:
            marker_type = "parallel"
        self.type = marker_type
        return self


class RenderLabel(DiagramLooseModel):
    text: str = ""
    placement: DiagramLabelPlacement | None = None
    dx: float = 0
    dy: float = -24
    show_point: bool = True

    @field_validator("placement", mode="before")
    @classmethod
    def normalize_placement(cls, value: object) -> object:
        if isinstance(value, str):
            return re.sub(r"\s+", " ", value.strip().lower().replace("_", " "))
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_shorthand(cls, value: object) -> object:
        if isinstance(value, str):
            return {"text": value}
        return value


class SpatialProjectionSpec(DiagramModel):
    """Projection controls that remain explicit in the final TikZ fragment."""

    mode: SpatialProjectionMode = SpatialProjectionMode.TEXTBOOK_OBLIQUE
    theta: float = Field(default=50, ge=0, le=90)
    phi: float = Field(default=120, ge=-360, le=360)
    depth_angle_deg: float = Field(default=45, ge=15, le=75)
    depth_scale: float = Field(default=0.5, gt=0, le=1)
    vertical_scale: float = Field(default=1.0, gt=0, le=2)
    flip_depth: bool = False
    min_plane_opening: float = Field(default=0.16, ge=0, le=1)
    min_core_angle_deg: float = Field(default=18, ge=0, le=90)

    @model_validator(mode="after")
    def apply_mode_defaults(self) -> SpatialProjectionSpec:
        fields_set = self.model_fields_set
        if self.mode == SpatialProjectionMode.HINGE_PLANES:
            if "theta" not in fields_set:
                self.theta = 50
            if "phi" not in fields_set:
                self.phi = 120
        elif self.mode == SpatialProjectionMode.ORTHOGRAPHIC_3D:
            if "theta" not in fields_set:
                self.theta = 55
            if "phi" not in fields_set:
                self.phi = 120
        elif self.mode == SpatialProjectionMode.AXIAL_SOLID:
            if "theta" not in fields_set:
                self.theta = 58
            if "phi" not in fields_set:
                self.phi = 115
        return self

class SceneDiagramSpec(DiagramLooseModel):
    """Model-generated renderer intent before Wolfram coordinates are solved."""

    type: str = DiagramKind.SYNTHETIC_GEOMETRY.value
    points: JsonObject = Field(default_factory=dict)
    objects: list[DiagramCoordinateObject] = Field(default_factory=list)
    segments: list[RenderSegment] = Field(default_factory=list)
    polygons: list[RenderPolygon] = Field(default_factory=list)
    markers: list[RenderMarker] = Field(default_factory=list)
    labels: dict[str, RenderLabel] = Field(default_factory=dict)
    teaching_focus: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    annotations: list[JsonObject] = Field(default_factory=list)
    source: JsonObject = Field(default_factory=dict)
    diagnostics: JsonObject = Field(default_factory=dict)


class ScenePayload(DiagramLooseModel):
    scene_code: NonEmptyStr
    points: list[str] = Field(default_factory=list)
    point_roles: dict[str, list[str]] = Field(default_factory=dict)
    diagram_spec: SceneDiagramSpec = Field(default_factory=SceneDiagramSpec)
    rationale: str = ""
    solution_reuse: JsonObject = Field(default_factory=dict)
    model_used: str = ""
    raw_response: str = ""
    model_attempts: list[ModelAttempt] = Field(default_factory=list)


class SolutionAuxiliaryPayload(DiagramLooseModel):
    auxiliary_points: list[str] = Field(default_factory=list)
    auxiliary_hypotheses_wl: list[str] = Field(default_factory=list)
    diagram_spec_delta: SceneDiagramSpec = Field(default_factory=SceneDiagramSpec)
    rationale: str = ""
    model_used: str = ""
    raw_response: str = ""
    model_attempts: list[ModelAttempt] = Field(default_factory=list)


class WolframRenderResult(DiagramLooseModel):
    success: bool = False
    fail_type: str = ""
    message: str = ""
    solve_time_s: float = Field(default=0, ge=0)
    seed: int | None = None
    parameters: JsonValue = None
    points: JsonValue = None
    image_path: str = ""
    render_image_requested: bool = True
    solution_reuse_check: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_payload(self) -> WolframRenderResult:
        if self.success:
            has_coordinates = self.parameters not in (None, {}, []) or self.points not in (None, {}, [])
            has_image = bool(self.image_path)
            if not (has_coordinates or has_image or self.render_image_requested is False):
                raise ValueError("successful Wolfram results require coordinates, image_path, or spec-only mode")
        elif not self.fail_type:
            self.fail_type = "unknown"
        return self


class VisionEvaluationResult(DiagramLooseModel):
    usable: bool = False
    score: int | str = 1
    defects: list[str] = Field(default_factory=list)
    suggested_constraint_feedback: str = ""
    evaluation_mode: str = ""
    model_used: str = ""
    raw_response: str = ""
    model_attempts: list[ModelAttempt] = Field(default_factory=list)


class WorkflowRound(DiagramModel):
    round_index: int = Field(default=0, ge=0)
    scene_payload: ScenePayload | JsonObject = Field(default_factory=dict)
    render_result: WolframRenderResult | JsonObject = Field(default_factory=dict)
    vision_result: VisionEvaluationResult | JsonObject = Field(default_factory=dict)


class DiagramWolframSummary(DiagramLooseModel):
    success: bool = False
    solve_time_s: float = Field(default=0, ge=0)
    seed: int | None = None


class DiagramModelSummary(DiagramLooseModel):
    text_model_used: str = ""
    attempts: list[ModelAttempt] = Field(default_factory=list)


class DiagramJobResult(DiagramLooseModel):
    schema_version: Literal["diagram-job-result/v2"] = "diagram-job-result/v2"
    job_id: str = Field(default="", validation_alias=AliasChoices("job_id", "diagram_job_id"))
    status: DiagramRunStatus = DiagramRunStatus.FAILED
    fail_type: str = ""
    message: str = ""
    request: str = "request.json"
    workflow_events: str = "workflow_events.jsonl"
    scene_payload: str = "scene_payload.json"
    final_renderer_spec: str = "final_renderer_spec.json"
    wolfram: DiagramWolframSummary = Field(default_factory=DiagramWolframSummary)
    model: DiagramModelSummary = Field(default_factory=DiagramModelSummary)
    policy_warnings: list[str] = Field(default_factory=list)
    final_diagram_spec: str = "final_diagram_spec.json"
    final_tikz_fragment_path: str = ""
    skills_used: JsonObject = Field(default_factory=dict)
    model_attempts: list[ModelAttempt] = Field(default_factory=list)
    rounds: list[WorkflowRound] = Field(default_factory=list)
    solution_reuse: JsonObject = Field(default_factory=dict)
    solution_reuse_check: JsonObject = Field(default_factory=dict)


class GeometryRenderSpec(DiagramLooseModel):
    schema_version: Literal["geometry-render-spec/v1"] = "geometry-render-spec/v1"
    job_id: str = ""
    variant: DiagramVariant | None = None
    disclosure_policy: DisclosurePolicy | None = None
    type: str = "synthetic_geometry"
    status: str = ""
    canvas: RenderCanvas = Field(default_factory=RenderCanvas)
    render_profile: DiagramRenderProfile = Field(
        default_factory=lambda: default_render_profile(DiagramDisplayProfile.WORKSHEET_GEOMETRY_SIDECAR)
    )
    viewport: DiagramCoordinateViewport | None = None
    axes: DiagramAxesSpec | None = None
    points: dict[str, Point2D] = Field(default_factory=dict)
    points3d: dict[str, Point3D] = Field(default_factory=dict)
    projection: SpatialProjectionSpec | None = None
    segments: list[RenderSegment] = Field(default_factory=list)
    polygons: list[RenderPolygon] = Field(default_factory=list)
    markers: list[RenderMarker] = Field(default_factory=list)
    labels: dict[str, RenderLabel] = Field(default_factory=dict)
    objects: list[DiagramCoordinateObject] = Field(default_factory=list)
    functions: list[DiagramFunctionSpec] = Field(default_factory=list)
    curves: list[JsonObject] = Field(default_factory=list)
    samples: dict[str, list[Point2D]] = Field(default_factory=dict)
    teaching_focus: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    source: JsonObject = Field(default_factory=dict)
    diagnostics: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_render_payload(self) -> GeometryRenderSpec:
        diagram_type = str(self.type)
        if self.status == "missing_coordinates":
            return self
        if diagram_type == DiagramKind.SYNTHETIC_GEOMETRY.value and not self.points:
            raise ValueError("synthetic geometry render specs require points")
        if diagram_type == DiagramKind.SPATIAL_GEOMETRY.value:
            if not self.points3d:
                raise ValueError("spatial geometry render specs require points3d")
            if self.points:
                raise ValueError("spatial geometry render specs must not contain pre-projected points")
            if self.projection is None:
                self.projection = SpatialProjectionSpec()
        if diagram_type in {
            DiagramKind.COORDINATE_GEOMETRY.value,
            DiagramKind.FUNCTION_GRAPH.value,
        }:
            if not (self.points or self.objects or self.functions or self.curves or self.samples):
                raise ValueError(
                    "coordinate/function render specs require points, objects, functions, curves, or samples"
                )
        point_names = set(self.points3d if diagram_type == DiagramKind.SPATIAL_GEOMETRY.value else self.points)
        for index, segment in enumerate(self.segments):
            if point_names and (segment.start not in point_names or segment.end not in point_names):
                raise ValueError(f"segments[{index}] references missing point")
        for index, polygon in enumerate(self.polygons):
            if point_names and any(name not in point_names for name in polygon.points):
                raise ValueError(f"polygons[{index}] references missing point")
        for index, marker in enumerate(self.markers):
            refs: list[str] = []
            if marker.vertex:
                refs.append(marker.vertex)
            refs.extend(marker.arms)
            refs.extend(name for segment in marker.segments for name in segment)
            if point_names and any(name not in point_names for name in refs):
                raise ValueError(f"markers[{index}] references missing point")
        return self


class RendererChecks(DiagramLooseModel):
    references_valid: bool = False
    svg_exists: bool = False
    image_exists: bool = False
    tikz_exists: bool = False
    pdf_exists: bool = False
    audit_exists: bool = False


class TikzRendererPaths(DiagramModel):
    fragment_path: str = ""
    standalone_tex_path: str = ""
    pdf_path: str = ""
    preview_png_path: str = ""
    preview_svg_path: str = ""
    log_path: str = ""
    audit_path: str = "renderer_audit.json"


class TikzNaturalSize(DiagramModel):
    width_pt: float | None = Field(default=None, gt=0)
    height_pt: float | None = Field(default=None, gt=0)
    aspect_ratio: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def compute_aspect_ratio(self) -> TikzNaturalSize:
        if self.aspect_ratio is None and self.width_pt and self.height_pt:
            self.aspect_ratio = round(self.width_pt / self.height_pt, 4)
        return self


class TikzReadabilityAudit(DiagramModel):
    display_width: str = ""
    point_label_count: int = Field(default=0, ge=0)
    min_point_label_pt_at_display_width: float | None = Field(default=None, gt=0)
    condition_label_style: DiagramConditionLabelStyle | None = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_display_width(self) -> TikzReadabilityAudit:
        if self.display_width:
            validate_latex_dimension(self.display_width, field_name="display_width")
        return self


class TikzRendererAudit(DiagramModel):
    schema_version: Literal["tikz-renderer-audit/v1"] = "tikz-renderer-audit/v1"
    job_id: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    paths: TikzRendererPaths = Field(default_factory=TikzRendererPaths)
    natural_size: TikzNaturalSize = Field(default_factory=TikzNaturalSize)
    readability: TikzReadabilityAudit = Field(default_factory=TikzReadabilityAudit)
    checks: RendererChecks = Field(default_factory=RendererChecks)
    warnings: list[str] = Field(default_factory=list)


class TikzSourcePayload(DiagramModel):
    """TikZ source emitted by the deterministic renderer.

    The fragment is the bindable TeX payload. Standalone TeX/PDF/PNG/SVG files
    are optional diagnostics and previews; the final assignment can inline or
    input the fragment directly.
    """

    source_mode: TikzSourceMode = TikzSourceMode.SOURCE_FILE
    fragment: str = ""
    fragment_path: str = ""
    standalone_tex_path: str = ""
    packages: list[str] = Field(default_factory=lambda: ["tikz"])
    libraries: list[str] = Field(default_factory=list)
    compile_engine: TikzCompileEngine = TikzCompileEngine.NONE
    export_tool: TikzExportTool = TikzExportTool.NONE

    @model_validator(mode="after")
    def require_fragment_or_path(self) -> TikzSourcePayload:
        if not self.fragment and not self.fragment_path:
            raise ValueError("TikZ source requires fragment or fragment_path")
        return self


class GeometryRendererResult(DiagramLooseModel):
    schema_version: Literal["geometry-renderer-result/v1"] = "geometry-renderer-result/v1"
    job_id: str = Field(default="", validation_alias=AliasChoices("job_id", "diagram_job_id"))
    status: DiagramRunStatus = DiagramRunStatus.FAILED
    fail_type: str = ""
    message: str = ""
    renderer: str = "teaching-tikz-geometry-renderer"
    artifact_kind: DiagramArtifactKind = DiagramArtifactKind.TIKZ
    diagram_variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    renderer_spec: str = "final_renderer_spec.json"
    tikz_fragment: str = ""
    tikz_fragment_path: str = ""
    tikz_source_path: str = ""
    tikz_standalone_path: str = ""
    tikz_pdf_path: str = ""
    preview_png_path: str = ""
    preview_svg: str = ""
    renderer_audit: str = ""
    natural_width_pt: float | None = Field(default=None, gt=0)
    natural_height_pt: float | None = Field(default=None, gt=0)
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    checks: RendererChecks = Field(default_factory=RendererChecks)

    @model_validator(mode="after")
    def enforce_renderer_output_policy(self) -> GeometryRendererResult:
        if self.status == DiagramRunStatus.OK:
            has_tikz = bool(self.tikz_fragment or self.tikz_fragment_path or self.tikz_source_path)
            if not has_tikz:
                raise ValueError("ok renderer results require tikz_fragment, tikz_fragment_path, or tikz_source_path")
        return self


class RendererBinding(DiagramModel):
    """Bindable TikZ result derived directly from a job renderer_result.json."""

    slot_id: NonEmptyStr
    diagram_ref: NonEmptyStr
    job_id: NonEmptyStr
    status: DiagramRunStatus = DiagramRunStatus.FAILED
    bindable: bool = False
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    tikz_fragment: str = ""
    tikz_fragment_path: str = ""
    tikz_source_path: str = ""
    tikz_standalone_path: str = ""
    tikz_pdf_path: str = ""
    preview_png_path: str = ""
    preview_svg: str = ""
    renderer_audit: str = ""
    renderer_result: str = ""
    workflow_result: str = ""
    final_renderer_spec: str = ""
    artifact_hash: str = Field(
        default="",
        validation_alias=AliasChoices("hash", "artifact_hash"),
        serialization_alias="hash",
    )
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_binding_policy(self) -> RendererBinding:
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt renderer bindings must use disclosure_policy='clean'")
        if self.bindable:
            if self.status != DiagramRunStatus.OK:
                raise ValueError("bindable renderer bindings must have status='ok'")
            if not (self.tikz_fragment or self.tikz_fragment_path or self.tikz_source_path):
                raise ValueError("bindable renderer bindings require tikz_fragment, tikz_fragment_path, or tikz_source_path")
            if not self.artifact_hash:
                raise ValueError("bindable renderer bindings must have a hash")
        return self


class RendererBindingManifest(DiagramModel):
    schema_version: Literal["renderer-bindings/v1"] = "renderer-bindings/v1"
    assignment_id: NonEmptyStr
    source_jobs: NonEmptyStr
    bindings: dict[str, RendererBinding] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_binding_keys(self) -> RendererBindingManifest:
        for diagram_ref, binding in self.bindings.items():
            if diagram_ref != binding.diagram_ref:
                raise ValueError(
                    f"binding key '{diagram_ref}' must match binding.diagram_ref '{binding.diagram_ref}'"
                )
        return self


class ResolvedDiagramTikz(DiagramModel):
    """Resolved YAML TikZ object consumed directly by LaTeX templates."""

    kind: Literal["tikz"] = "tikz"
    tikz_code: str = ""
    tikz_path: str = ""
    diagram_ref: NonEmptyStr
    diagram_job_id: NonEmptyStr = Field(validation_alias=AliasChoices("diagram_job_id", "job_id"))
    width: str = ""
    caption: str = ""
    variant: DiagramVariant = DiagramVariant.PROMPT
    disclosure_policy: DisclosurePolicy = DisclosurePolicy.CLEAN
    artifact_hash: str = Field(default="", validation_alias=AliasChoices("artifact_hash", "hash"))
    packages: list[str] = Field(default_factory=lambda: ["tikz"])
    libraries: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_resolved_tikz_policy(self) -> ResolvedDiagramTikz:
        if not self.tikz_code and not self.tikz_path:
            raise ValueError("resolved TikZ diagrams require tikz_code or tikz_path")
        if self.width:
            validate_latex_dimension(self.width, field_name="resolved TikZ width")
        if self.variant == DiagramVariant.PROMPT and self.disclosure_policy != DisclosurePolicy.CLEAN:
            raise ValueError("prompt resolved TikZ diagrams must use disclosure_policy='clean'")
        return self


class ResolvedDiagramFallback(DiagramModel):
    fallback: Literal[True] = True
    message: str = "图暂不可用"


class ResolvedDiagramPlacement(DiagramModel):
    field: Literal["diagram_col", "diagram_row_item", "diagram"] = "diagram_col"
    tikz: ResolvedDiagramTikz | None = None
    fallback: ResolvedDiagramFallback | None = None

    @model_validator(mode="after")
    def require_single_payload(self) -> ResolvedDiagramPlacement:
        payloads = [self.tikz is not None, self.fallback is not None]
        if sum(payloads) > 1:
            raise ValueError("resolved diagram placement accepts only one payload")
        return self

    def as_mapping(self) -> JsonObject:
        value: JsonValue
        if self.tikz is not None:
            value = self.tikz.model_dump(mode="json", by_alias=True)
        elif self.fallback is not None:
            value = self.fallback.model_dump(mode="json")
        else:
            value = {}
        return {self.field: value}


class AnswerSpacePartView(DiagramLooseModel):
    diagram_slot: DiagramSlot | None = None


class AnswerSpaceView(DiagramLooseModel):
    diagram_slot: DiagramSlot | None = None
    parts: list[AnswerSpacePartView] = Field(default_factory=list)


class AssignmentRouteStepView(DiagramLooseModel):
    diagram_slot: DiagramSlot | None = None


class AssignmentBlockView(DiagramLooseModel):
    id: str = ""
    stem_latex: str = ""
    stem: str = ""
    diagram_slot: DiagramSlot | None = None
    steps: list[AssignmentRouteStepView] = Field(default_factory=list)
    answer_space: AnswerSpaceView | None = None


class AssignmentSectionView(DiagramLooseModel):
    blocks: list[AssignmentBlockView] = Field(default_factory=list)


class AssignmentPlanDiagramView(DiagramLooseModel):
    meta: JsonObject = Field(default_factory=dict)
    sections: list[AssignmentSectionView] = Field(default_factory=list)

    @property
    def assignment_id(self) -> str:
        value = self.meta.get("assignment_id")
        return value if isinstance(value, str) else ""

    @property
    def title(self) -> str:
        value = self.meta.get("title")
        return value if isinstance(value, str) else ""


class DiagramSlotRef(DiagramModel):
    slot_path: NonEmptyStr
    slot: DiagramSlot
    section_index: int = Field(ge=0)
    block_index: int = Field(ge=0)
    step_index: int | None = Field(default=None, ge=0)
    part_index: int | None = Field(default=None, ge=0)


class GenerateCandidateResult(DiagramModel):
    status: Literal["ok", "failed"] = "ok"
    action: Literal["generate"] = "generate"
    round_index: int = Field(ge=0)
    scene_payload_path: str
    scene_payload: ScenePayload | None = None
    skills_used: list[str] = Field(default_factory=list)


class RenderCandidateResult(DiagramModel):
    status: Literal["ok", "failed"] = "failed"
    action: Literal["render"] = "render"
    round_index: int = Field(ge=0)
    render_result_path: str
    render_result: WolframRenderResult


class EvaluateImageResult(DiagramModel):
    status: Literal["ok", "failed"] = "ok"
    action: Literal["evaluate"] = "evaluate"
    round_index: int = Field(ge=0)
    vision_result_path: str
    vision_result: VisionEvaluationResult
    skills_used: list[str] = Field(default_factory=list)


class DiagramGateCheck(DiagramModel):
    name: NonEmptyStr
    status: Literal["pass", "warn", "block"]
    message: str = ""
    refs: list[str] = Field(default_factory=list)


class DiagramGateReport(DiagramModel):
    schema_version: Literal["diagram-gate-report/v1"] = "diagram-gate-report/v1"
    assignment_id: NonEmptyStr
    status: Literal["pass", "warn", "block"]
    checks: list[DiagramGateCheck] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch execution types
# ---------------------------------------------------------------------------

class DiagramBatchJobResult(DiagramModel):
    """Per-job execution result from the batch runner."""

    job_id: str = ""
    slot_id: str = ""
    variant: str = "prompt"
    status: Literal[
        "ok", "dry_run", "not_run",
        "workflow_failed", "renderer_failed", "renderer_no_spec",
        "dependency_failed",
    ] = "not_run"
    workflow_status: str = "not_run"
    renderer_status: str = "not_run"
    tikz_fragment_path: str = ""
    tikz_source_path: str = ""
    failure_reason: str = ""


class DiagramBatchReport(DiagramModel):
    """Overall batch execution report."""

    schema_version: Literal["diagram-batch-report/v1"] = "diagram-batch-report/v1"
    assignment_id: str = ""
    total_jobs: int = Field(default=0, ge=0)
    ok_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    dry_run: bool = False
    jobs: list[DiagramBatchJobResult] = Field(default_factory=list)
