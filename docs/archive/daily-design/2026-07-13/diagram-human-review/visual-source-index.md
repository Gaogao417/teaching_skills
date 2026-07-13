# Diagram Human Review Visual Source Index

## Existing sources

- Job overview already renders the effective candidate preview, selected round, status evidence, and stage grid.
- The detail pane is the only place with enough job context; no new page, tab, or modal is needed.
- Existing tokens in `monitor.css` use white bordered surfaces, teal accent, semantic success/warning/danger colors, 10 px radii, and compact 11–12 px controls.

## Required addition

- Add a `人工复核` section immediately below the current candidate preview in the Overview tab.
- Name the image `当前候选 Round N`, show its deterministic-audit state, and separately show an accepted Round when one exists. Do not call an unaccepted image final.
- Show status text for `未复核`, `已接受`, `排队中`, `Agent 修订中`, `新版本待复核`, and `修订失败`.
- Keep the current preview visible during all states.
- Provide a textarea labeled `修改建议` and two explicit actions: `接受当前图` and `提交给 Agent`.
- State clearly that submission starts one revision and does not allow Agent self-review/repeated repair.
- Disable duplicate submissions while queued/running; preserve typed feedback across auto-refresh. Disable acceptance when deterministic audit is not `pass`, while still allowing concrete change advice.

## Responsive and accessible behavior

- Controls stack below 720 px and never force horizontal overflow.
- The textarea has a visible label and status updates use an `aria-live` region.
- Buttons use text, not color alone; destructive/error copy remains visible as text.
