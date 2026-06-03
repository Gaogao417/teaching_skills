---
name: math-student-response-diagnosis
description: "诊断学生数学回答中的可见证据，识别当前卡点、已掌握/未掌握动作、置信度、建议支架强度和建议变式深度。Use when: 用户明确提供学生答案、草稿、口述记录、教师观察或要求诊断回答后再设计练习。Skip when: 没有学生回答证据，或用户只想按默认 LaTeX/YAML 作业流程继续。输出诊断摘要供 math-adaptive-practice-latex-data 使用，所有判断只服务下一轮任务。"
---

# Math Student Response Diagnosis

## Purpose

Use this optional skill between explanation and adaptive practice:

```text
student response + structure analysis + canonical solution -> diagnosis artifact -> adaptive practice YAML instructions
```

This skill diagnoses the current blocker from evidence. It does not label the student.

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
artifacts/<学生名>/<date>-<problem-slug>/03-student-response-diagnosis.md
```

If this diagnosis happens after a later practice round, increment the filename or place it under `round-02/`.

## Required Structure

Write in Chinese. Keep it teacher-facing and concise.

```markdown
# 学生回答证据诊断：<题目短标题>

## 一、学生回答摘要
- 学生做对了什么：
- 学生卡住/出错的位置：
- 是否使用提示：

## 二、对照标准完整解
- 与 canonical solution 一致的部分：
- 缺失的关键量/关系：
- 错误的计算或推理：
- 需要排查的隐藏条件：

## 三、当前卡点诊断
- 主要卡点：
- 次要卡点：
- 不是本轮重点的问题：
- 证据：
- 置信度：高/中/低

## 四、动作掌握情况
- 已掌握动作：
- 未掌握动作：
- 容易误判的表象：

## 五、下一轮练习调节建议
- entry_point：
- scaffold_level：high / medium / low
- variation_depth：
- complexity_budget 使用方式：
- fallback_move：
- 给 math-adaptive-practice-latex-data 的出题指令：

## 六、交付给下一阶段的诊断摘要
```json
{
  "confidence": "",
  "main_blocker": "",
  "evidence": [],
  "secondary_blockers": [],
  "mastered_actions": [],
  "unmastered_actions": [],
  "entry_point": "",
  "scaffold_level": "high | medium | low",
  "variation_depth": "",
  "complexity_note": "",
  "fallback_move": "",
  "practice_instruction": ""
}
```
```

## Diagnosis Rules

- Diagnose from evidence. If evidence is thin, say confidence is low.
- Do not over-credit a correct final answer if the reasoning skips the core action.
- Do not over-punish an arithmetic slip if the structure is correct; record it as calculation carelessness.
- Distinguish "不会算" from "不知道为什么这样算".
- Prefer actionable blockers: "不知道交点要联立方程" is better than "基础差".
- Do not use student rating, rank, band, or long-term level labels.

## Mandatory Self-Check

Before finalizing `03-student-response-diagnosis.md`, perform the checks below internally. If any check fails, revise the diagnosis first. Do not append the checklist to the formal artifact unless the user explicitly asks for an audit trail.

```markdown
- 数学检查：
  - 是否正确对照 canonical solution：
  - 是否误判漏解、增根、退化值或公式适用性：
- 教学检查：
  - 诊断是否聚焦一个主要核心动作：
  - 是否引入无关知识点：
  - 下一步建议是否围绕本题核心链条：
- 证据检查：
  - 当前卡点是否由学生证据支持：
  - 如果证据不足，是否标注低置信度：
  - 建议变式是否只小步上升：
- 输出形态检查：
  - 本阶段是否只输出诊断 artifact，未输出讲解 YAML、练习 YAML 或 PDF：
- 自检结论：
```

Confidence must come from visible reasoning or teacher evidence, not from the final answer alone.

## Handoff

End with:

```text
下一步建议：使用 math-adaptive-practice-latex-data，输入本诊断 + 结构分析 + 讲解 YAML，生成下一组学生版/教师版练习 YAML。注意：本 skill 为可选独立工具，默认工作流无需经过本诊断阶段。
```
