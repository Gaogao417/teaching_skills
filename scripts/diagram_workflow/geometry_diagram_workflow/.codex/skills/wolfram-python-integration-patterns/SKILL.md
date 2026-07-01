---
name: wolfram-python-integration-patterns
description: Use this skill when integrating Wolfram Engine with Python via wolframclient. Covers session management, file loading, error handling, and JSON conversion patterns.
---

# Wolfram Python Integration Patterns

## Trigger Conditions
Use this skill when:
- Using `wolframclient.evaluation.WolframLanguageSession`
- Calling Wolfram functions from Python
- Need to load `.wl` files from Python
- Converting Wolfram Associations to Python dicts
- Handling timeout and timing measurements
- Rendering images or extracting properties

## Core Patterns

### 1. Session Lifecycle

**Best Practice:**
```python
from wolframclient.evaluation import WolframLanguageSession

# GOOD: Use context manager for cleanup
with WolframLanguageSession() as session:
    result = session.evaluate(wlexpr('1 + 1'))
    print(result)
# Session automatically terminated

# OK: Explicit termination (when context manager not suitable)
session = WolframLanguageSession()
try:
    result = session.evaluate(wlexpr('1 + 1'))
    print(result)
finally:
    session.terminate()

# BAD: Forget to terminate (leaks resources)
session = WolframLanguageSession()
result = session.evaluate(wlexpr('1 + 1'))
# Memory leak!
```

### 2. Loading .wl Files

**Pattern A: Get[] with absolute path (RECOMMENDED)**
```python
from pathlib import Path
from wolframclient.language import wlexpr

# GOOD: Get[] handles paths correctly
wl_path = Path("e:/geometricScene-builder/wl/scene_builders.wl").resolve()
session.evaluate(wlexpr(f'Get["{wl_path}"]'))

# Also OK: Join with Path operators
base_dir = Path("e:/geometricScene-builder")
wl_path = base_dir / "wl" / "scene_builders.wl"
session.evaluate(wlexpr(f'Get["{wl_path}"]'))
```

**Pattern B: Use ToFileName[] for path sanitization**
```python
# GOOD: ToFileName[] handles OS-specific path issues
wl_path = r"e:\geometricScene-builder\wl\scene_builders.wl"
sanitized_path = session.evaluate(wlexpr(f'ToFileName["{wl_path}"]'))
session.evaluate(wlexpr(f'Get["{sanitized_path}"]'))
```

**Pattern C: Import[] for inline code**
```python
# GOOD: Import[] for small inline snippets
wl_code = """
  MyFunction[x_] := x^2
"""
session.evaluate(wlexpr(f'Import["{wl_code}"]'))
```

### 3. Timeout and Timing

**Pattern: TimeConstrained[]**
```python
from wolframclient.language import wl

# GOOD: TimeConstrained[] with timeout value
timeout = 60
code = f'''
  TimeConstrained[
    BlockRandom[SeedRandom[{seed}]; RandomInstance[scene]],
    {timeout},
    $Failed
  ]
'''
result = session.evaluate(wlexpr(code))

# Then check result type
if result == wl.symbol('$Failed'):
    print("Timeout!")
else:
    print("Success")
```

**Pattern: AbsoluteTime[] for measurement**
```python
# GOOD: Measure elapsed time with AbsoluteTime[]
code = f'''
  start = AbsoluteTime[];
  result = TimeConstrained[
    RandomInstance[scene],
    60,
    $Failed
  ];
  AbsoluteTime[] - start
'''
elapsed = session.evaluate(wlexpr(code))
```

### 4. Association to Dict Conversion

**Pattern A: Built-in dict() conversion**
```python
# GOOD: Wolfram Associations convert to Python dicts
result = session.evaluate(wlexpr('<|"a" -> 1, "b" -> 2|>'))
# result is: {'a': 1, 'b': 2}

# Access with get()
print(result.get('a'))  # 1

# Safe access with default
print(result.get('c', 'default'))  # 'default'
```

**Pattern B: Normal[] for deeper structures**
```python
# Use Normal[] for nested Associations
code = '''
  assoc = <|"outer" -> <|"inner" -> 123|>|>;
  Normal[assoc]
'''
result = session.evaluate(wlexpr(code))
# result is: {'outer': {'inner': 123}}
```

**Pattern C: Manual iteration**
```python
# If automatic conversion fails, use Keys and Values
assoc = session.evaluate(wlexpr('<|"a" -> 1, "b" -> 2|>'))
keys = session.evaluate(wlexpr('Keys[assoc]'))
values = session.evaluate(wlexpr('Values[assoc]'))
```

### 5. Error Handling Patterns

**Pattern: Check Head and Type**
```python
# GOOD: Verify result type before using
result = session.evaluate(wlexpr('RandomInstance[scene]'))

from wolframclient.language import wl

# Option A: Check Head explicitly
head = session.evaluate(wlexpr(f'Head[{result}]'))
if head == wl.symbol('GeometricScene'):
    print("Valid GeometricScene")
else:
    print(f"Invalid type: {head}")

# Option B: Which[] for branching
status = session.evaluate(wlexpr(f'''
  Which[
    {result} === $Failed,
      "timeout",
    Head[{result}] =!= GeometricScene,
      "invalid_head",
    True,
      "success"
  ]
'''))
```

**Pattern: Try/Catch in Wolfram**
```python
# GOOD: Handle Wolfram-side errors
code = '''
  result = Module[
    {scene},
    Check[AllTrue[scene, ValidQ]];  # May throw
  ];
  If[Head[result] === Error,
    <|"success" -> False, "error" -> ToString[result]|>,
    <|"success" -> True, "data" -> result|>
  ]
'''
result = session.evaluate(wlexpr(code))
```

### 6. Extracting GeometricScene Properties

