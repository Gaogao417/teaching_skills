# exam-zh 接口提取：K12 作业场景

## 基本信息

- 版本: v0.2.6 (2025-11-12)
- 基类: `ctexbook` (XeLaTeX, UTF8, scheme=chinese, openany)
- 依赖: TeX Live 2020+

## 直接用于 K12 作业的接口

### 文档类

```latex
\documentclass{exam-zh}
```

### 全局配置

```latex
\examsetup{
  page / size = a4paper,
  page / show-head = false,
  page / show-foot = false,
  sealline / show = false,          % 作业不需要密封线
  font = times,                     % 接近宋体印刷效果
  math-font = xits,                 % 数学字体
}
```

### 题目环境

| 环境 | 用途 | 示例 |
| --- | --- | --- |
| `question` | 选择题/填空题题干 | `\begin{question}[points=4]` |
| `choices` | 选项列表 | `\begin{choices} \item A \item B \end{choices}` |
| `problem` | 解答题 | `\begin{problem}[points=8]` |
| `solution` | 解答/解析 | `\begin{solution} ... \end{solution}` |

### 填空/括号

| 命令 | 用途 |
| --- | --- |
| `\fillin[答案]` | 填空（line 类型） |
| `\paren[答案]` | 选择括号 （ ） |
| `\score{4}` | 分值标记 |

### 答案控制

```latex
\examsetup{
  question / show-answer = true,    % 显示选择/填空答案
  fillin / show-answer = true,      % 显示填空答案
  solution / show-solution = show-stay, % 原位显示解答
}
```

### 排版辅助

| 命令/环境 | 用途 |
| --- | --- |
| `\clearpage` | 分页 |
| `\vspace{25mm}` | 答题区空白 |
| `\examsquare{10}` | 方格纸 |
| `\scoringbox` | 得分框 |

### 标题与元信息

```latex
\title{一次函数专题作业}
\subject{数学 · 八年级}
\maketitle
```

## 暂时不用的接口

| 接口 | 原因 |
| --- | --- |
| `sealline` (密封线) | 作业场景不需要 |
| `\secret` (绝密标记) | 非考试场景 |
| `notice` (注意事项) | 作业不需要 |
| `information` (考生信息栏) | 非考试场景 |
| `select` (连线/匹配) | 暂无此类题型 |
| `material` / `poem` | 非语文场景 |
| `writingbox` (作文格) | 非语文场景 |
| `lineto` (连线题) | 暂无此类题型 |
| `calculations` (计算专栏) | 可用 problem 替代 |
| `multifigures` / `textfigure` | 暂不需要图文混排 |
| `draft` (草稿纸) | 暂不需要 |
| `\ExamPrintAnswer` (学生版生成) | 用自定义 version 控制 |

## 自定义环境需求

exam-zh 不提供但我们需要的：

```latex
% 在 preamble 中定义
\newtcolorbox{problemcard}{...}     % 原题卡片
\newtcolorbox{routemap}{...}        % 解题路线图
\newtcolorbox{keyideabox}{...}      % 关键想法
\newtcolorbox{mistakebox}{...}      % 易错提醒
\newtcolorbox{hintbox}{...}         % 提示
\newtcolorbox{thinkbox}{...}        % 思考题
\newtcolorbox{teachernote}{...}     % 教师备注
\newtcolorbox{traininggoal}{...}    % 训练目标
```

这些环境基于 `tcolorbox` 实现，风格参照 `edu-print.css` 中的配色和边框。
