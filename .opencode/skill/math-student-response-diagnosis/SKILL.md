---
name: math-student-response-diagnosis
description: "Diagnose a student's math response after an explanation or attempt, map the observed behavior to a human-readable L0-L6 learning level, identify the specific blocker, update the student profile, and recommend the next teaching move before adaptive practice is generated. This is an OPTIONAL skill outside the default 3-stage workflow. TRIGGER when: user explicitly requests student response diagnosis; user provides a student answer and wants diagnostic analysis; teacher wants learning-level assessment of student work. SKIP: user has not submitted any student response; user wants to proceed with the default 3-stage workflow (math-structure-analysis → math-student-explanation-html → math-adaptive-practice-html)."
---

# Math Student Response Diagnosis

## Purpose

Use this skill between explanation and adaptive practice:

```text
student response + structure analysis + canonical solution -> diagnosis artifact -> adaptive practice
```

This skill decides why the student struggled, not merely whether the final answer is right.

## Inputs

Require:

- `01-structure-analysis.md` or equivalent, especially `canonical_solution`, `common_blockers`, and `explanation_task_packet`.
- Student answer, scratch work, oral response transcript, teacher notes, or screenshots transcribed into text.

Accept:

- Previous student profile.
- Which question or checkpoint the student was answering.
- Whether hints were given.

## Output Artifact

Create:

```text
artifacts/<same-problem-slug>/03-student-response-diagnosis.md
```

If this diagnosis happens after a later practice round, increment the filename or place it under `round-02/`.

## Required Structure

Write in Chinese. Keep it teacher-facing and concise.

```markdown
# 学生回答诊断：<题目短标题>

## 一、学生回答摘要
- 学生做对了什么：
- 学生卡住/出错的位置：
- 是否使用提示：

## 二、对照标准完整解
- 与 canonical solution 一致的部分：
- 缺失的关键量/关系：
- 错误的计算或推理：
- 需要排查的隐藏条件：

## 三、错因诊断
- 主要错因：
- 次要错因：
- 不是本轮重点的问题：

## 四、学习层级判断
- 当前层级：
- 判断依据：
- 置信度：高/中/低

## 五、更新学生画像
- 已掌握：
- 未掌握：
- 容易误判的表象：
- 下一轮允许的抽象程度：

## 六、下一步教学建议
- 需要再讲：
- 需要先练：
- 是否可以升级变式：
- 给 adaptive practice 的出题指令：

## 七、交付给下一阶段的诊断摘要
```json
{
  "learning_level": "",
  "confidence": "",
  "main_blocker": "",
  "secondary_blockers": [],
  "mastered_actions": [],
  "unmastered_actions": [],
  "allowed_abstraction": "",
  "next_move": "",
  "practice_instruction": ""
}
```
```

## Learning-Level Rules

- L0 读题层：学生看不懂题目场景、对象或条件关系。
- L1 入手层：学生能说出对象和条件，但找不到第一步入口。
- L2 建模层：学生能找到关键量，但不会建立等量关系、公式入口或坐标/图形对应。
- L3 求解层：学生会列式求解，但检查范围、绝对值、单位、排除值或退化情形不稳。
- L4 迁移层：学生能完成原题，但换问法、换数字或换表征后不稳定。
- L5 抽象层：学生能识别同构变式，可以处理部分隐藏结构或条件包装。
- L6 命题层：学生能解释结构不变量和迁移条件，可以做反向构造或判断条件是否充分。

## Diagnosis Rules

- Diagnose from evidence. If evidence is thin, say confidence is low and choose a lower band.
- Do not over-credit a correct final answer if the reasoning skips the core action.
- Do not over-punish an arithmetic slip if the structure is correct; record it as calculation carelessness.
- Distinguish "不会算" from "不知道为什么这样算".
- Prefer actionable blockers: "不知道交点要联立方程" is better than "基础差".
- Use the lowest level that explains the visible evidence. A correct answer without visible reasoning usually supports at most L3-L4, not L5-L6.

## Mandatory Self-Check

Before finalizing `03-student-response-diagnosis.md`, perform the checks below. If any check fails, revise the diagnosis first. Then append:

```markdown
## 八、生成后自检
- 数学检查：
  - 是否正确对照 canonical solution：
  - 是否误判漏解、增根、退化值或公式适用性：
- 教学检查：
  - 诊断是否聚焦一个主要核心动作：
  - 是否引入无关知识点：
  - 下一步建议是否围绕本题核心链条：
- 学习层级检查：
  - 当前层级是否由学生证据支持：
  - 如果没有学生证据，是否标注“默认诊断”：
  - 升级是否只小步上升：
- HTML 检查：
  - 本阶段不生成 HTML，是否未输出练习页/讲解页 HTML：
  - 若建议后续 HTML，是否提醒 A4 打印与无 CDN 优先：
- 自检结论：
```

Do not infer high confidence from a correct answer alone; confidence must come from visible reasoning or teacher evidence.

## Handoff

End with:

```text
下一步建议：使用 math-adaptive-practice-html，输入本诊断 + 结构分析，生成下一组 A4 练习。注意：本 skill 为可选独立工具，默认工作流为 math-structure-analysis → math-student-explanation-html → math-adaptive-practice-html，无需经过本诊断阶段。
```
