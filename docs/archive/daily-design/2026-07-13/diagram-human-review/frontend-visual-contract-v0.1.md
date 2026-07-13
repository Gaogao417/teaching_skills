# Diagram Human Review Frontend Visual Contract v0.1

Status: revised after contract audit; approved extension of the existing Diagram Pipeline Monitor contract.

| ID | User-visible contract | Automated acceptance | Manual acceptance |
|---|---|---|---|
| DHR-V01 | Human review appears inside the selected Job Overview directly below its current candidate preview. | Static DOM/JS test finds `人工复核`, candidate Round, textarea label, and both actions. | No navigation away from the current monitor is required. |
| DHR-V02 | Current review state is always text-visible and distinguishes six lifecycle states. | JS test covers all labels and maps API state to copy. | Color is supplementary only. |
| DHR-V03 | `接受当前图` and `提交给 Agent` are separate actions; advice submission requires non-empty text. | Interaction/unit checks protect request payloads and validation copy. | The user can predict whether an Agent will run. |
| DHR-V04 | The panel says that one explicit submission creates one revision and the Agent will not self-review/retry. | Static copy assertion. | The operating rule is understandable without docs. |
| DHR-V05 | Queued/running states disable both actions and retain the current preview; blocked/missing audit disables acceptance but not advice. | JS/CSS state checks. | Auto-refresh does not erase text currently being edited. |
| DHR-V06 | At mobile width, textarea and buttons stack within the detail pane without horizontal overflow. | Responsive CSS assertion at the existing 720 px breakpoint. | Controls remain comfortably tappable. |

## Styling constraints

- Reuse current `--accent`, `--success`, `--warning`, `--danger`, `--line`, and `--radius` tokens.
- Use a bordered inset section, not a new modal, floating panel, gradient, or dashboard widget.
- Keep button and textarea sizing aligned with existing compact local-tool controls.