**Pattern: Access scene attributes**
```python
# GOOD: Use indexed access for scene properties
scene = session.evaluate(wlexpr('RandomInstance[scene]'))

# Extract Graphics
graphics = scene["Graphics"]

# Extract Parameters
params = scene["Parameters"]

# Extract AlgebraicFormulation
algebraic = scene["AlgebraicFormulation"]

# Extract Points
points = scene["Points"]
```

**Pattern: Export Graphics**
```python
# GOOD: Export with ImageSize for consistency
code = f'''
  Export["{image_path}", scene["Graphics"], ImageSize -> 512]
'''
session.evaluate(wlexpr(code))
```

### 7. RandomInstance with UnconstrainedParameters

**Pattern: Enable unconstrained solving**
```python
# GOOD: Allow WL to choose free parameters
code = f'''
  scene = GeometricScene[{{points}}, {{hypotheses}}];
  inst = RandomInstance[scene, UnconstrainedParameters -> All]
'''
result = session.evaluate(wlexpr(code))
```

## Common Mistakes

### Mistake 1: Forgetting to terminate session

**Symptom:**
- Memory leak
- "Too many Wolfram kernels running" error

**Fix:**
```python
# Always use context manager or explicit termination
with WolframLanguageSession() as session:
    # ... do work ...
    pass  # Auto terminated
```

### Mistake 2: Wrong string escaping in wlexpr()

**Symptom:**
```
Syntax::sntxf: "1 + 1" cannot be parsed
```

**Example Mistake:**
```python
# BAD: Double escaping
code = f'SomeFunction["{variable_with_quotes}"]'
session.evaluate(wlexpr(code))  # Breaks if variable contains "
```

**Fix:**
```python
# GOOD: Use wl.String() for quoted strings
from wolframclient.language import wl
code = f'SomeFunction[{wl.String(variable_with_quotes)}]'
session.evaluate(wlexpr(code))

# OR: Escape carefully
code = f'SomeFunction["{variable.replace('"', '\\"')}"]'
```

### Mistake 3: Not handling symbolic vs numeric results

**Symptom:**
```
TypeError: cannot multiply sequence by non-int of type 'Integer'
```

**Fix:**
```python
# GOOD: Convert symbolic to numeric if needed
from wolframclient.language import wl

result = session.evaluate(wlexpr('Solve[x^2 == 4]'))

# Check if numeric
if isinstance(result, (int, float)):
    value = result
else:
    # It might be symbolic, convert
    value = float(session.evaluate(wlexpr(f'N[{result}]')))
```

### Mistake 4: Blocking on render

**Symptom:**
- Benchmark timing includes image export time
- Inconsistent timing results

**Fix:**
```python
# GOOD: Separate solve and render times
# Step 1: Solve only (no render)
code_solve = f'''
  inst = TimeConstrained[
    RandomInstance[scene],
    60,
    $Failed
  ];
  <|"success" -> (inst =!= $Failed)|>
'''
solve_result = session.evaluate(wlexpr(code_solve))

# Step 2: Only render if successful
if solve_result['success']:
    code_render = f'''
      Export["{img_path}", inst["Graphics"], ImageSize -> 512]
    '''
    session.evaluate(wlexpr(code_render))
```

## Performance Optimization

### 1. Reuse Session
```python
# GOOD: One session for multiple evaluations
with WolframLanguageSession() as session:
    # Load modules once
    session.evaluate(wlexpr('Get["common.wl"]'))

    # Run many cases
    for case in cases:
        result = session.evaluate(wlexpr(f'RunCase[{case}]'))
        process(result)

# BAD: Create new session for each case (slow)
for case in cases:
    with WolframLanguageSession() as session:
        # ... slow startup overhead ...
        pass
```

### 2. Batch Operations

```python
# GOOD: Process multiple in one WL call
code = f'''
  results = Table[
    ProcessCase[{case}],
    {{case, cases}}
  ];
'''
results = session.evaluate(wlexpr(code))

# BAD: Sequential calls (slow)
results = []
for case in cases:
    result = session.evaluate(wlexpr(f'ProcessCase[{case}]'))
    results.append(result)
```

## Testing Strategy

### Test 1: Session Cleanup
```python
# test_session_cleanup.py
from wolframclient.evaluation import WolframLanguageSession

# Create multiple sessions, verify cleanup
for i in range(5):
    with WolframLanguageSession() as session:
        result = session.evaluate(wlexpr('1 + 1'))
        print(f"Iter {i}: {result}")
# If this doesn't crash, cleanup works
```

### Test 2: Path Loading
```python
# test_path_loading.py
session = WolframLanguageSession()

# Test different path formats
test_paths = [
    r"e:\geometricScene-builder\wl\module.wl",
    "e:/geometricScene-builder/wl/module.wl",
    Path("e:/geometricScene-builder/wl/module.wl")
]

for path in test_paths:
    try:
        session.evaluate(wlexpr(f'Get["{path}"]'))
        print(f"[OK] {path}")
    except Exception as e:
        print(f"[FAIL] {path}: {e}")
```

### Test 3: Timeout Behavior
```python
# test_timeout.py
session = WolframLanguageSession()

# Test that timeout works
code = '''
  TimeConstrained[
    Pause[Duration[10]],  # 10 seconds
    2,
    $Failed
  ]
'''
result = session.evaluate(wlexpr(code))
print(f"Result: {result}")  # Should be $Failed
```

## References

- WolframClient docs: https://reference.wolfram.com/language/WolframLanguageSession
- GeometricScene: https://reference.wolfram.com/language/ref/GeometricScene
- RandomInstance: https://reference.wolfram.com/language/ref/RandomInstance
- TimeConstrained: https://reference.wolfram.com/language/ref/TimeConstrained
