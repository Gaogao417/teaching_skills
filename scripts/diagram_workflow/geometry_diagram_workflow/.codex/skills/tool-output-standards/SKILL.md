---
name: tool-output-standards
description: Use this skill when writing scripts that output JSON to stdout for OpenCode tools. Ensures consistent, machine-readable responses that geo-tools.ts can parse.
---

# Tool Output Standards

## Trigger Conditions
Use this skill when:
- Writing Python scripts that `print()` JSON to stdout
- Scripts will be called by OpenCode custom tools (run_sweep, build_report, launch_rater)
- Need to ensure output is parseable by TypeScript tool wrappers
- Handling errors and success cases consistently

## Required Output Format

### 1. JSON Structure

**Mandatory Fields for Success:**
```json
{
  "status": "ok",
  "<field1>": "<value1>",
  "<field2>": "<value2>"
}
```

**Mandatory Fields for Error:**
```json
{
  "status": "error",
  "message": "<human-readable error description>"
}
```

**Optional Fields:**
- Additional metadata relevant to the operation

### 2. Status Values

**Valid Status Values:**
- `"ok"` - Operation completed successfully
- `"error"` - Operation failed

**NEVER Use:**
- `"success"` / `"failed"` - Inconsistent
- `"done"` - Ambiguous
- HTTP status codes - Wrong domain

## Common Patterns

### Pattern 1: Simple Success Response

**Good:**
```python
print(json.dumps({
    "status": "ok",
    "run_dir": str(out_dir),
    "total_cases": total_count
}))
```

**Bad:**
```python
print("Done! Created", total_count, "cases")  # NOT JSON
print(json.dumps({"success": True}))  # Wrong status field
```

### Pattern 2: Error with Validation

**Good:**
```python
if not config_path.exists():
    print(json.dumps({
        "status": "error",
        "message": f"Config file not found: {config_path}"
    }))
    sys.exit(1)
```

**Bad:**
```python
if not config_path.exists():
    print(f"Error: Config file not found at {config_path}")  # NOT JSON
    sys.exit(1)
```

### Pattern 3: Path in Output

**Good:**
```python
print(json.dumps({
    "status": "ok",
    "run_dir": str(run_dir),  # Convert Path to string
    "report": str(report_path)
}))
```

**Bad:**
```python
print(json.dumps({
    "status": "ok",
    "run_dir": run_dir  # Path object may not serialize correctly
}))
```

### Pattern 4: Mixed Success with Warnings

**Good:**
```python
print(json.dumps({
    "status": "ok",
    "report": str(md_path),
    "html": str(html_path),
    "warnings": ["Some images missing"]  # Optional
}))
```

## Integration with geo-tools.ts

### Expected Behavior of run_sweep

**Script Output:**
```json
{"status":"ok","run_dir":"outputs/run_20260224_120000","total_cases":60}
```

**TypeScript Parse (geo-tools.ts):**
```typescript
const result = JSON.parse(stdout);
if (result.status === "ok") {
  const runDir = result.run_dir;  // Use this
  const totalCases = result.total_cases;
}
```

### Expected Behavior of build_report

**Script Output:**
```json
{
  "status":"ok",
  "report":"outputs/.../report.md",
  "html":"outputs/.../report.html"
}
```

**TypeScript Parse (geo-tools.ts):**
```typescript
const reportOut = runPython(context.worktree, "core/report.py", ["--run_dir", runDir]);
const analysisOut = runPython(context.worktree, "core/analyze.py", ["--run_dir", runDir]);

return JSON.stringify({
  status: "ok",
  report: reportOut,
  analysis: analysisOut
}, null, 2);
```

### Expected Behavior of launch_rater

**Script Output:**
```json
{"status":"ok","ui":"started","run_dir":"outputs/run_20260224_120000"}
```

**Note:** launch_rater uses `spawn()` (async), so stdout check is for startup only.

## Common Mistakes

### Mistake 1: Non-JSON Output

**Symptom:**
- TypeScript `JSON.parse()` fails
- "SyntaxError: Unexpected token D" or similar

