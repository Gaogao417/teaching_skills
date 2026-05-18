#!/usr/bin/env bash
# compile_latex.sh — Compile .tex to PDF using XeLaTeX.
#
# Usage:
#   bash compile_latex.sh <input.tex>
#
# Output:
#   <dir>/04-assignment.pdf
#   <dir>/build.log
#
# Requirements:
#   xelatex (texlive-xetex) or tectonic
#   exam-zh package

set -euo pipefail

TEX_FILE="${1:?Usage: compile_latex.sh <input.tex>}"

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

# Initialize log
: > "$TEX_DIR/$LOG_NAME"
echo "Build started: $(date)" >> "$TEX_DIR/$LOG_NAME"
echo "Source: $TEX_FILE" >> "$TEX_DIR/$LOG_NAME"
echo "Engine: $ENGINE" >> "$TEX_DIR/$LOG_NAME"
echo "" >> "$TEX_DIR/$LOG_NAME"

# Two passes for cross-references
if [ "$ENGINE" = "tectonic" ]; then
    compile_tectonic 1
    compile_tectonic 2
else
    compile_xelatex 1
    compile_xelatex 2
fi

# Check result
if [ -f "$TEX_DIR/$PDF_NAME" ]; then
    echo ""
    echo "=== SUCCESS ==="
    echo "PDF: $TEX_DIR/$PDF_NAME"
    echo "Log: $TEX_DIR/$LOG_NAME"
    ls -lh "$TEX_DIR/$PDF_NAME"
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
