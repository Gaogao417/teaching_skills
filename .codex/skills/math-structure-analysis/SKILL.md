---
name: math-structure-analysis
description: "Analyze a math problem into 01-structure-analysis.md before LaTeX/YAML explanation or practice generation. Use when: user provides a math problem to analyze/teach, asks for canonical solution, problem pattern, likely blockers, variation rules, complexity budget, or diagram teaching needs. Skip when: non-math request, an adequate 01-structure-analysis.md already exists, or the user only asks to render/compile existing YAML. This stage locks math facts and task packets; it does not generate assignment YAML, diagrams, images, or PDFs."
---

# Math Structure Analysis

## Purpose

Use this skill as stage 1 of the math teaching workflow:

```text
original problem -> structure analysis artifact -> explanation/practice artifacts
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

The artifact must be self-contained and include both human-readable sections and a compact machine-readable block.

## Required Structure

Write in Chinese. Use concise teacher-facing language.

```markdown
# 结构分析：<题目短标题>

## 原题
<完整题目；必要时补充图形文字描述>

## 一、题目场景
- 数学对象：
- 变量/参数：
- 函数/图形：
- 已知条件：
- 要求目标：

## 二、核心结构
- 表面考点：
- 本质考点：
- 一句话问题模式：

## 三、关键转化
- 最关键的转化：
- 为什么降低计算量：
- 不转化时的低效路径：

## 四、标准路径骨架
1. 先做什么：
2. 再做什么：
3. 建立什么关系：
4. 如何求解：
5. 需要检查什么：

## 四点五、标准完整解与验算
- 关键交点/关键量：
- 面积/方程/关系式：
- 完整求解过程：
- 最终答案：
- 排除值：
- 退化情形：
- 验算：
- 本题最短可靠路径：

## 五、出题人逻辑
- 诱导学生硬算的位置：
- 真正的捷径：
- 训练的可迁移能力：

## 六、学生卡点预测
- 基础薄弱学生：
- 中等学生：
- 较强学生：

## 七、变式原则
- 核心不变量：
- 表层特征：
- 可变维度：
- 深化阶梯：
- 允许的变换：
- 禁止的变换：
- 表征切换：
- 包装方式：
- 近迁移例子：
- 远迁移例子：
- 反例/伪变式：

## 八、计算复杂度预算
- 原题计算层级：
- 允许小步上升到：
- 禁止引入的计算负担：
- 必须保留的可见支架：

## 九、推荐讲题任务包
- 建议的本轮教学入口：
- 本题讲解目标：
- 不要直接讲的抽象话：
- 必须先问的问题：
- 关键讲解顺序：
- 最适合的具体数值例子：
- 讲到哪里停下来让学生回答：

## 十、推荐练题任务包
- 若卡在读题/入手动作，出什么题：
- 若卡在建模或关系入口，出什么题：
- 若卡在求解和检查，出什么题：
- 若原题已稳，如何小步迁移：
- 若结构识别已稳，如何深化/抽象/包装：
- 禁止出的跑偏变式：

## 十点五、推荐图形请求包（可选）
- 是否需要图：
- 图形类型：`synthetic_geometry` / `coordinate_geometry` / `function_graph` / `auto`
- 用图意图：`student_explanation` / `practice_prompt` / `teacher_reference`
- 需要出现的对象：
- 需要突出给学生看的关系：
- 图中不能暗示的错误性质：
- 图失败时的降级方案：

## 十一、交付给下一阶段的结构摘要
```json
{
  "problem_pattern": "",
  "core_transformation": "",
  "solution_skeleton": ["", "", ""],
  "canonical_solution": {
    "key_quantities": [],
    "equation": "",
    "answer_set": [],
    "excluded_values": [],
    "degenerate_cases": [],
    "verification": "",
    "shortest_reliable_path": ""
  },
  "common_blockers": {
    "low": [],
    "middle": [],
    "strong": []
  },
  "variation_rules": {
    "core_invariant": "",
    "surface_features": [],
    "variation_dimensions": [],
    "depth_ladder": [],
    "allowed_transforms": [],
    "forbidden_transforms": [],
    "cognitive_load_budget": "",
    "representation_options": [],
    "packaging_options": [],
    "near_transfer_examples": [],
    "far_transfer_examples": [],
    "non_examples": []
  },
  "complexity_budget": {
    "original_level": "",
    "max_next_step": "",
    "forbidden_load": [],
    "required_scaffolds": []
  },
  "explanation_task_packet": {
    "target_teaching_entries": [],
    "goal": "",
    "avoid_abstract_phrases": [],
    "must_ask_first": [],
    "teaching_sequence": [],
    "concrete_probe_example": "",
    "pause_points": []
  },
  "practice_task_packet": {
    "read_context_or_find_entry_tasks": [],
    "build_relation_tasks": [],
    "solve_and_check_tasks": [],
    "transfer_tasks": [],
    "hidden_structure_or_reverse_tasks": [],
    "forbidden_variations": []
  },
  "diagram_request_packet": {
    "needs_diagram": false,
    "diagram_type": "synthetic_geometry | coordinate_geometry | function_graph | auto",
    "diagram_intent": "student_explanation",
    "objects_hint": {
      "points": [],
      "segments": [],
      "curves": [],
      "constraints": []
    },
    "teaching_focus": [],
    "must_not_imply": [],
    "fallback": "textual_diagram_description"
  }
}
```
```

## Quality Rules

- Always solve the problem completely before writing the teaching analysis.
- Treat the canonical solution as the mathematical anchor for later artifacts.
- Separate what the problem determines from what the student determines.
- Keep "学生卡点预测" as predictions, not a final teaching plan.
- Prefer action language over slogan language: "找交点坐标" beats "数形结合".
- Identify the shortest reliable route and at least one tempting inefficient route.
- Treat variation rules as a first-class output. Do not stop at "change numbers"; name the invariant, the allowed dimensions of change, and the next safe deepening move.
- For each deepening move, change only one main dimension at a time: number, question target, representation, condition packaging, hidden structure, or reverse construction.
- Mention hidden constraints such as domains, sign, absolute value, range checks, units, and diagram assumptions when relevant.
- If a diagram would materially help the student, fill `diagram_request_packet`; otherwise set `needs_diagram: false`.
- `diagram_request_packet` describes teaching needs only. Do not write Wolfram, GeometricScene code, rendering prompts, VLM prompts, retry rules, or image paths in this skill.
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
- Hidden constraints such as domains, sign, absolute value, excluded values, or degenerate cases are named when relevant.
- `variation_rules` preserve one core invariant and avoid off-track variations.
- `complexity_budget` gives concrete constraints for the practice stage.
- `diagram_request_packet` describes only teaching needs, object hints, focus, and visual traps; it does not include renderer code, retry logic, or image paths.
- The output contains no assignment YAML, diagrams, images, TEX, or PDF instructions beyond the handoff.

## Handoff

End with:

```text
下一步建议：使用 math-student-explanation-latex-data，输入本结构分析 + 学生画像 + 本次目标，生成 02-student-explanation.plan.assignment.yaml 或 02-student-explanation.assignment.yaml。工作流：math-structure-analysis → math-student-explanation-latex-data → math-adaptive-practice-latex-data → math-geometry-diagram-renderer → math-assignment-latex render/compile → math-homework-review。
```
