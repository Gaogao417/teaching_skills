# Diagram TikZ-Only Architecture

## 0. Position

The diagram backend should be TikZ-only.

The final student or teacher TeX should not depend on a pre-rendered diagram
PNG. PNG/SVG/PDF previews are still useful for gate checks and visual review,
but they are diagnostics. The bindable artifact is TikZ source.

Clean target flow:

```text
diagram_slot
  -> DiagramJobRequest
  -> workflow.py / analytic_diagram_workflow.py
  -> solved geometry facts
  -> GeometryRenderSpec
  -> TikzDiagramSpec
  -> tikz fragment (.tex)
  -> renderer_result.json
  -> RendererBindingManifest
  -> resolved YAML with kind: tikz
  -> assignment TeX inlines or inputs TikZ
```

The renderer never consumes assignment YAML. The assignment renderer never
solves geometry. The only bridge is structured TikZ payload in resolved YAML.

## 1. Why TikZ Changes The Contract

The old renderer contract treated the diagram as an external image:

```text
final_renderer_spec.json -> rendered/prompt.png -> image_path in resolved YAML
```

That is no longer the right final artifact. With TikZ, the assignment TeX can
directly include the diagram source:

```text
final_renderer_spec.json
  -> rendered/prompt.fragment.tex
  -> resolved YAML:
       diagram_col:
         kind: tikz
         tikz_path: build/diagram/jobs/q1/rendered/prompt.fragment.tex
         width: 60mm
```

or, for small diagrams:

```yaml
diagram_col:
  kind: tikz
  tikz_code: |
    \begin{tikzpicture}
      ...
    \end{tikzpicture}
  width: 60mm
```

The PDF build then uses:

```tex
\begin{diagramcoltikz}{60mm}{原题图}
  \input{build/diagram/jobs/q1/rendered/prompt.fragment.tex}
\end{diagramcoltikz}
```

Preview rendering is optional and separate:

```text
prompt.fragment.tex -> prompt.preview.pdf/png/svg
```

## 2. Step-By-Step: GeometricScene To TeX

### 2.1 Plan Stage

The LaTeX-data skills write only `diagram_slot`.

```yaml
diagram_slot:
  slot_id: q1.prompt
  diagram_ref: q1.prompt
  variant: prompt
  disclosure_policy: clean
  placement: diagram_col
  layout_role: question_sidecar
  width_hint: 60mm
  engine: geometric_scene
  diagram_kind: synthetic_geometry
  semantic_constraints:
    given_objects: [A, B, C]
    given_constraints: [AB = AC]
```

No image path and no TikZ source appears in plan YAML.

### 2.2 Job Stage

The collector turns each slot into one `DiagramJob`.

```text
diagram_slot -> build/diagram/diagram_jobs.json
```

`DiagramJob` keeps only execution identity and slot binding data:

```text
job_id
slot_id
diagram_ref
slot_path
variant
disclosure_policy
engine
diagram_kind
depends_on
```

### 2.3 Request Stage

`run_diagram_batch.py` writes `request.json` for each job.

```text
DiagramJob + plan context -> DiagramJobRequest
```

The request contains problem semantics, analytic requirements, render profile,
and reuse constraints. It does not contain final TeX source.

### 2.4 Geometry Solving Stage

For synthetic geometry:

```text
DiagramJobRequest
  -> model-generated GeometricScene intent
  -> Wolfram GeometricScene solve
  -> reliable point coordinates and geometry instance
```

For coordinate or function diagrams:

```text
DiagramJobRequest
  -> analytic_diagram_workflow.py
  -> explicit viewport, axes, objects, samples, intersections
```

For spatial geometry:

```text
DiagramJobRequest
  -> spatial_diagram_workflow.py
  -> points3d + structured relations + derived plane intersections
  -> projection profile and readability diagnostics
```

Spatial coordinates remain three-dimensional through `GeometryRenderSpec`.
Python may calculate projected metrics for gate checks, but the final TikZ
fragment uses a textbook oblique coordinate basis or `tikz-3dplot`; it does not
consume pre-projected 2D points. See `docs/spatial-geometry-diagram-workflow.md`.

