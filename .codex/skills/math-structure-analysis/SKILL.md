---
name: math-structure-analysis
description: "Analyze a math problem into 01-structure-analysis.md before LaTeX/YAML explanation or practice generation. Use when: user provides a math problem to analyze/teach, asks for canonical solution, problem pattern, likely blockers, variation rules, complexity budget, or diagram teaching needs. Skip when: non-math request, an adequate 01-structure-analysis.md already exists, or the user only asks to render/compile existing YAML. This stage locks math facts and task packets; it does not generate assignment YAML, diagrams, images, or PDFs."
---

# Math Structure Analysis

## Purpose

Use this skill as stage 1 of the math teaching workflow:

```text
original problem -> structure analysis artifact -> model-rule ingestion -> explanation/practice artifacts
```

Do not write a student-facing explanation. Produce a backend teaching artifact that later skills can consume. The first stage must lock the mathematical facts of the problem, not merely discuss it.

## Inputs

Require:

- Original problem text, including diagrams described in words if no image is available.

Accept when available:

- Grade/term, exam type, textbook version, topic, prior hints from the teacher.
- Student context, but use it only as weak context. Student-specific teaching decisions belong to later stages.

## Output Artifact

Create one Markdown file alongside the explanation and practice artifacts (same directory) unless the user gives another path:

```text
artifacts/<student-name>/<date>-<problem-slug>/01-structure-analysis.md
```

Example: `artifacts/王攸然/2026-05-19-等腰直角存在性/01-structure-analysis.md`

Derive the path from the conversation context:
- `<student-name>`: ask the user or infer from existing artifact directories.
- `<date>`: today's date in `YYYY-MM-DD` format.
- `<problem-slug>`: short Chinese or ASCII slug describing the problem (e.g., `等腰直角存在性`, `linear-area-param`).

If the directory already exists (e.g., explanation PDFs are already there), place the file in that existing directory. If the directory does not exist, create it.

The artifact must be self-contained. Use structured Markdown sections as the downstream interface; do not append a compact JSON or machine-readable summary that lets later skills ignore the prose. The only allowed machine-oriented block is the optional `model_rule_draft` in "模型规则入库草案"; it is an ingestion draft, not a replacement for the prose analysis.

## Required Structure

Write in Chinese. Use concise teacher-facing language.

The artifact must include these sections:

- 原题
- 题目场景
- 核心结构（必须包含题型功能、统一命题网络、模型标签）
- 知识点/模型锚点
- 关键转化
- 标准路径骨架
- 标准完整解与验算
- 出题人逻辑
- 学生卡点预测
- 变式原则
- 计算复杂度预算
- 推荐讲题任务包
- 推荐练题任务包
- 推荐图形请求包（可选）
- 模型规则入库草案（可选；一次函数相关题默认尝试）

When writing the actual artifact, read `references/structure-template.md` and use its Markdown template. Keep the artifact self-contained: later YAML skills should be able to consume the full structure analysis without rereading the original problem.

## References

- `references/structure-template.md`: full `01-structure-analysis.md` Markdown template.

## Core Structure Representation

The "核心结构" section should be more precise than a topic label. Use a teacher-readable proposition network inspired by ai-math:

```text
problem -> propositions -> relations -> target
```

Use the representation that matches the problem type:

- 概念辨析题：write a "判别条件表", then express the shortest check as a small proposition network.
- 基础计算题：still use propositions. Treat computation states as propositions, e.g. `P3（计算状态）：去分母后得到 ...`, then write `R1: P1 + P2 -> P3，方法：去分母`.
- 应用题：use 情景量表 + proposition network. Quantities are propositions or proposition inputs; equations are relations.
- 证明题：write propositions as `P1`, `P2`, ... and relations as `R1: P1 + P2 -> P3，方法：...`.
- 综合题/压轴题/存在性题：use layered proposition network plus a compressed main chain. Separate branch conditions and final range/degenerate checks.

Rules:

- Label each proposition by source: `题设`, `定义`, `定理`, `构造`, `可推`, `目标`, or `检查`.
- Do not invent propositions from a diagram. If a relation comes only from a visual impression, mark it as `需原图复核`.
- A relation should name the method, not just the result: "R2: P3 + P4 -> P5，方法：SAS 全等" is useful; "推出 P5" is not.
- Keep the human-readable network compact. For long proofs, list the key network and put routine algebra in the standard solution.
- Put compatibility-friendly labels such as problem pattern, core transformation, proposition network, and model tags in the prose sections themselves. Do not duplicate them into a separate handoff block.

## Model Rule Draft

For linear-function topics, coordinate area, and coordinate parallelogram existence, add a final section:

```markdown
## 十一点、模型规则入库草案（可选）
```

If the problem should enter the v0 model-rule library, include a fenced YAML block named `model_rule_draft` with:

```yaml
model_rule_draft:
  model_family_id:
  name:
  intuitive_given:
    - ...
  intuitive_derive:
    - ...
  type_registry_patch:
    aliases_to_add: []
    new_type_candidates: []
  relation_candidates:
    - relation_id:
      given:
        - ...
      derive:
        - ...
      expected_input_types:
        slot_name: Point2D
      expected_output_types:
        slot_name: Area
      must_keep_constraints:
        - ...
```

