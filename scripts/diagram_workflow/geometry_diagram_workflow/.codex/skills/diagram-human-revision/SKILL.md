---
name: diagram-human-revision
description: Revise an existing synthetic-geometry diagram from teacher feedback inside the geometry diagram workflow. Use when a DiagramJobRequest contains human_revision, a teacher requests changes to an existing diagram Round, or a revision candidate must be visually checked before finalization.
---

# Diagram Human Revision

Revise the existing candidate conservatively and prove the rendered result was
visually inspected. Treat deterministic audit and visual inspection as separate
required gates.

## Required workflow

1. Read the teacher feedback in full.
2. Open and inspect the base Round preview before editing:
   `rounds/round_<base_round>/rendered/prompt.preview.png`.
3. If the requested Round preview already exists, open and inspect it before
   editing. Otherwise render the first requested-Round candidate, then open it.
4. Compare the feedback, original/base preview, requested-Round preview,
   normalized request, scene payload, and renderer spec. Preserve every
   already-correct geometric relation and every required visible given.
5. Make only the smallest change needed to resolve the feedback. Reuse the base
   geometry and visible structure unless the feedback requires changing them.
6. Render and run deterministic audit in the requested Round directory.
7. Open the newly rendered requested-Round preview with the image-view tool.
   Reading the PNG path, renderer result, audit JSON, SVG, PDF, or TikZ source is
   not visual inspection. Audit success never substitutes for opening the PNG.
8. If the image is visually wrong, edit and rerender in the same requested Round.
   Overwrite that Round's candidate files and inspect the new PNG again. Never
   create another Round for repairs within the same teacher request.
9. Finalize only after deterministic audit passes and the latest rendered PNG
   passes visual inspection.

## Visual gate

Check that the requested change is visible, labels are readable, and no new
false implication or solution hint was introduced. Compare against the base
preview so unrelated correct geometry does not drift.

Before finalizing, enumerate every visible object named in the feedback and
every `REQUIRED VISIBLE` marker or label in the normalized request. Confirm each
one is actually present in the PNG. If the base candidate already omitted a
required given, consult the original Round 0 preview and restore it rather than
preserving the omission.

For an angle-marker revision, verify all of the following from the PNG:

- the marker vertex is the middle letter of the intended angle;
- the arc endpoints lie on the two intended rays from that vertex;
- the sweep direction selects the intended interior angle;
- the arc is the minor interior arc, strictly less than 180 degrees;
- the marker is not a near-complete circle, reflex arc, or full-angle loop;
- matching angle markers identify the intended equal angles and nothing else.

If any item fails, continue editing and rendering in the same requested Round.
Do not finalize a candidate merely because its deterministic audit passed.

## Boundaries

- Do not modify historical Round directories.
- Do not hand-edit assignment plan YAML, add TikZ to plan YAML, or add final
  image paths to plan YAML.
- Do not redesign unrelated diagram content while addressing narrow feedback.
- Do not finalize without opening both the base preview and the current
  requested-Round preview during this revision turn.
