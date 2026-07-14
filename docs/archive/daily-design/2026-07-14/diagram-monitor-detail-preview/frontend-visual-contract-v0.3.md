# Diagram Monitor Detail Preview — Frontend Visual Contract v0.3

Status: approved from the user's reported broken state and the existing monitor visual language.

## Scope

- Repair the overview preview inside the existing Job detail pane.
- Keep the current three-pane information architecture, tokens, tabs, and human-review controls.
- Do not alter diagram artifacts or regenerate images.

## Behavior

- The initial deterministic Round 0 displays the job-level final preview when its round record has no dedicated `preview_path` and no selected/effective round was recorded.
- A later human-review candidate never falls back to an older job-level preview; while its own image is absent, the empty candidate state remains visible.
- The detail preview contains the image without cropping and the detail body remains independently scrollable.

## Acceptance checks

- A successful one-round job with `preview_path` and `selected_round: null` renders one loaded image in `.detail-preview`.
- The image has positive natural width and height and stays within the detail preview bounds.
- A pending revision round with no preview does not show the previous round's image.
- At the current 919 px-wide viewport, the detail body retains `overflow: auto` and no horizontal overflow is introduced.