If the problem is outside the v0 scope, write "暂不入库" and a short reason. Geometry proof models are out of scope for now.

## Quality Rules

- Always solve the problem completely before writing the teaching analysis.
- Treat the canonical solution as the mathematical anchor for later artifacts.
- Separate what the problem determines from what the student determines.
- Keep "学生卡点预测" as task-level predictions, not student labels or a final teaching plan.
- Prefer action language over slogan language: "找交点坐标" beats "数形结合".
- In "核心结构", prefer explicit relations over vague labels: "P1 + P2 -> P3" beats "利用相似".
- Identify the shortest reliable route and at least one tempting inefficient route.
- Treat variation rules as a first-class output. Do not stop at "change numbers"; name the invariant, the allowed dimensions of change, and the next safe deepening move.
- For each deepening move, change only one main dimension at a time: number, question target, representation, condition packaging, hidden structure, or reverse construction.
- Variation rules should preserve the proposition network/model relation, not merely the surface topic. If a variation changes the key relation set, mark it as a non-example.
- Mention hidden constraints such as domains, sign, absolute value, range checks, units, and diagram assumptions when relevant.
- If a diagram would materially help the student, fill "推荐图形请求包"; otherwise write "是否需要图：否" and give a short reason.
- "推荐图形请求包" describes teaching needs only. Do not write Wolfram, GeometricScene code, rendering prompts, VLM prompts, retry rules, or image paths in this skill.
- Use `synthetic_geometry` only for ruler-and-compass style geometry such as triangles, circles, parallel/perpendicular relations, angle bisectors, medians, altitudes, and angle relations.
- Use `coordinate_geometry` or `function_graph` for axes, coordinates, function images, intersections, area under/with axes, and graph-reading tasks; do not force these into GeometricScene.
- In `must_not_imply`, name visual traps such as "不要暗示等腰", "不要画成直角", "不要让点重合", or "坐标比例不能误导面积关系".
- Do not generate assignment YAML, diagrams, images, or PDFs in this skill.

## Teaching Entry Ladder

Use these human-readable entries as local teaching-entry descriptions, not as student ratings:

- read_context：看不懂题目场景、对象或条件关系。
- find_entry：能说出对象和条件，但找不到第一步入口。
- build_relation：能找到关键量，但不会建立等量关系、公式入口或坐标/图形对应。
- solve_and_check：会列式求解，但检查范围、绝对值、单位、排除值或退化情形不稳。
- transfer：能完成原题，但换问法、换数字或换表征后不稳定。
- hidden_structure：能识别同构变式，可以处理部分隐藏结构或条件包装。
- reverse_construct：能解释结构不变量和迁移条件，可以做反向构造或判断条件是否充分。

## Variation Deepening Ladder

Use this ladder when designing practice. Do not skip levels unless the student evidence supports it.

1. 原题复现：保留题面结构，只训练完整路径。
2. 同结构换数：只换干净数字，核心动作不变。
3. 同结构换问法：已知与所求轻微互换，仍保留明显入口。
4. 同结构换表征：解析式、图像、表格、文字条件之间切换。
5. 条件包装：把关键条件藏进一句情境或几何描述，但不加新知识点。
6. 结构部分隐藏：题面不直接暴露核心结构，需要学生主动识别同构。
7. 反向构造：给目标或性质，让学生构造参数、条件或判断是否存在。

Variation quality rule: preserve the core invariant, deepen exactly one main dimension, keep computation within budget, and include at least one non-example that explains what would count as a misleading or off-track variation.

## Internal Generation Checks

Before finalizing `01-structure-analysis.md`, check the points below internally and revise if needed. Do not append a separate self-check or review section to the artifact; final quality review belongs to `math-homework-review`.

- The canonical solution is complete enough to anchor later YAML generation.
- The "核心结构" section contains an appropriate proposition network. Concept criteria and application quantity tables may appear as helper tables, but the core inference should still be expressible as `P_i + P_j -> P_k`.
- Every nontrivial `P_i + P_j -> P_k` relation names a method or theorem.
- The prose sections include proposition network and model tags, even if some entries are brief for simple concept/basic-skill tasks.
- Hidden constraints such as domains, sign, absolute value, excluded values, or degenerate cases are named when relevant.
- "变式原则" preserves one core invariant and avoids off-track variations.
- "计算复杂度预算" gives concrete constraints for the practice stage.
- "推荐图形请求包" describes only teaching needs, object hints, focus, and visual traps; it does not include renderer code, retry logic, or image paths.
- The output contains no assignment YAML, diagrams, images, TEX, or PDF instructions beyond the handoff.
- If the topic is in the v0 model-rule scope, the output includes either a `model_rule_draft` or a clear "暂不入库" reason.

## Handoff

End with:

```text
下一步建议：先使用 math-model-rule-ingestion 将本结构分析中的模型规则规范化为 canonical relations；随后 math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 可并行消费结构分析和模型库关系。工作流：math-structure-analysis → math-model-rule-ingestion →（math-student-explanation-latex-data 与 math-adaptive-practice-latex-data 并行）→ math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
```
