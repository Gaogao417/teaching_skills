---
name: math-practice-html
description: "Generate the next printable A4 Chinese math practice HTML artifact from a structure-analysis artifact and an explanation artifact. Use as stage 3 after math-student-explanation-html to decide whether to downgrade, consolidate, mildly transfer, or hide the structure in variations while respecting a computation complexity budget. TRIGGER when: a structure-analysis artifact and explanation artifact exist for the current problem; user asks for practice problems or practice exercises; after math-student-explanation-html completes; user wants printable practice based on a previously analyzed problem. SKIP: no structure-analysis artifact exists (run math-structure-analysis first); no explanation artifact exists (run math-student-explanation-html first); user wants explanation not practice."
---

# Math Practice HTML

## Purpose

Use this skill after explanation:

```text
structure analysis + explanation artifact -> printable practice HTML
```

The goal is not to create similar problems mechanically. Decide the next teaching move from the diagnosed blocker.

## Inputs

Require:

- `01-structure-analysis.md` or equivalent, including `canonical_solution`, `variation_rules`, and `complexity_budget`.
- `02-student-explanation.html` or equivalent explanation artifact (for context on what the student has already seen).

Fallback:

- If no explanation artifact exists, run `math-student-explanation-html` first.

## Output Artifact

Create:

```text
artifacts/<same-problem-slug>/03-practice.html
```

Use the same A4 print style as the explanation page. Include an answer key after a page break when the user wants a complete teacher version; otherwise include compact standard answers on the last page.
Use or copy `assets/edu-print.css` beside the generated HTML. `assets/print-a4.css` may exist only as a backward-compatible entry point that imports `edu-print.css`.

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

All generated printable HTML must use the shared atomic style system in `assets/edu-print.css`. Do not invent new visual classes unless absolutely necessary. Practice pages are built from fixed teaching components, not from ad-hoc page-specific boxes.

Allowed semantic classes:

- `edu-page`
- `edu-title`
- `edu-subtitle`
- `edu-section`
- `edu-section-title`
- `edu-subsection-title`
- `edu-p`
- `edu-small`
- `edu-math`
- `edu-strong`
- `edu-card`
- `edu-card-soft`
- `edu-card-title`
- `edu-problem-card`
- `edu-problem-title`
- `edu-problem-stem`
- `edu-task-table`
- `edu-object-table`
- `edu-table`
- `edu-route`
- `edu-key-idea`
- `edu-step`
- `edu-step-title`
- `edu-step-why`
- `edu-substep`
- `edu-subproblem`
- `edu-subproblem-title`
- `edu-formula`
- `edu-formula-key`
- `edu-question`
- `edu-question-title`
- `edu-mistake`
- `edu-student-note`
- `edu-teacher-note`
- `edu-practice-problem`
- `edu-practice-title`
- `edu-training-goal`
- `edu-expected-blocker`
- `edu-tag`
- `edu-hint`
- `edu-hint-title`
- `edu-answer-space`
- `edu-answer-lines`
- `edu-answer-steps`
- `edu-answer-step`
- `edu-answer-step-label`
- `edu-answer-key`
- `edu-judge`
- `edu-upgrade`
- `edu-downgrade`
- `edu-review`
- utility classes: `page-break`, `page-break-after`, `no-print`, `u-mt-0`, `u-mb-0`, `u-center`, `u-right`, `u-muted`, `u-small`, `u-avoid-break`

Forbidden:

- Creating ad-hoc classes like `think-box`, `step-box`, `case-box`, `negative-box`, `question-box`, `problem-block`, `problem-section`, `teacher-note`, `mistake-box`, `answer-space`, or `problem`.
- Mixing teacher-only metadata into the student main flow. Use `.edu-teacher-note` and keep it visually separate.
- Using `details` for printable hints unless the details are marked `open` or converted to print-visible `.edu-hint` blocks.
- Placing `.edu-training-goal`, `.edu-expected-blocker`, complexity notes, mastery bands, confidence, upgrade/downgrade rules, or self-check text in the student main flow.
- **学生版练习页不得包含教师判断内容。** 教师判断、训练目标、预期卡点、复杂度说明、档位、置信度、升级/降级建议必须放在 `no-print` 的 `.edu-teacher-note` 或 `.edu-judge` 中；默认打开页面时也应优先呈现学生视角。

