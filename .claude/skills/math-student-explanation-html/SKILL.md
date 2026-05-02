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

Also create or reuse `assets/print-a4.css` beside the HTML when helpful. The HTML must be standalone enough to open directly, with embedded CSS or a relative stylesheet.

## Mode Rules

### printable_sheet

- Ask questions but do not immediately answer them in the student-facing body.
- Leave blanks or ruled answer space after each check question.
- Put answers in a teacher note, folded section, or final answer area.
- Do not fake interaction with "问：... 答：..." unless the answer is clearly marked as teacher-only.
- For browser preview, set `<body data-view="student">` by default; any teacher-view toggle must be `no-print`.

### live_tutor_script

For each key question, include:

- 预期学生回答；
- 如果答对怎么推进；
- 如果答错怎么提示；
- 如果沉默怎么降级；
- 何时记录学生表现以交给 `math-student-response-diagnosis`。

## HTML Design Rules

- Format for A4 print: `@page { size: A4; margin: 16mm 14mm; }`.
- Use Chinese-friendly fonts: `"SimSun", "Songti SC", "Noto Serif CJK SC", serif` for body; `"SimHei", "Microsoft YaHei", sans-serif` for headings.
- Match mainland China exam/workbook feel: black text, thin borders, modest headings, dense but readable spacing.
- Avoid web-app styling: no gradients, no large hero, no cards-within-cards.
- Keep answer space printable: use ruled blanks, short checkboxes, and small "想一想" boxes.
- Support MathJax if formulas need TeX; include a CDN script only if the user allows network-dependent rendering. Otherwise keep formulas as plain text/HTML.

## Required Sections

Write the page in Chinese for the student unless a section is explicitly teacher-only.

```html
<h1>学生版讲解：题目短标题</h1>
<section>
  <h2>一、先补哪几个动作</h2>
  <p>列出本题需要的前置动作；弱学生先做一个具体数值小例子。</p>
</section>
<section>
  <h2>二、这题先看懂什么</h2>
  <p>用朴素话解释题目场景。</p>
</section>
<section>
  <h2>三、第一步该做什么</h2>
  <p>说明为什么第一步不是套公式，而是找关键点/交点/关系。</p>
</section>
<section>
  <h2>四、关键转化怎么想</h2>
  <p>把后台结构翻译成学生语言。</p>
</section>
<section>
  <h2>五、标准解法</h2>
  <ol>
    <li>每步都写“为什么这么做”。</li>
  </ol>
</section>
<section>
  <h2>六、边讲边问</h2>
  <ol>
    <li>3-5 个检查理解的小问题；按 mode 处理答案位置。</li>
  </ol>
</section>
<section>
  <h2>七、易错提醒</h2>
  <ul>
    <li>2-3 个学生能懂的提醒。</li>
  </ul>
</section>
<section>
  <h2>八、一句话总结</h2>
  <p>一句口诀或流程。</p>
</section>
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
<aside class="teacher-note self-check no-print">
  <h2>生成后自检</h2>
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
<aside class="teacher-note no-print">
下一步：记录学生在“边讲边问”中的回答，先使用 math-student-response-diagnosis 诊断档位，再使用 math-adaptive-practice-html 生成练习。
</aside>
```