Important boundary: GeometricScene or WolframClient computes geometry facts.
TikZ does not become the mathematical solver.

### 2.5 Renderer Spec Stage

The workflow compiles solved facts into `GeometryRenderSpec`:

```text
points
points3d
projection
segments
polygons
markers
labels
viewport
axes
objects
functions
samples
render_profile
```

This is still backend-neutral enough to test, diff, and gate semantically.

### 2.6 TikZ Diagram Spec Stage

The deterministic TikZ compiler converts `GeometryRenderSpec` into a more
TeX-shaped intermediate object:

```text
TikzDiagramSpec
  document_preamble
  tikz_libraries
  style_roles
  coordinates
  draw_commands
  label_nodes
  marker_commands
  axis_or_pgfplots_block
  audit metadata
```

This stage is pure Python and deterministic. It does not call LLMs or Wolfram.

### 2.7 TikZ Fragment Stage

The renderer writes:

```text
build/diagram/jobs/<job_id>/rendered/<variant>.fragment.tex
```

The fragment is the bindable artifact:

```tex
\begin{tikzpicture}[x=1cm,y=1cm,baseline=(current bounding box.center)]
  ...
\end{tikzpicture}
```

Optional standalone wrapper for preview:

```text
rendered/<variant>.standalone.tex
rendered/<variant>.preview.pdf
rendered/<variant>.preview.png
rendered/<variant>.preview.svg
```

### 2.8 Renderer Result Stage

`renderer_result.json` records the TikZ payload and optional previews:

```json
{
  "schema_version": "geometry-renderer-result/v1",
  "status": "ok",
  "renderer": "teaching-tikz-geometry-renderer",
  "artifact_kind": "tikz",
  "diagram_variant": "prompt",
  "tikz_fragment_path": "rendered/prompt.fragment.tex",
  "tikz_standalone_path": "rendered/prompt.standalone.tex",
  "tikz_pdf_path": "rendered/prompt.preview.pdf",
  "preview_png_path": "rendered/prompt.preview.png",
  "preview_svg": "rendered/prompt.preview.svg",
  "renderer_audit": "renderer_audit.json"
}
```

### 2.9 Binding And Gate Stage

`renderer_bindings.py` reads `diagram_jobs.json` and each job's
`renderer_result.json`, resolves the TikZ fragment path, and hashes the TikZ
source. This in-memory binding manifest is the single source consumed by gate
and resolver.

```text
diagram_jobs.json + jobs/<job_id>/renderer_result.json
  -> RendererBindingManifest
  -> gate / resolver
```

Bindable means:

```text
status == ok
artifact_kind == tikz
tikz_fragment or tikz_fragment_path or tikz_source_path exists
artifact_hash starts with sha256:
```

Preview images are not required for final LaTeX inclusion, but they can be
required by visual gate policies.

`build_diagram_artifacts.py` is now only a debug helper that can dump those
bindings to `renderer_bindings.json`; the production chain does not require a
`diagram_artifacts.json` file.

### 2.10 Resolver Stage

The resolver replaces `diagram_slot` with a TikZ payload:

```yaml
diagram_col:
  kind: tikz
  tikz_path: build/diagram/jobs/q1/rendered/prompt.fragment.tex
  diagram_ref: q1.prompt
  diagram_job_id: q1-prompt
  width: 60mm
  caption: 原题图
  variant: prompt
  disclosure_policy: clean
  artifact_hash: sha256:...
```

For small fragments, resolver may inline:

```yaml
diagram_col:
  kind: tikz
  tikz_code: |
    \begin{tikzpicture}
      ...
    \end{tikzpicture}
```

### 2.11 Assignment TeX Stage

The assignment renderer consumes `kind: tikz`:

```tex
\begin{diagramcoltikz}{60mm}{原题图}
  \input{build/diagram/jobs/q1/rendered/prompt.fragment.tex}
\end{diagramcoltikz}
```

or:

```tex
\begin{diagramcoltikz}{60mm}{原题图}
  \begin{tikzpicture}
    ...
  \end{tikzpicture}
\end{diagramcoltikz}
```

