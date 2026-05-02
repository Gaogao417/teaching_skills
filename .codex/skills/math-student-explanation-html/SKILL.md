---
name: math-student-explanation-html
description: Generate a student-facing Chinese math explanation as either a printable A4 HTML worksheet or a live tutor script from a prior structure-analysis artifact, student profile, teaching goal, allowed abstraction level, and interaction mode. Use as stage 2 after math-structure-analysis, especially when the output should look like mainland China exam or workbook material and be easy to print.
---

# Math Student Explanation HTML

## Purpose

Use this skill as stage 2:

```text
structure analysis + student profile + teaching goal + mode -> explanation artifact
```

Transform backend structure into a lesson the student can actually cross. Do not expose the full structure analysis.

## Inputs

Require:

- `01-structure-analysis.md` or equivalent structure analysis with `canonical_solution`.
- Student profile: current level, common blockers, recent performance, teacher goal.

Accept:

- `mode`: `printable_sheet` or `live_tutor_script`.
- If omitted, default to `printable_sheet`.

Default assumptions when profile is thin:

- Student's abstraction ability is weaker than the problem solver expects.
- The student may not know why actions connect: graph -> intersection -> coordinate difference -> formula -> equation.
- Teach actions first, concepts second.

## Pre-Action Chain

Before explaining the main solution, decide which prerequisite actions the problem depends on:

- 会不会找 x 轴交点？
- 会不会找 y 轴交点？
- 会不会找与 `x=a` 的交点？
- 会不会找与 `y=b` 的交点？
- 会不会把坐标差看成长度？
- 会不会解释为什么面积要取正、为什么可能出现绝对值？
- 会不会把“两个图像交点”理解成“两个表达式同时成立”？

If the student profile is weak, first include a concrete numeric warm-up that trains the needed actions before entering a parameterized or abstract version.

## Output Artifact

For `printable_sheet`, create:

```text
artifacts/<same-problem-slug>/02-student-explanation.html
```

For `live_tutor_script`, create:

```text
artifacts/<same-problem-slug>/02-live-tutor-script.html
```

Also create or reuse `assets/edu-print.css` beside the HTML. `assets/print-a4.css` may exist only as a backward-compatible entry point that imports `edu-print.css`. The HTML must be standalone enough to open directly, with embedded CSS or a relative stylesheet.

## Mode Rules

### printable_sheet

- Ask questions but do not immediately answer them in the student-facing body.
- Leave blanks or ruled answer space after each check question.
- Put answers in a teacher note, folded section, or final answer area.
- Do not fake interaction with "问：... 答：..." unless the answer is clearly marked as teacher-only.

### live_tutor_script

For each key question, include:

- 预期学生回答；
- 如果答对怎么推进；
- 如果答错怎么提示；
- 如果沉默怎么降级；
- 何时记录学生表现以交给 `math-student-response-diagnosis`。

## HTML Design Rules

- All generated printable HTML must use the shared atomic style system in `assets/edu-print.css`.
- Do not invent new visual classes unless absolutely necessary. Prefer choosing and combining existing `edu-*` classes.
- Match mainland China exam/workbook feel through the style system: black text, thin borders, modest headings, dense but readable spacing.
- Avoid web-app styling: no gradients, no large hero, no cards-within-cards.
- Keep answer space printable: use `.edu-blank-line`, `.edu-answer-lines`, `.edu-answer-space`, or `.edu-answer-steps`.
- Support MathJax if formulas need TeX; include a CDN script only if the user allows network-dependent rendering. Otherwise keep formulas as plain text/HTML.

### Allowed Atomic Classes

Use these semantic classes as the fixed vocabulary for layout and teaching elements:

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
- utility classes: `page-break`, `no-print`, `u-mt-0`, `u-mb-0`, `u-center`, `u-right`, `u-muted`, `u-small`, `u-avoid-break`

Forbidden:

- Creating ad-hoc classes like `think-box`, `step-box`, `case-box`, `negative-box`, `question-box`, `problem-block`, `problem-section`, `teacher-note`, `mistake-box`, `answer-space`, or `problem`.
- Starting the explanation body before an `.edu-problem-card`.
- Mixing teacher-only metadata into the student main flow. Use `.edu-teacher-note` and keep it visually separate.
- Using `details` for printable hints unless the details are marked `open` or converted to print-visible `.edu-hint` blocks.

## Required Sections

Write the page in Chinese for the student unless a section is explicitly teacher-only.

```html
<body>
<div class="edu-page">
  <h1 class="edu-title">学生版讲解：题目短标题</h1>
  <p class="edu-subtitle">主题标签：...</p>

  <section class="edu-problem-card">
    <div class="edu-problem-title">原题</div>
    <p class="edu-problem-stem">完整题目放这里。</p>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">一、先把题目拆开</h2>
    <table class="edu-table edu-task-table">
      <tr><th>已知条件</th><td>...</td></tr>
      <tr><th>要求目标</th><td>...</td></tr>
      <tr><th>关键词</th><td>...</td></tr>
      <tr><th>容易忽略</th><td>...</td></tr>
    </table>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">二、这题准备怎么走</h2>
    <div class="edu-route">
      <ol>
        <li>只写路线顺序，不展开计算。</li>
      </ol>
    </div>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">三、关键想法</h2>
    <div class="edu-key-idea">把后台结构翻译成一个具体动作。</div>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">四、标准解法</h2>
    <div class="edu-subproblem">
      <div class="edu-subproblem-title">第(1)问</div>
      <div class="edu-step">
        <div class="edu-step-title">第 1 步：动作</div>
        <p class="edu-p">计算。</p>
        <p class="edu-step-why">为什么：...</p>
      </div>
    </div>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">五、边讲边问</h2>
    <div class="edu-question">
      <div class="edu-question-title">想一想 1</div>
      <p class="edu-p">检查理解的小问题。</p>
      <span class="edu-blank-line"></span>
    </div>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">六、易错提醒</h2>
    <div class="edu-mistake"><strong>易错点：</strong>每个提醒只讲一个错点。</div>
  </section>

  <section class="edu-section">
    <h2 class="edu-section-title">七、一句话总结</h2>
    <div class="edu-key-idea">一句流程或口诀。</div>
  </section>
</div>
</body>
```

## Teaching Rules

- Use `canonical_solution` from the structure analysis as the answer anchor; do not independently invent a conflicting solution.
- Once per key move, ask one small question before continuing.
- Introduce only one new idea at a time.
- Replace abstract phrases with concrete actions. If using "转化", immediately explain the action.
- Do not say "显然" unless the next sentence explains why.
- Use likely student wording for misconceptions, then correct it gently.
- Make the solution complete enough for checking, but not so long that it becomes a teacher monologue.

## Mandatory Self-Check

Before finalizing the HTML, inspect and revise the artifact. Add a teacher-only self-check block near the end:

```html
<aside class="edu-teacher-note self-check">
  <div class="edu-card-title">生成后自检</div>
  <ul>
    <li><strong>数学检查：</strong>答案是否与 canonical solution 一致；是否漏解、增根、退化值；所用公式是否适用于本题。</li>
    <li><strong>教学检查：</strong>本页是否只训练一个核心动作；是否引入无关知识点；提示二是否过早暴露答案；互动问题是否围绕本题核心链条。</li>
    <li><strong>档位检查：</strong>学生档位是否由学生画像或教师输入支持；若没有学生证据，是否标注默认假设；讲解升级是否只小步上升。</li>
    <li><strong>HTML 检查：</strong>标签是否闭合；是否包含 required sections；是否依赖网络 CDN；是否适合 A4 打印。</li>
    <li><strong>自检结论：</strong>...</li>
  </ul>
</aside>
```

If using MathJax or any CDN, explicitly state the dependency in the HTML check. Prefer no network dependency unless the user asks for it.

## Handoff

At the end of the HTML, include a small teacher-only print note:

```html
<aside class="edu-teacher-note">
下一步：记录学生在“边讲边问”中的回答，先使用 math-student-response-diagnosis 诊断档位，再使用 math-adaptive-practice-html 生成练习。
</aside>
```
