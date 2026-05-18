# exam-zh LaTeX 映射表

## 题型 → exam-zh 环境

| YAML type | LaTeX 环境 | 说明 |
| --- | --- | --- |
| `choice` | `\begin{question}[points=N]` + `\begin{choices}` | 选择题 |
| `fillin` | `\begin{question}[points=N]` + `\fillin[答案]` | 填空题 |
| `problem` | `\begin{problem}[points=N]` + `\begin{solution}` | 解答题 |
| `short_answer` | `\begin{problem}[points=N]` + `\vspace` + `\begin{solution}` | 简答题 |

## 自定义环境 → edu-print.css 对应

| 自定义环境 | edu CSS class | 颜色/边框 |
| --- | --- | --- |
| `problemcard` | `.edu-problem-card` | 1.5pt 黑边框, 浅灰底 |
| `routemap` | `.edu-route` | 1pt 黑边框, 浅灰底 |
| `keyideabox` | `.edu-key-idea` | 1.5pt 黑边框, 暖白底 |
| `mistakebox` | `.edu-mistake` | 1pt 浅边框, 3pt 红左边框, 暖白底 |
| `hintbox` | `.edu-hint` | 1pt 虚线浅边框, 浅灰底 |
| `thinkbox` | `.edu-question` | 1pt 虚线黑边框 |
| `teachernote` | `.edu-teacher-note` | 1pt 浅边框, 灰底 (teacher 版) |
| `traininggoal` | `.edu-training-goal` | 小字号 (teacher 版) |
| `answerarea` | `.edu-answer-lines` | 横线底纹 |

## 版本渲染规则

```latex
% student 版
\examsetup{
  question/show-answer = false,
  fillin/show-answer = false,
  solution/show-solution = hide,
}
% 不渲染 teachernote, traininggoal 环境

% teacher 版
\examsetup{
  question/show-answer = true,
  fillin/show-answer = true,
  solution/show-solution = show-stay,
}
% 渲染全部环境

% both 版
% 先渲染 student 内容
% \clearpage
% 再渲染 teacher 附加内容
```

## 分页映射

| YAML layout | LaTeX |
| --- | --- |
| `break_before: true` | `\clearpage` |
| `avoid_break: true` | `\needspace{5\baselineskip}` (需 needspace 宏包) |
| answer_key_position | `\clearpage` + 答案页 |

## 数学排版

```text
YAML $...$        → LaTeX $...$
YAML $$...$$      → LaTeX \[ ... \]
自动转义: # → \#, % → \%, & → \&, _ → \_, { → \{, } → \}
不破坏: $...$, \(...\), \[...\]
```