```html
<body data-view="student">
<div class="edu-page">
  <h1 class="edu-title">自适应练习：题目短标题</h1>

  <section class="edu-section">
    <h2 class="edu-section-title">练习说明</h2>
    <p class="edu-p">本组只练一个核心动作：...</p>
  </section>

  <section class="edu-practice-problem u-avoid-break">
    <h2 class="edu-practice-title">第 1 题：入口题</h2>
    <p class="edu-p">题目...</p>

    <div class="edu-hint">
      <div class="edu-hint-title">提示一</div>
      <p class="edu-p">指向动作，不给答案。</p>
    </div>
    <div class="edu-hint">
      <div class="edu-hint-title">提示二</div>
      <p class="edu-p">接近列式，但不直接给最终答案。</p>
    </div>

    <div class="edu-answer-steps">
      <div class="edu-answer-step">
        <span class="edu-answer-step-label">① 写出关键对象或关系：</span>
      </div>
      <div class="edu-answer-step">
        <span class="edu-answer-step-label">② 列式并计算：</span>
      </div>
      <div class="edu-answer-step">
        <span class="edu-answer-step-label">③ 检查并写结论：</span>
      </div>
    </div>

    <aside class="edu-teacher-note no-print">
      <div class="edu-card-title">第 1 题教师备忘</div>
      <p class="edu-training-goal"><span class="edu-tag">训练目标</span>...</p>
      <p class="edu-expected-blocker"><span class="edu-tag">预期卡点</span>...</p>
      <p class="edu-small">复杂度说明：为什么没有超过预算。</p>
      <div class="edu-judge">
        <p class="edu-p"><span class="edu-upgrade">升级：</span>若学生...，进入...</p>
        <p class="edu-p"><span class="edu-downgrade">降级：</span>若学生...，回到...</p>
      </div>
    </aside>
  </section>

  <!-- 后续题目之间按需插入 <div class="page-break"></div> -->

  <section class="edu-answer-key page-break">
    <h2 class="edu-section-title u-mt-0">参考答案</h2>
    <div class="edu-step">
      <div class="edu-step-title">第 1 题答案</div>
      <p class="edu-p">标准答案...</p>
    </div>
  </section>

  <!-- 教师判断区：学生打印时不可见 -->
  <aside class="edu-teacher-note no-print">
    <div class="edu-card-title">教师判断</div>
    <p class="edu-p">当前档位：X档。主要错因：...。置信度：...</p>
  </aside>

  <aside class="edu-teacher-note no-print">
    <div class="edu-card-title">升级 / 降级建议</div>
    <div class="edu-judge">
      <p class="edu-p"><span class="edu-upgrade">升级：</span>若学生...，进入...</p>
      <p class="edu-p"><span class="edu-downgrade">降级：</span>若学生...，回到...</p>
    </div>
  </aside>
</div>
</body>
```

## Page Break Rules

打印分页规则：

- 答案区（`.edu-answer-key`）前必须使用 `page-break`，与学生练习内容分页。
- 若题目数量超过一页（约2道大题），在第2题前插入 `<div class="page-break"></div>`。
- 每道练习题（`.edu-practice-problem`）使用 `u-avoid-break` 防止题目被截断跨页。
- 标题（`.edu-section-title`、`.edu-practice-title`、`.edu-step-title`）不允许出现在页面最底部（CSS 已设置 `break-after: avoid`）。
- 若单道题带解答区超过一页，移除该题的 `u-avoid-break`，改用自然的步骤分隔。

## Generation Rules

- Preserve the original problem's core structure.
- Use the canonical solution as a pattern anchor and answer-quality reference.
- For browser preview, set `<body data-view="student">` by default; if a teacher toggle is added, it must be `no-print` and must not appear in the printed student sheet.
- Keep computation controlled; avoid ugly arithmetic unless the original structure requires it.
- Do not introduce unrelated knowledge points.
- Make hints progressive: hint 1 points to the action; hint 2 nearly reveals the setup, not the final answer.
- Include how to judge the student's response after each problem only in a `no-print` teacher note, not beside the student-facing stem.
- Use printable answer space: ruled lines or boxed work area.
- **教师判断（档位、升级/降级、训练目标、预期卡点、复杂度说明）必须放在 `no-print` 的 `.edu-teacher-note` 中，学生在打印版和默认学生视角中看不到这些内容。** 答案区只放标准答案，不放升级/降级建议。

## Mandatory Self-Check

Before finalizing the HTML, solve every generated problem and revise any faulty item. Add a teacher-only self-check block near the end:

```html
<aside class="edu-teacher-note self-check no-print">
  <div class="edu-card-title">生成后自检</div>
  <ul>
    <li><strong>数学检查：</strong>每道题答案是否正确；是否存在漏解、增根、退化值；公式是否适用于本题。</li>
    <li><strong>教学检查：</strong>本页是否只训练一个核心动作；有没有引入无关知识点；提示二是否过早暴露答案；互动问题/判断问题是否围绕本题核心链条。</li>
    <li><strong>档位检查：</strong>当前档位是否由学生证据或诊断 artifact 支持；如果没有学生证据，是否标注“默认诊断”；升级是否只小步上升。</li>
    <li><strong>学生版检查：</strong>教师判断、训练目标、预期卡点、复杂度说明、升级/降级建议是否全部在 `no-print` 区域内；学生打印和默认学生视角是否只看到题目、提示、答案空间和标准答案。</li>
    <li><strong>HTML 检查：</strong>标签是否闭合；是否符合 required sections；是否依赖网络 CDN；是否适合 A4 打印；分页位置是否合理。</li>
    <li><strong>自检结论：</strong>...</li>
  </ul>
</aside>
```

Do not finalize a practice page unless the answer key has been checked against the generated stems.

## Handoff

End with a teacher-only note:

```html
<aside class="edu-teacher-note no-print">
下一轮：根据本页完成情况，更新学生画像；若需讲解新题，回到 math-structure-analysis；若需新一轮变式，再次使用 math-practice-html。工作流循环：math-structure-analysis → math-student-explanation-html → math-practice-html。
</aside>
```