Then the normal assignment compile runs once:

```text
resolved.assignment.yaml -> assignment.tex -> xelatex/tectonic -> assignment.pdf
```

There is no required separate image-rendering step for final output.

## 3. Pydantic Contract Model

### 3.1 Renderer Output

Core models:

```text
TikzSourcePayload
TikzRendererPaths
TikzNaturalSize
TikzReadabilityAudit
TikzRendererAudit
GeometryRendererResult
```

`GeometryRendererResult` is TikZ-only:

```text
artifact_kind = tikz
tikz_fragment
tikz_fragment_path
tikz_source_path
tikz_standalone_path
tikz_pdf_path
preview_png_path
preview_svg
renderer_audit
```

No `image_path` is required or considered bindable.

### 3.2 Renderer Binding

`RendererBinding` is derived from `diagram_jobs.json` and per-job
`renderer_result.json`:

```text
diagram_ref
job_id
status
tikz_fragment
tikz_fragment_path
tikz_source_path
tikz_standalone_path
tikz_pdf_path
preview_png_path
preview_svg
renderer_audit
artifact_hash
bindable
warnings
```

`bindable=true` means the TikZ source can be included in final TeX.

### 3.3 Resolved YAML

`ResolvedDiagramTikz` is the only resolved diagram payload:

```text
kind = tikz
tikz_code
tikz_path
diagram_ref
diagram_job_id
width
caption
variant
disclosure_policy
artifact_hash
packages
libraries
```

`ResolvedDiagramPlacement` wraps either:

```text
tikz
fallback
```

It no longer wraps `ResolvedDiagramImage`.

## 4. TikZ Feature Inventory

### 4.1 Core Geometry

| Need | TikZ / PGF feature | Spec source |
|---|---|---|
| Points | `\coordinate`, `\node`, `\fill` | `points`, point objects |
| Segments | `\draw (A) -- (B)` | `segments` |
| Polygons | `\draw ... -- cycle`, `\filldraw` | `polygons` |
| Polylines | `\draw ... -- ...` | `polyline`, samples |
| Circles | `\draw (O) circle[radius=...]` | circle objects |
| Arcs | `arc[start angle=..., end angle=...]` | arc and angle markers |
| Filled regions | `fill opacity`, `patterns.meta` | region / area objects |
| Clip viewport | `\clip`, `scope` | coordinate viewport |

### 4.2 Markers

| Need | TikZ / PGF feature | Spec source |
|---|---|---|
| Right angle | custom `pic` using `calc` | `right_angle` |
| Equal ticks | custom perpendicular tick macro | `equal_ticks` |
| Parallel marks | custom repeated tick macro | future marker |
| Angle arcs | `angles`, `quotes`, or custom arc macro | `angle_arc` |
| Congruent angle marks | repeated arcs | future marker |
| Arrowheads | `arrows.meta` | axes, rays, vectors |
| Construction lines | dashed/dotted styles | auxiliary roles |

### 4.3 Coordinate And Function Graphs

| Need | TikZ / PGF feature | Spec source |
|---|---|---|
| Axes | TikZ arrows or `pgfplots` axis | `axes` |
| Grid | TikZ grid or `pgfplots` grid | `axes.grid` |
| Equal scale | `axis equal image`, explicit `x=`, `y=` | `viewport.preserve_aspect` |
| Function curve | `\addplot coordinates` | `functions + samples` |
| Discontinuity | multiple coordinate plots | future segmented curve |
| Asymptote | dashed line object | explicit objects |
| Interval band | translucent rectangle | `interval_band` |
| Labels | anchored nodes | labels/text objects |

### 4.4 Calculations And Intersections

TikZ libraries:

```text
calc
intersections
angles
quotes
arrows.meta
decorations.markings
patterns.meta
backgrounds
```

Use them for drawing convenience: midpoints, marker placement, label offsets,
path clipping, and visual intersections.

Do not use TikZ to replace solved mathematical facts. Intersections that matter
to the problem should still be emitted by workflow or analytic workflow.

### 4.5 Semantic Macro Layer

The compiler should not stay as a primitive TikZ writer forever.

The first implementation emits valid low-level TikZ:

```tex
\coordinate (A) at (...);
\draw (A) -- (B);
\node at (A) {...};
\draw (...) arc[...];
```

That is compile-safe, but it does not use TikZ's strongest diagram features
enough. The target architecture is:

```text
GeometryRenderSpec
  -> TikzDiagramSpec
  -> semantic TikZ macro calls
  -> shared worksheet diagram macros
```

The renderer still generates the TikZ deterministically. The LLM never emits
raw TikZ. Macro arguments are always structured values: point ids, style roles,
placement enums, numeric dimensions, and escaped label text.

Recommended shared macros:

```tex
\DrawSegment{A}{B}
\DrawDashedSegment{A}{B}
\PointDot{A}
\PointLabel[above left]{A}{A}
\SegmentLabel[above]{A}{B}{5}
\AngleMark{A}{B}{C}
\AngleLabel{A}{B}{C}{30^\circ}
\RightAngleMark{A}{B}{C}
\EqualTick{A}{B}
\ParallelMark{A}{B}
\CoordinateTag[above right]{P}{text}
\NamedSegmentPath{ab}{A}{B}
\IntersectPaths{I}{ab}{cd}
```

Macro conventions:

```text
\AngleMark{A}{B}{C} means angle ABC, with B as the vertex.
\RightAngleMark{A}{B}{C} uses the same convention.
\EqualTick{A}{B} marks segment AB at its midpoint.
\SegmentLabel{A}{B}{text} places text near the midpoint of AB.
```

These macros should use TikZ libraries instead of duplicating geometry drawing
logic in Python:

```tex
pic {angle = A--B--C}
pic {right angle = A--B--C}
($(A)!0.5!(B)$)
name path=...
name intersections={of=pathA and pathB, by=I}
```

The production macro definitions should live in the assignment LaTeX preamble
so every diagram shares one visual language. The preview renderer should import
or emit the same macro definitions in standalone TeX; preview and final TeX
must not drift.

### 4.6 Label And Tag Placement

Current implementation:

```text
synthetic point labels:
  node at point + xshift/yshift
  default: above the point

coordinate point labels:
  node at axis cs:x,y
  default: anchor=south west

coordinate text tags:
  node at axis cs:x,y
  default: anchor=center
```

This is deterministic and compile-safe, but too blunt for dense geometry.

Target placement model:

```text
point labels:
  placement enum first: above, below, left, right, above left, ...
  auto default: away from the diagram centroid
  dx/dy offset remains an escape hatch

segment labels:
  midpoint via calc: ($(A)!0.5!(B)$)
  normal side chosen away from figure centroid unless explicitly specified

angle labels:
  position along the angle bisector
  radius/eccentricity controlled by marker style

condition/free tags:
  anchor + coordinate binding
  can attach to point, segment midpoint, angle bisector point, or explicit coordinate
```

The `GeometryRenderSpec` should evolve from point-only `labels` into typed label
records:

```text
PointLabelSpec:
  point, text, placement, dx, dy

SegmentLabelSpec:
  start, end, text, placement, pos

AngleLabelSpec:
  arm1, vertex, arm2, text, radius, placement

FreeTagSpec:
  at, text, anchor, dx, dy
```

For v1 hardening, the compiler should support explicit placement hints and
produce audit warnings for likely collisions. Full global label avoidance is a
later improvement; the first target is stable, semantic placement rather than
pixel-like offsets.

### 4.7 Intersections Policy

Use TikZ `intersections` for visual drawing convenience:

```text
extension line crosses another drawn path
helper path midpoint/intersection is only needed for drawing a marker
construction tag needs a visual anchor but not a mathematical fact
```

Do not use TikZ `intersections` as the source of mathematical truth:

```text
problem-relevant intersection point
root / zero / solution point on a graph
derived point needed by explanation text
length or angle fact used by reasoning
```

Those must remain solved upstream by GeometricScene, WolframClient, or analytic
workflow and enter `GeometryRenderSpec` as named points or objects. TikZ may
reuse the named point for drawing, but it should not silently invent it.

## 5. Size Strategy

