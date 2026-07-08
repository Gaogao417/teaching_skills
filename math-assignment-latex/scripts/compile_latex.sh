#!/usr/bin/env bash
# compile_latex.sh — Compile .tex to PDF using XeLaTeX.
#
# Usage:
#   bash compile_latex.sh [--strict] <input.tex>
#
# Options:
#   --strict  Treat layout warnings (overfull boxes) as errors
#
# If a corresponding .assignment.yaml exists (in build/ or same dir),
# the script will automatically re-render the .tex before compiling.
#
# Requirements:
#   xelatex (texlive-xetex) or tectonic
#   exam-zh package

set -euo pipefail

STRICT=0
if [[ "${1:-}" == "--strict" ]]; then
    STRICT=1
    shift
fi

# Add local texmf tree so tectonic/xelatex finds exam-zh and other local packages
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${REPO_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi
LOCAL_TEXMF="${SCRIPT_DIR}/../texmf"
export TEXINPUTS="${LOCAL_TEXMF}/tex/latex//:${TEXINPUTS-}"

TEX_FILE="${1:?Usage: compile_latex.sh [--strict] <input.tex>}"

if [ ! -f "$TEX_FILE" ]; then
    echo "Error: File not found: $TEX_FILE" >&2
    exit 1
fi

# Determine paths
TEX_DIR="$(cd "$(dirname "$TEX_FILE")" && pwd)"
TEX_NAME="$(basename "$TEX_FILE")"
PDF_NAME="${TEX_NAME%.tex}.pdf"
LOG_NAME="build.log"

# --- Functions (must be defined before use) ---

summarize_errors() {
    local log_file="$1"

    if grep -q "Missing \$ inserted" "$log_file"; then
        echo "✗ Math mode error: Missing \$ inserted"
    fi
    if grep -q "Undefined control sequence" "$log_file"; then
        echo "✗ Undefined command (check spelling or package)"
    fi
    if grep -q "File .*\.sty.* not found" "$log_file"; then
        echo "✗ Missing package: $(grep -oP "File '([^']+)'" "$log_file" | head -3)"
    fi
    if grep -q "Extra }, or forgotten \$" "$log_file"; then
        echo "✗ Brace/math mismatch: Extra } or forgotten $"
    fi
    if grep -q "LaTeX Error: Environment .* undefined" "$log_file"; then
        echo "✗ Undefined environment: $(grep -oP 'Environment (\w+) undefined' "$log_file" | head -3)"
    fi
    if grep -q "^!" "$log_file"; then
        local error_count
        error_count=$(grep -c "^!" "$log_file")
        echo "✗ Total errors: $error_count"
    fi
}

check_layout_warnings() {
    local log_file="$1"
    local warnings=0

    if grep -q "The upper box part has become overfull" "$log_file"; then
        echo "⚠ tcolorbox content overflow (upper box part overfull)"
        warnings=$((warnings + 1))
    fi

    local hbox_count
    hbox_count=$(grep -cE "Overfull \\\\hbox \([0-9.]+pt too wide\)" "$log_file" || true)
    if [ "$hbox_count" -gt 0 ]; then
        echo "⚠ Overfull \\\\hbox: $hbox_count occurrence(s)"
        grep -E "Overfull \\\\hbox \([0-9.]+pt too wide\)" "$log_file" | head -3
        warnings=$((warnings + 1))
    fi

    local vbox_count
    vbox_count=$(grep -cE "Overfull \\\\vbox \([0-9.]+pt too wide\)" "$log_file" || true)
    if [ "$vbox_count" -gt 0 ]; then
        echo "⚠ Overfull \\\\vbox: $vbox_count occurrence(s)"
        warnings=$((warnings + 1))
    fi

    if [ "$warnings" -gt 0 ]; then
        echo "--- Layout warnings: $warnings ---"
        if [ "$STRICT" -eq 1 ]; then
            echo "❌ Strict mode: build blocked by layout warnings."
            return 1
        else
            echo "ℹ Run with --strict to block on warnings."
            return 0
        fi
    fi
    return 0
}

compile_xelatex() {
    local pass_num="$1"
    echo "--- Pass $pass_num ---"
    cd "$TEX_DIR"
    xelatex \
        -interaction=nonstopmode \
        -halt-on-error \
        -file-line-error \
        "$TEX_NAME" \
        >> "$LOG_NAME" 2>&1 || true
}

compile_tectonic() {
    local pass_num="$1"
    echo "--- Pass $pass_num ---"
    cd "$TEX_DIR"
    tectonic -X compile --keep-logs "$TEX_NAME" >> "$LOG_NAME" 2>&1 || true
}

# --- Main ---

echo "=== Compiling $TEX_NAME ==="
echo "Working directory: $TEX_DIR"

# Auto re-render: if a .assignment.yaml exists for this .tex, re-render first
RENDER_SCRIPT="${SCRIPT_DIR}/render_assignment.py"
YAML_CANDIDATES=()
# Convention: yaml lives in build/ next to the .tex
YAML_CANDIDATES+=("$TEX_DIR/build/${TEX_NAME%.tex}.assignment.yaml" "$TEX_DIR/build/${TEX_NAME%.tex}.*.assignment.yaml")
# Also check same directory
YAML_CANDIDATES+=("$TEX_DIR/${TEX_NAME%.tex}.assignment.yaml" "$TEX_DIR/${TEX_NAME%.tex}.*.assignment.yaml")

