# LaTeX 排版规范

## 宏包依赖

```text
exam-zh          % 文档类（基类 ctexbook）
tcolorbox        % 自定义教学盒子
needspace        % 避免孤行
amsmath/amssymb  % 数学符号（exam-zh 已含）
```

## 字体

```text
正文: ctex 默认 (SimSun/Songti SC)
标题: SimHei/Microsoft YaHei (ctex 默认)
数学: STIX/XITS (exam-zh font 设置)
```

## 排版约束

1. A4 纸, 16mm/14mm 边距
2. 正文字号 12pt
3. 标题字号 18pt (大标题) / 13.5pt (节标题) / 12.5pt (小节标题)
4. 行距 1.72 倍
5. 黑色文字, 不使用彩色（升级/降级标记除外）
6. 密集排版, 不使用大量留白

## 文件命名

```text
输入: *.assignment.yaml
中间: 04-assignment.tex
输出: 04-assignment.pdf
日志: build.log
```
