# latex-document-skill 提取：工程链路借鉴

## 基本信息

- 仓库: `https://github.com/ndpvt-web/latex-document-skill`
- 核心脚本: `compile_latex.sh` (739行), `validate_latex.py` (427行)

## 借鉴的工程思想

### 1. 编译脚本核心逻辑

```
compile_latex.sh 值得借鉴:
- 自动检测引擎 (xelatex/lualatex/pdflatex)
- 至少编译 2 次以解决引用
- 失败时解析 log 文件提取可读错误摘要
- --verbose / --quiet 模式
- texfot 过滤噪音输出
```

我们的编译脚本简化版:
```bash
# 固定 xelatex（中文数学作业）
# 编译 2 次
# 提取常见错误摘要
# 不做自动修复
```

### 2. 预编译验证

```
validate_latex.py 值得借鉴:
- \begin/\end 配对检查
- 数学环境边界检查
- 特殊字符检查
```

我们简化为:
```python
# 检查 \begin/\end 配对
# 检查常见未转义字符
# 不做复杂上下文分析
```

### 3. 错误摘要模式

```
原脚本的模式:
grep "Missing \$ inserted" build.log
grep "Undefined control sequence" build.log
grep "File .* not found" build.log
grep "Extra }" build.log
grep "Environment .* undefined" build.log
```

我们直接复用这个错误识别列表。

### 4. PDF 预览

```
pdf_to_images.sh:
- 使用 pdftoppm 转换为 PNG
- 200 DPI 默认
- 自动安装依赖
```

MVP 阶段不做，后续可加。

## 不要搬的功能

| 功能 | 原因 |
| --- | --- |
| `--auto-fix` 自动修复 | 危险，可能改坏内容 |
| `--pdfa` PDF/A 模式 | 作业不需要归档标准 |
| `--use-latexmk` | 过于复杂，固定 2 次 xelatex 足够 |
| bibtex/biber 支持 | 作业无参考文献 |
| makeindex 支持 | 作业无索引 |
| CSV/JSON 邮件合并 | 不适用 |
| Graphviz/PlantUML/Mermaid | 不适用 |
| PDF 加密/表单填写 | 不适用 |
| `convert_document.sh` (Pandoc) | 不适用 |
| 30+ 模板文件 | 我们用 exam-zh 自定义模板 |
| `.chktexrc` lint 配置 | MVP 不需要 lint |
| `pdf_validate_boxes.py` | 过度工程化 |

## 最终借鉴清单

```text
✅ 编译脚本框架 (简化版)
✅ 错误日志摘要逻辑
✅ 预编译验证思路 (简化版)
✅ 目录组织方式 (scripts/references/templates)

❌ 自动修复
❌ 多引擎支持
❌ latexmk 集成
❌ PDF/A/PDF 预览
❌ 全部模板和参考文档
❌ chktex lint
❌ Pandoc 转换
❌ 邮件合并
❌ 图表工具
```
