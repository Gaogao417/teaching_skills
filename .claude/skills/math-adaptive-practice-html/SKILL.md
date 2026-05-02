---
name: math-adaptive-practice-html
description: Generate the next printable A4 Chinese math practice HTML artifact from a structure-analysis artifact and a student-response diagnosis artifact. Use as stage 4 after math-student-response-diagnosis to decide whether to downgrade, consolidate, mildly transfer, or hide the structure in variations while respecting a computation complexity budget.
---

# Math Adaptive Practice HTML

## Purpose

Use this skill after diagnosis:

```text
structure analysis + diagnosis artifact -> printable adaptive practice HTML
```

The goal is not to create similar problems mechanically. Decide the next teaching move from the diagnosed blocker.

## Inputs

Require:

- `01-structure-analysis.md` or equivalent, including `canonical_solution`, `variation_rules`, and `complexity_budget`.
- `03-student-response-diagnosis.md` or equivalent diagnosis artifact.

Fallback:

- If no diagnosis artifact exists, first create a brief diagnosis section inside the output using the same A-F band rules, mark confidence as low, and generate diagnostic practice. Prefer using `math-student-response-diagnosis` first.

## Output Artifact

Create:

```text
artifacts/<same-problem-slug>/04-adaptive-practice.html
```

Use the same A4 print style as the explanation page. Include an answer key after a page break when the user wants a complete teacher version; otherwise include compact standard answers on the last page.
Teacher-only metadata must be hidden from the default student view and from print output.

## Mastery Bands

Use the diagnosed band and stated blocker:

- A档：看不懂题目场景。
- B档：能看懂图形，但不会找关键交点/关键量。
- C档：会找关键量，但不会选底高/关系。
- D档：会列式，但漏绝对值、范围、单位或条件检查。
- E档：会做原题，但不会迁移。
- F档：已经掌握，可以做结构隐藏的变式。

## Practice Selection

- A/B档：低门槛识别题，不急着加入参数。
- C档：选底高、选关系、找关键量的专项题。
- D档：绝对值、范围、分类讨论、条件检查题。
- E档：同源平级变式，保留核心结构，换表层情境。
- F档：结构隐藏型变式，小步提高，不引入无关知识点。

Each set has at most 3 problems. Difficulty may only rise one small step.

## Complexity Budget

Use the budget from structure analysis. If missing, infer and state one before generating problems.

- If the original ends in a linear equation or simple absolute value equation, variations may at most move to a simple quadratic or one extra simple case split.
- If the original only uses coordinate differences, variations must not mainly depend on point-to-line distance.
- If the original has no radicals, avoid complex radicals.
- If the original is for beginners, keep a visible baseline, axis, table, or diagram cue.
- Keep arithmetic clean: small integers, simple fractions, and answers that can be checked by hand.
- Do not hide the core structure and raise calculation difficulty in the same problem unless the diagnosis is F档 with high confidence.

## Required HTML Sections

Write in Chinese.

```html
<h1>自适应练习：题目短标题</h1>
<section>
  <h2>练习说明</h2>
  <p>告诉学生本组只练什么动作，不讲后台术语。</p>
</section>
<section class="problem">
  <h2>第1题</h2>
  <p class="stem">题目...</p>
  <details>
    <summary>提示一</summary>
    <p>...</p>
  </details>
  <details>
    <summary>提示二</summary>
    <p>...</p>
  </details>
  <div class="answer-space"></div>
  <aside class="teacher-note no-print">
    <h3>第1题教师备忘</h3>
    <p><strong>训练目标：</strong>...</p>
    <p><strong>预期卡点：</strong>...</p>
    <p><strong>复杂度说明：</strong>为什么没有超过预算。</p>
    <p><strong>升级/降级判断：</strong>...</p>
  </aside>
</section>
<section class="answer-key page-break">
  <h2>参考答案</h2>
  <ol>
    <li>只放标准答案和必要推导。</li>
  </ol>
</section>
<aside class="teacher-note no-print">
  <h2>教师判断</h2>
  <p>当前档位：X档。主要错因：...。置信度：...</p>
</aside>
```

## Generation Rules

- Preserve the original problem's core structure.
- Use the canonical solution as a pattern anchor and answer-quality reference.
- For browser preview, set `<body data-view="student">` by default; if a teacher toggle is added, it must be `no-print` and must not appear in the printed student sheet.
- Keep computation controlled; avoid ugly arithmetic unless the original structure requires it.
- Do not introduce unrelated knowledge points.
- Make hints progressive: hint 1 points to the action; hint 2 nearly reveals the setup, not the final answer.
- Include how to judge the student's response after each problem only in a `no-print` teacher note, not beside the student-facing stem.
- Use printable answer space: ruled lines or boxed work area.
- Do not put training goals, expected blockers, complexity notes, mastery bands, confidence, upgrade/downgrade rules, or self-check text in the student main flow. The student-facing page should contain only the stem, optional hints, answer space, and standard answers.

## Mandatory Self-Check

Before finalizing the HTML, solve every generated problem and revise any faulty item. Add a teacher-only self-check block near the end:

```html
<aside class="teacher-note self-check no-print">
  <h2>生成后自检</h2>
  <ul>
    <li><strong>数学检查：</strong>每道题答案是否正确；是否存在漏解、增根、退化值；公式是否适用于本题。</li>
    <li><strong>教学检查：</strong>本页是否只训练一个核心动作；有没有引入无关知识点；提示二是否过早暴露答案；互动问题/判断问题是否围绕本题核心链条。</li>
    <li><strong>档位检查：</strong>当前档位是否由学生证据或诊断 artifact 支持；如果没有学生证据，是否标注“默认诊断”；升级是否只小步上升。</li>
    <li><strong>学生版检查：</strong>教师判断、训练目标、预期卡点、复杂度说明、升级/降级建议是否全部在 `no-print` 区域内；学生打印和默认学生视角是否只看到题目、提示、答案空间和标准答案。</li>
    <li><strong>HTML 检查：</strong>标签是否闭合；是否符合 required sections；是否依赖网络 CDN；是否适合 A4 打印。</li>
    <li><strong>自检结论：</strong>...</li>
  </ul>
</aside>
```

Do not finalize a practice page unless the answer key has been checked against the generated stems.

## Handoff

End with a teacher-only note:

```html
<aside class="teacher-note no-print">
下一轮：根据本页完成情况，更新学生画像；必要时回到讲解页，或生成下一组变式。
</aside>
```