**Example Mistake:**
```python
print("Completed successfully!")  # NOT JSON
print(f"Results: {results}")  # NOT JSON
print("=" * 50)  # NOT JSON
```

**Fix:**
```python
# ALWAYS wrap in json.dumps()
print(json.dumps({
    "status": "ok",
    "message": "Completed successfully"
}))
```

### Mistake 2: Wrong Status Field

**Symptom:**
- TypeScript doesn't recognize the status
- Logic branches not executing

**Example Mistake:**
```python
print(json.dumps({
    "success": True,  # WRONG FIELD
    "data": results
}))
```

**Fix:**
```python
print(json.dumps({
    "status": "ok",  # CORRECT FIELD
    "data": results
}))
```

### Mistake 3: Missing Error Handling

**Symptom:**
- Script crashes without JSON output
- TypeScript hangs waiting for response

**Example Mistake:**
```python
try:
    result = process_data()
    print(json.dumps({"status": "ok", "result": result}))
except Exception as e:
    print(f"Error: {e}")  # NOT JSON
    sys.exit(1)  # Exits without JSON!
```

**Fix:**
```python
try:
    result = process_data()
    print(json.dumps({"status": "ok", "result": result}))
except Exception as e:
    print(json.dumps({
        "status": "error",
        "message": str(e)
    }))
    sys.exit(1)
```

### Mistake 4: Mixed Output (Text + JSON)

**Symptom:**
- Parser gets first line (text) or can't find JSON

**Example Mistake:**
```python
print("Starting process...")
result = do_work()
print(json.dumps({"status": "ok", "result": result}))
# TWO lines of output!
```

**Fix:**
```python
# Use logging for debug, stdout for JSON only
import logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
logging.info("Starting process...")

result = do_work()
print(json.dumps({"status": "ok", "result": result}))
```

### Mistake 5: Pretty Print Without Compact Flag

**Symptom:**
- May have newlines that break parsing
- Inconsistent across runs

**Example Mistake:**
```python
print(json.dumps({"status": "ok", "result": result}, indent=2))
# Outputs:
# {
#   "status": "ok",
#   ...
# }
```

**Fix:**
```python
print(json.dumps({"status": "ok", "result": result}))
# One-line JSON: {"status":"ok","result":...}

# Or use separators for compact output
print(json.dumps({"status": "ok", "result": result}, separators=(',', ':')))
```

## Debugging Tips

### 1. Capture Raw Output
```python
# test_output.py
import sys

result = {"status": "ok", "data": "test"}
output = json.dumps(result)

# Show what will be printed
print("DEBUG: Output will be:", file=sys.stderr)
print(output)

# Then verify parse works
parsed = json.loads(output)
print("DEBUG: Parsed back:", file=sys.stderr)
```

### 2. Test TypeScript Parsing
```typescript
// test_parse.ts
const testOutput = '{"status":"ok","run_dir":"test"}';
try {
  const parsed = JSON.parse(testOutput);
  console.log("Parsed:", parsed);
} catch (e) {
  console.log("Parse failed:", e);
}
```

### 3. Validate JSON Structure
```python
# validate_json.py
import json

def validate_output(output_str: str) -> bool:
    try:
        data = json.loads(output_str)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        return False

    # Validate required fields
    if "status" not in data:
        print("Missing 'status' field")
        return False

    if data["status"] not in ["ok", "error"]:
        print(f"Invalid status: {data['status']}")
        return False

    return True
```

## Checklist Before Committing Scripts

1. [ ] All `print()` calls output JSON via `json.dumps()`
2. [ ] Status field is "ok" or "error" (never "success" or "failed")
3. [ ] Error paths print JSON and exit(1)
4. [ ] No plain text print() before/after JSON
5. [ ] No pretty-printing (use default or separators=(',', ':'))
6. [ ] Path objects converted to string before JSON serialization
7. [ ] Exceptions caught and converted to error JSON
8. [ ] Verify TypeScript can parse the output

## References

- JSON spec: https://www.json.org/json-en.html
- Python json module: https://docs.python.org/3/library/json.html
- geo-tools.ts: `e:\geometricScene-builder\.opencode\tools\geo-tools.ts`
