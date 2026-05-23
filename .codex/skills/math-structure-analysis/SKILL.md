---
name: math-structure-analysis
description: "Analyze a math problem into a reusable teaching-structure artifact before any student-facing explanation or practice generation, including canonical solution, likely blockers, learning-level prediction, and a variation blueprint for deeper practice. Use as stage 1 of the math teaching workflow. TRIGGER when: user provides a math problem to analyze or teach; user mentions math structure analysis; user asks to break down a math problem, find the canonical solution, identify the problem pattern, predict student blockers, or design variation principles. SKIP: user asks about a non-math subject; conversation already has a completed 01-structure-analysis.md for the problem; user is asking for student-facing explanation directly without first analyzing structure."
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
- 适合的学习层级：
- 本题讲解目标：
- 不要直接讲的抽象话：
- 必须先问的问题：
- 关键讲解顺序：
- 最适合的具体数值例子：
- 讲到哪里停下来让学生回答：

## 十、推荐练题任务包
- 若学生在 L0-L1，出什么题：
- 若学生在 L2，出什么题：
- 若学生在 L3，出什么题：
- 若学生在 L4，如何迁移：
- 若学生达到 L5-L6，如何深化/抽象/包装：
- 禁止出的跑偏变式：

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
    "target_learning_levels": [],
    "goal": "",
    "avoid_abstract_phrases": [],
    "must_ask_first": [],
    "teaching_sequence": [],
    "concrete_probe_example": "",
    "pause_points": []
  },
  "practice_task_packet": {
    "l0_l1_tasks": [],
    "l2_tasks": [],
    "l3_tasks": [],
    "l4_transfer_tasks": [],
    "l5_l6_deepening_variations": [],
    "forbidden_variations": []
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
- Do not generate HTML in this skill.

## Learning-Level Ladder

Use these human-readable levels:

- L0 读题层：学生看不懂题目场景、对象或条件关系。
- L1 入手层：学生能说出对象和条件，但找不到第一步入口。
- L2 建模层：学生能找到关键量，但不会建立等量关系、公式入口或坐标/图形对应。
- L3 求解层：学生会列式求解，但检查范围、绝对值、单位、排除值或退化情形不稳。
- L4 迁移层：学生能完成原题，但换问法、换数字或换表征后不稳定。
- L5 抽象层：学生能识别同构变式，可以处理部分隐藏结构或条件包装。
- L6 命题层：学生能解释结构不变量和迁移条件，可以做反向构造或判断条件是否充分。

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

## Mandatory Self-Check

Before finalizing `01-structure-analysis.md`, perform the checks below. If any check fails, revise the artifact first. Then append a concise section:

```markdown
## 十二、生成后自检
- 数学检查：
  - 每道题答案是否正确：
  - 是否存在漏解、增根、退化值：
  - 公式是否适用于本题：
- 教学检查：
  - 本页/本阶段是否只锁定一个核心结构或核心动作：
  - 有没有引入无关知识点：
  - 互动问题是否围绕本题核心链条：
- 学习层级检查：
  - 当前学习层级判断是否只作为预测而非结论：
  - 如果没有学生证据，是否标注“默认预测/默认诊断不可用”：
  - 后续升级建议是否只小步上升：
- HTML 检查：
  - 本阶段不生成 HTML，是否未输出学生页 HTML：
  - 若引用后续 HTML 要求，是否保留 A4 打印约束：
- 自检结论：
```

Use the canonical solution section to support the math check. Do not write "已检查" without naming the actual risk points checked.

## Handoff

End with:

```text
下一步建议：使用 math-student-explanation-html，输入本结构分析 + 学生画像 + 本次目标，生成学生讲解页。工作流：math-structure-analysis → math-student-explanation-html → math-adaptive-practice-html。
```