TikZ helps substantially, but it does not decide the final worksheet layout by
itself.

### 5.1 What TikZ Solves

TikZ gives a natural TeX bounding box:

```text
tikzpicture -> TeX box dimensions
```

The final assignment can scale this box:

```tex
\resizebox{\linewidth}{!}{<tikzpicture>}
```

This solves:

```text
unused whitespace
consistent line/text proportions
vector quality in final PDF
same source for final PDF and preview exports
```

### 5.2 What TikZ Does Not Solve

TikZ does not know:

```text
whether the diagram should be sidecar or centered
whether 55mm is enough for six dense labels
whether the left text column remains readable
whether an annotated solution diagram is too crowded
```

Those are still controlled by:

```text
layout_role
width_hint
render_profile
renderer_audit
gate checks
visual fixtures
```

### 5.3 Clean Size Model

Use two sizes:

```text
intrinsic size:
  TikZ natural bounding box and audit metadata

display size:
  resolved YAML width from layout_role / width_hint / render_profile
```

The renderer audit should record:

```json
{
  "natural_size": {
    "width_pt": 180.0,
    "height_pt": 110.0,
    "aspect_ratio": 1.6364
  },
  "readability": {
    "display_width": "60mm",
    "min_point_label_pt_at_display_width": 9.5,
    "point_label_count": 6,
    "condition_label_style": "value_only"
  }
}
```

So the practical answer is:

```text
TikZ solves intrinsic diagram sizing.
The pipeline still decides display sizing.
```

## 6. Implemented Renderer Modules

```text
scripts/diagram_workflow/render_geometry_spec.py

scripts/diagram_workflow/tikz_renderer/
  __init__.py
  compiler.py
  contracts.py
  validate.py
  geometry_to_tikz.py
  coordinate_to_tikz.py
  styles.py
  writer.py
  toolchain.py
  result.py
```

Responsibilities:

```text
validate current GeometryRenderSpec
compile TikzDiagramSpec
write fragment tex
write tikz_spec debug json
write optional standalone tex
optionally compile preview pdf/png/svg
write renderer_audit.json
write renderer_result.json
```

No SVG backend, no backend flag, no legacy renderer fallback.

Current implementation note:

```text
The renderer already emits bindable TikZ fragments and passes smoke tests.
However, geometry_to_tikz.py still emits mostly primitive TikZ commands.
The next hardening step is to move marker, label, tag, and intersection drawing
onto the semantic macro layer described above.
```

## 7. Toolchain Policy

Final assignment compile requires a TeX engine capable of TikZ:

```text
tectonic or xelatex
```

Preview generation additionally needs:

```text
pdftocairo or dvisvgm
```

Preview toolchain failure should not automatically make the TikZ source
unbindable. It should create a gate warning or block depending on policy.

Final assignment compile failure remains fatal.

## 8. Migration Tasks

1. Keep renderer-result as the renderer output contract and derive bindable
   facts through `RendererBindingManifest`.
2. Make resolver output `kind: tikz` payloads.
3. Make LaTeX templates render `tikz_code` or `tikz_path`.
4. Implement deterministic `GeometryRenderSpec -> TikzDiagramSpec`.
5. Implement `TikzDiagramSpec -> fragment.tex`.
6. Add optional preview compilation and audit.
7. Update gate checks to read TikZ audit, not SVG text metadata.
8. Update e2e tests so bindable means TikZ source, not image path.
9. Add shared semantic macros for point labels, segment labels, angle marks,
    right-angle marks, equal ticks, tags, and visual intersections.
10. Replace primitive synthetic-geometry marker output with semantic macro
    calls backed by TikZ `calc`, `angles`, `quotes`, and `intersections`.

## 9. Acceptance Criteria

TikZ-only architecture is ready when:

```text
required diagram slots resolve to kind: tikz
resolved YAML contains tikz_code or tikz_path
assignment templates compile TikZ directly
renderer_result.json is the only per-job renderer truth
RendererBindingManifest hashes TikZ source
preview PNG/SVG is optional and marked diagnostic
student YAML cannot bind annotated solution TikZ
gate checks use renderer_audit.json
no production path requires image_path
```
