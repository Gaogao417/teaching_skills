# 编译故障排查

## 常见错误

| 错误信息 | 原因 | 修复 |
| --- | --- | --- |
| `Missing $ inserted` | 数学符号在文本模式 | 检查 `$...$` 边界 |
| `Undefined control sequence` | 未知命令 | 检查宏包加载/拼写 |
| `File 'xxx.sty' not found` | 缺少宏包 | 安装 texlive 包 |
| `Extra }, or forgotten $` | 花括号/数学模式不匹配 | 检查嵌套 |
| `Environment xxx undefined` | 未定义环境 | 检查 preamble 定义 |

## 诊断流程

```text
1. 查看 build.log 最后 80 行
2. 搜索 ^! 开头的错误行
3. 定位行号，回到 .tex 文件对应位置
4. 区分：内容错误（改 YAML）vs 模板错误（改模板）
```

## 不做事项

- 不做 OCR
- 不做 PDF 重建
- 不做自动修复（auto-fix）
- 不做复杂宏包检测