FOUND_YAML=""
for pattern in "${YAML_CANDIDATES[@]}"; do
    for f in $pattern; do
        if [ -f "$f" ]; then
            FOUND_YAML="$f"
            break 2
        fi
    done
done

if [ -n "$FOUND_YAML" ] && [ -f "$RENDER_SCRIPT" ]; then
    echo "--- Re-rendering from $(basename "$FOUND_YAML") ---"
    if "$PYTHON_BIN" "$RENDER_SCRIPT" "$FOUND_YAML" --out "$TEX_FILE"; then
        echo "Re-render complete."
    else
        echo "⚠ Re-render failed. Compiling with existing .tex."
    fi
fi

# Pre-compile LaTeX syntax check
CHECK_SCRIPT="${SCRIPT_DIR}/check_latex.py"
if [ -f "$CHECK_SCRIPT" ]; then
    if "$PYTHON_BIN" "$CHECK_SCRIPT" "$TEX_FILE"; then
        : # check passed
    else
        echo "--- LaTeX syntax issues detected (see above) ---"
        echo "Continuing compilation anyway..."
    fi
fi

# Detect engine: xelatex > tectonic
ENGINE=""
if command -v xelatex &>/dev/null; then
    ENGINE="xelatex"
elif command -v tectonic &>/dev/null; then
    ENGINE="tectonic"
else
    echo "Error: No XeLaTeX engine found. Install texlive-xetex or tectonic." >&2
    exit 1
fi
echo "Engine: $ENGINE"

# Tectonic ignores TEXINPUTS, so copy local packages to the working directory.
# xelatex uses TEXINPUTS (set above) so no copy needed.
LOCAL_LATEX_DIR="${LOCAL_TEXMF}/tex/latex"
if [ "$ENGINE" = "tectonic" ] && [ -d "$LOCAL_LATEX_DIR" ]; then
    while IFS= read -r -d '' f; do
        cp "$f" "$TEX_DIR/"
    done < <(find "$LOCAL_LATEX_DIR" -type f \( -name '*.cls' -o -name '*.sty' \) -print0)
fi

# Initialize log
: > "$TEX_DIR/$LOG_NAME"
echo "Build started: $(date)" >> "$TEX_DIR/$LOG_NAME"
echo "Source: $TEX_FILE" >> "$TEX_DIR/$LOG_NAME"
echo "Engine: $ENGINE" >> "$TEX_DIR/$LOG_NAME"
echo "" >> "$TEX_DIR/$LOG_NAME"

# XeLaTeX needs explicit passes for cross-references. Tectonic manages reruns
# within a single invocation, so calling it twice doubles the fixed startup cost.
if [ "$ENGINE" = "tectonic" ]; then
    compile_tectonic 1
else
    compile_xelatex 1
    compile_xelatex 2
fi

# Check result
if [ -f "$TEX_DIR/$PDF_NAME" ]; then
    # --- Post-compile cleanup: move intermediates to build/ ---
    BUILD_DIR="$TEX_DIR/build"
    mkdir -p "$BUILD_DIR"

    # Move build log
    [ -f "$TEX_DIR/$LOG_NAME" ] && mv "$TEX_DIR/$LOG_NAME" "$BUILD_DIR/"

    # Move per-tex log (tectonic --keep-logs produces <name>.log)
    TEX_LOG="${TEX_NAME%.tex}.log"
    [ -f "$TEX_DIR/$TEX_LOG" ] && mv "$TEX_DIR/$TEX_LOG" "$BUILD_DIR/"

    # Move local packages copied for tectonic.
    for f in "$TEX_DIR"/exam-zh.cls "$TEX_DIR"/exam-zh-*.sty "$TEX_DIR"/edu-*.sty; do
        [ -f "$f" ] && mv "$f" "$BUILD_DIR/"
    done

    # Check layout warnings before declaring success
    FINAL_LOG="$BUILD_DIR/$LOG_NAME"
    [ ! -f "$FINAL_LOG" ] && FINAL_LOG="$BUILD_DIR/${TEX_NAME%.tex}.log"
    if [ -f "$FINAL_LOG" ]; then
        if ! check_layout_warnings "$FINAL_LOG"; then
            echo ""
            echo "=== FAILED (layout warnings in strict mode) ==="
            exit 1
        fi
    fi

    echo ""
    echo "=== SUCCESS ==="
    echo "PDF: $TEX_DIR/$PDF_NAME"
    ls -lh "$TEX_DIR/$PDF_NAME"

    # 自动打开生成的 PDF (macOS)
    if command -v open >/dev/null 2>&1; then
        open "$TEX_DIR/$PDF_NAME"
    fi
else
    echo ""
    echo "=== FAILED ==="
    echo "PDF was not generated. Showing last 80 lines of build.log:"
    echo ""
    tail -80 "$TEX_DIR/$LOG_NAME"
    echo ""
    echo "--- Error Summary ---"
    summarize_errors "$TEX_DIR/$LOG_NAME"
    exit 1
fi
