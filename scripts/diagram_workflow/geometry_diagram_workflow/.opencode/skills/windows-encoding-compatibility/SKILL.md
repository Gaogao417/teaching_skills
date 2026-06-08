---
name: windows-encoding-compatibility
description: Use this skill when writing Python scripts that print to stdout on Windows. Avoid Unicode encoding errors with special characters, command chaining issues, and hardcoded paths.
---

# Windows Encoding Compatibility for Python Scripts

## Trigger Conditions
Use this skill when:
- Writing Python scripts that `print()` to stdout
- Scripts will run on Windows with PowerShell or CMD
- Scripts include special characters (checkmarks, arrows, emojis) in output
- Scripts use shell command chaining (&&)
- Hardcoded file paths are used

## Problem Summary

### 1. Special Characters Cause Encoding Errors

**Symptom:**
```
UnicodeEncodeError: 'gbk' codec can't encode character '\u2713' in position 0: illegal multibyte sequence
```

**Root Cause:**
- Windows console often uses GBK or other non-UTF-8 encoding by default
- Special characters like ✓, ❌, ✗, →, ⭐ fail to encode

**Example Mistake:**
```python
print(f"✓ {description}: {path}")  # CRASHES on Windows GBK console
print(f"❌ {description}: {path}")  # CRASHES on Windows GBK console
```

**Correct Approach:**
```python
print(f"[OK] {description}: {path}")   # ASCII-safe
print(f"[FAIL] {description}: {path}")  # ASCII-safe
```

**Alternative with encoding handling:**
```python
import sys
import io

# Use UTF-8 wrapper if needed
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
```

### 2. Command Chaining (&&) Fails in PowerShell

**Symptom:**
```
&& : The term '&&' is not recognized as the name of a cmdlet, function, operable program, or script file.
```

**Root Cause:**
- PowerShell uses `;` as command separator, not `&&`
- CMD supports `&&` but not in all contexts
- Mixing bash-style commands breaks Windows

**Example Mistake:**
```bash
cd "e:\geometricScene-builder" && python core/verify_setup.py  # FAILS in PowerShell
```

**Correct Approaches:**

**Option A: Use PowerShell semicolon:**
```powershell
cd "e:\geometricScene-builder"; python core/verify_setup.py
```

**Option B: Use separate commands:**
```bash
cd "e:\geometricScene-builder"
python core/verify_setup.py
```

**Option C: Use explicit working directory:**
```powershell
python core/verify_setup.py -WorkingDirectory "e:\geometricScene-builder"
```

### 3. Hardcoded Absolute Paths Break Cross-Platform

**Symptom:**
- Script fails when moved to different directory
- CI/CD fails due to different workspace structures

**Example Mistake:**
```python
session.evaluate(wlexpr('Get["e:/geometricScene-builder/wl/scene_builders.wl"]'))  # HARDCODED
```

**Correct Approaches:**

**Option A: Use relative paths from script location:**
```python
import os
script_dir = Path(__file__).parent.resolve()
wl_path = script_dir.parent / "wl" / "scene_builders.wl"
```

**Option B: Use workspace root from environment or config:**
```python
import os
workspace_root = Path(os.getenv('WORKSPACE_ROOT', '.'))
wl_path = workspace_root / "wl" / "scene_builders.wl"
```

**Option C: Pass paths as function parameters:**
```python
def run_wl_module(session, wl_file_path: Path):
    session.evaluate(wlexpr(f'Get["{wl_file_path}"]'))
```

### 4. Path Joining Inconsistency

**Symptom:**
- Mixed forward/backward slashes
- `Path /` operator vs `os.path.join` vs string concatenation

**Best Practice:**
```python
# GOOD: Always use Path objects
base_dir = Path("e:/geometricScene-builder")
wl_file = base_dir / "wl" / "scene_builders.wl"  # Path operator

# OK: os.path.join
wl_file = os.path.join("e:/geometricScene-builder", "wl", "scene_builders.wl")

# BAD: String concatenation
wl_file = "e:/geometricScene-builder/wl/scene_builders.wl"  # OS-specific separator
```

### 5. Python Package Import Order in Verification Scripts

**Symptom:**
```
ModuleNotFoundError: No module named 'plotly'
```

**Best Practice:**
```python
# GOOD: Isolate each import with individual try-except
try:
    import yaml
    print("[OK] pyyaml installed")
except ImportError:
    print("[FAIL] pyyaml NOT installed")

try:
    import plotly
    import pandas
    print("[OK] plotly and pandas installed")
except ImportError as e:
    print(f"[FAIL] plotly/pandas NOT installed: {e}")

# BAD: One big try-except hides which package failed
try:
    import yaml, plotly, pandas, streamlit
except ImportError as e:
    print(f"Some package missing: {e}")  # WHICH one?
```

## Checklist Before Running Scripts on Windows

1. [ ] No special Unicode characters (✓, ❌, ✗, →, ⭐, ★) in print statements
2. [ ] Use [OK]/[FAIL] or PASS/FAIL instead
3. [ ] Avoid `&&` command chaining in Shell tool calls
4. [ ] Use `Path` objects for all path operations
5. [ ] Avoid hardcoded absolute paths, use relative from script location
6. [ ] Use separate try-except blocks for each library import
7. [ ] Test output with `python -m py_compile` to check syntax

## Testing Strategy

### Test 1: Encoding Safety
```python
# test_encoding.py
print("[OK] Test passed")  # Should work everywhere
print("✓ Test failed")      # Will fail on Windows GBK
```

### Test 2: Path Handling
```python
# test_paths.py
from pathlib import Path
base = Path(__file__).parent.resolve()
test_file = base / "data" / "test.json"
print(f"Path: {test_file}")  # Check OS separator handling
```

### Test 3: Command Execution
```python
# test_commands.py
import subprocess
# Test different command separators
result = subprocess.run(["echo", "test1; echo", "test2"], shell=True)
print(result.stdout)
```

## Examples

### Bad Example (Full of Issues)
```python
#!/usr/bin/env python3
"""Buggy verification script"""
import sys
from pathlib import Path

def check_file(path, desc):
    if not path.exists():
        print(f"❌ {desc}: {path}")  # ENCODING ERROR
        return False
    print(f"✓ {desc}: {path}")  # ENCODING ERROR
    return True

# Hardcoded path
wl_path = "e:/geometricScene-builder/wl/module.wl"
```

### Good Example (Fixed)
```python
#!/usr/bin/env python3
"""Robust verification script"""
import sys
from pathlib import Path

def check_file(path, desc):
    if not path.exists():
        print(f"[FAIL] {desc}: {path}")  # ASCII-safe
        return False
    print(f"[OK] {desc}: {path}")  # ASCII-safe
    return True

# Relative from script location
script_dir = Path(__file__).parent.parent.resolve()
wl_path = script_dir / "wl" / "module.wl"
```

## References

- Python stdout encoding on Windows: https://docs.python.org/3/library/sys.html#sys.stdout
- Pathlib cross-platform paths: https://docs.python.org/3/library/pathlib.html
- PowerShell command separators: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_operators
