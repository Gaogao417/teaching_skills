---
name: wolframclient-usage-guide
description: Wolfram Client Library 正确使用指南。在处理 Python 与 Wolfram Language 之间的数据转换时，必须使用 wl 构造函数而非字符串插值。
---

# Wolfram Client Library 正确使用指南

## 核心原则

### 1. 优先直接传 Python/wl 类型给 evaluate()

文档 [Serialization](https://reference.wolfram.com/language/WolframClientForPython/docpages/basic_usages.html#serialization) 表明：`session.evaluate()` 接受 Python 对象和 wl 表达式，库会自动序列化（通常走 WXF）发送给 kernel。

```python
# 正确：直接传 Python/wl 表达式
session.evaluate(wl.MinMax([1, 5, -3, 9]))  # Python list 自动转 List
session.evaluate(Global.SolveSingleCase(problem_id, points_wl, ...))  # wl 表达式直接传
```

只有在需要 **InputForm 字符串**（如拼 wlexpr、写文件）时才用 `export()`：`export([1,2,3])` -> `b'{1, 2, 3}'`。

#### 错误方式（不要用）

```python
# ❌ 错误：字符串插值
wl_expr = f"points = {points}"  # 这只是字符串，不会执行

wl_expr = f"Module[{{points}}]"  # 不会展开

# ❌ 错误：直接使用 Python 列表/字典
wl_expr = f"SolveSingleCase[{problem_id}, {points}]"  # 会被当作字符串
```

#### 正确方式

```python
# ✅ 正确：使用 wl.List() 构造列表
wl_expr = wl.List([wl.Symbol("a"), wl.Symbol("b"), wl.Symbol("c")])

# ✅ 正确：使用 wl.Association() 构造关联
wl_expr = wl.Association([
    ("name", "Alice"),
    ("age", 30),
    ("city", "NYC")
])

# ✅ 正确：使用 wl.Symbol() 和 wl.Function()
wl_expr = wl.Function(wl.Symbol("x"), wl.Power(wl.Symbol("x"), 2))

# ✅ 正确：将 Python 列表转换为 WL 列表
python_list = [1, 2, 3, 4, 5]
wl_expr = wl.List(python_list)

# ✅ 正确：将 Python 字典转换为 WL Association
python_dict = {"name": "Alice", "age": 30, "city": "NYC"}
wl_expr = wl.Association([("name", python_dict["name"]), ("age", python_dict["age"]), ("city", python_dict["city"])])
```

### 2. 常用 wl 构造函数

| 函数 | 用途 | 示例 |
|--------|------|------|
| `wl.List([...])` | 创建 WL 列表 | `wl.List([1, 2, 3])` |
| `wl.Association([...])` | 创建 WL 关联（字典） | `wl.Association([("a", 1), ("b", 2)])` |
| `wl.Function(...)` | 创建 WL 函数 | `wl.Function(wl.Symbol("x"), wl.Power(wl.Symbol("x"), 2))` |
| `wl.Module(...)` | 加载 WL 模块 | `wl.Module("MyModule")` |
| `wl.Symbol(...)` | 创建 WL 符号 | `wl.Symbol("x")` |
| `wl.Rule(...)` | 创建替换规则 | `wl.Rule(x + 1, y + 1)` |
| `wl.Global(...)` | 创建全局变量 | `wl.Global.f[x_] := x^2` |
| `wl.Evaluate(...)` | 评估表达式 | `wl.Evaluate(wl.Integrate[x, x])` |
| `wlexpr(...)` | 将 InputForm 字符串转为表达式 | `wlexpr("f[x_] := x + 1")` |
| `wl.N(...)` | 创建 Named 函数 | `wl.N(f, x)` |

### 3. Python 数据类型 → Wolfram 类型映射

| Python 类型 | Wolfram 类型 | 构造方法 |
|-----------|-------------|----------|
| `list` | `List` | `wl.List(python_list)` |
| `dict` | `Association` | `wl.Association([("k", v) for k, v in python_dict.items()])` |
| `str` | `String` | 直接传递字符串 |
| `int`/`float` | `Integer`/`Real` | `wl.Integer(42)` / `wl.Real(3.14)` |
| `bool` | `Boolean` | `wl.TrueQ` / `wl.FalseQ` |
| `None` | `None` | 直接使用 `wl.Null` |
| `set`/`frozenset` | `wl.Symbols(python_set)` |

### 4. 获取 WL 模块定义的函数

如果 WL 模块定义了函数（如 `SolveSingleCase`），需要先加载模块，然后直接调用：

```python
# ✅ 正确
session.evaluate(wlexpr('Get["path/to/module.wl"]'))
session.evaluate(wlexpr('Get["path/to/scene_builders.wl", "path/to/bench_core.wl"]'))

# 获取函数后直接调用
session.evaluate(wlexpr('SolveSingleCase[...]'))
```

### 5. WL 表达式中的嵌套结构

在 WL 中，`Module[...]` 是参数列表，`Block[...]` 是语句块：

```wolfram
(* ✅ 正确：Module 包含多个参数 *)
Module[
  {points, baseHypotheses, layers},
  points = {points},
  baseHypotheses = baseHypotheses,
  layers = {layers},
  result = SolveSingleCase[...]
]
```

**关键点**：
- `Module` 的参数用逗号分隔，不是分号
- 在 `Module` 内部，可以用 `result = SolveSingleCase[...]` 获取返回值
- 不要用字符串插值 `"{layers}"`，直接传递变量

### 6. 时间与数值处理

使用 `wl.Quantity()` 创建带单位的量：

```python
# ✅ 正确
time_s = wl.Quantity(solve_time, "Seconds")
```

### 7. 处理返回的 WL Association

WL 返回的 `Association` 会自动转换为 Python 字典：

```python
# WL 返回
Association["success" -> True, "solve_time_s" -> 2.34]

# 自动转为 Python
{
    "success": True,
    "solve_time_s": 2.34
}
```

### 8. 常见错误模式

#### 错误 1：混淆 Python 列表和 WL 列表

```python
# ❌ 错误：直接传递 Python 列表
wl_expr = f"SolveSingleCase[{problem_id}, {points_list}]"

# 结果：SolveSingleCase 会把 Python 列表当作字符串 "[1, 2, 3]"
```

```python
# ✅ 正确：使用 wl.List 展开列表
points_wl = wl.List(*[wl.Symbol(p) for p in points])
wl_expr = wl.Function(wl.Symbol("SolveSingleCase"), problem_id, points_wl, ...)
```

#### 错误 2：混淆 Python 字典和 WL Association

```python
# ❌ 错误：使用字符串插值构建 Association
wl_expr = f"""Association[
  "problem_id" -> "{problem_id}",
  "points" -> {points},
  "baseHypotheses" -> {base_hypotheses}
]"""

# 问题：f-string 中的 {points} 不会展开，会被当作字符串字面量
```

```python
# ✅ 正确：使用 wl.Association 构建键值对
wl_assoc = wl.Association([
    ("problem_id", problem_id),
    ("points", wl.List([wl.Symbol(p) for p in points])),
    ("baseHypotheses", base_hypotheses)
])
wl_expr = wl.Association(wl_assoc)
```

#### 错误 3：在 wlexpr 中过度嵌套

```python
# ❌ 错误：多层嵌套 wlexpr
wl_expr = wlexpr(f"""
Module[
  {{points, baseHypotheses, layers}},
  points = {points},
  SolveSingleCase[{problem_id}, ...]
]
""")
```

```python
# ✅ 正确：使用 wl.Function 和 wl.Module
wl_expr = wl.Function(
    wl.Symbol("SolveAndMeasure"),
    wl.List([wl.Symbol("scene"), wl.Symbol("seed"), wl.Symbol("timeout")])
)
```

### 9. 调试技巧

#### 使用 ToInputForm 查看实际 WL 表达式

```python
expr = wl.List([1, 2, 3])
print(session.evaluate(wl.ToInputForm(expr)))
# 输出: List[1, 2, 3]
```

#### 在 Python 端构造 WL 表达式时使用 wl.*

不要混用 Python 字面量和 wl 函数：

```python
# ❌ 错误：混用
wl_expr = f"Module[{points}]" + wl.Evaluate(...)

# ✅ 正确：全程使用 wl 构造
wl_expr = wl.Module([points, baseHypotheses], layers)
```

### 10. 验证清单

在编写 Wolfram 调用代码前，检查：

- [ ] 是否使用了字符串插值 `f"{var}"` 而非 `wl.List([...])`
- [ ] 是否直接传递 Python 列表 `wl_expr = f"func[{list}]"` 而非 `wl.Function(..., wl.List(...))`
- [ ] 是否使用了 `wl.Association([...])` 构建键值对，而非字符串插值
- [ ] 是否正确使用了 `wlexpr(...)` 而非 f-string
- [ ] WL 模块是否已加载：`Get["path/to/module.wl"]`
- [ ] 是否使用了 `wl.ToInputForm()` 来调试表达式结构

### 11. 典型案例

#### 案例 1：构建 Layer 列表

```python
# ❌ 错误
layers = []
for layer_type in [L1, L2, L3]:
    layers.append(f"BuildLayer{layer_type}[points, {param}]")  # 错误！

# ✅ 正确：使用 wl.List 构建函数调用列表
layer_functions = [
    lambda p: wl.Function(wl.Symbol("BuildLayer1"), ...),
    lambda p: wl.Function(wl.Symbol("BuildLayer2"), ...),
    lambda p: wl.Function(wl.Symbol("BuildLayer3"), ...)
]
layers = wl.List(*[layer_functions])
```

#### 案例 2：处理配置参数

```python
# ❌ 错误：字符串插值
config_yaml = """
timeout: {timeout}
render: {render}
"""

# ✅ 正确：使用 wl.Association
config_wl = wl.Association([
    ("timeout", wl.Integer(timeout)),
    ("render", wl.Boolean(render))
])
```

#### 案例 3：调用带可选参数的函数

```python
# ❌ 错误
wl_expr = f"TimeConstrained[{scene}, {timeout}, $Failed]"  # 参数位置可能错误

# ✅ 正确：命名参数 + 使用规则
wl_expr = wl.TimeConstrained(scene, timeout, wl.Rule[TimeConstrained, "$Failed" -> wl.Null])
```

### 12. Session 生命周期管理

**核心原则**：`WolframLanguageSession` 必须在 `try` 块内创建，并在 `finally` 中终止，防止泄露。

#### 错误方式（可能泄露）

```python
# ❌ 错误：session 在 try 块外创建
session = WolframLanguageSession(...)

# 如果下面的代码抛出异常，session 不会被终止
results_path = out_dir / "results.jsonl"
results_file = open(results_path, "a")

try:
    # 主逻辑...
finally:
    session.terminate()  # 如果上面异常，这里不会执行
```

**问题**：如果在创建 session 之后、进入 try 块之前发生异常（如文件打开失败），session 会泄露，导致 Wolfram Kernel 进程残留。

#### 次选方式（try/finally）

```python
# ⚠️ 次选：使用 try/finally（当无法使用 with 时）
session = None
try:
    session = WolframLanguageSession(...)
    
    # 主逻辑...
    
finally:
    if session is not None:
        session.terminate()  # 安全检查
```

#### 最佳方式（推荐）

```python
# ✅ 最佳：使用 with 语句（上下文管理器）
with WolframLanguageSession(...) as session:
    # 自动管理生命周期
    result = session.evaluate(...)
# 退出时自动调用 terminate()，即使发生异常
```

**优点**：
- 代码更简洁，无需手动 `terminate()`
- 即使块内 `return`/`break`/异常，也会自动清理
- 符合 Pythonic 风格（RAII 模式）
- 防止 orphan kernel 进程残留

### 13. 参考资料

- [Wolfram Client Library 文档](https://reference.wolfram.com/language/WolframClientForPython/docpages/basic_usages.html)
- [Expression Representation](https://reference.wolfram.com/language/WolframClientForPython/docpages/expression_representation.html)
- [Serialization](https://reference.wolfram.com/language/WolframClientForPython/docpages/serialization.html)
- [Session Management](https://reference.wolfram.com/language/WolframClientForPython/docpages/basic_usages.html#expression-evaluation-local-session-management)
