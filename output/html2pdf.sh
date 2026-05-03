#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: html2pdf.sh <html_file> [output_pdf]"
  echo "Example: html2pdf.sh 02-explanation.html"
  echo "Example: html2pdf.sh 02-explanation.html output.pdf"
  exit 1
fi

html="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"

if [ ! -f "$html" ]; then
  echo "Error: $html not found"
  exit 1
fi

if [ $# -ge 2 ]; then
  pdf="$2"
else
  pdf="${html%.html}.pdf"
fi

if command -v chrome &>/dev/null; then
  chrome=chrome
elif [ -f "/mnt/c/Program Files/Google/Chrome/Application/chrome.exe" ]; then
  chrome="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"
elif [ -f "C:/Program Files/Google/Chrome/Application/chrome.exe" ]; then
  chrome="C:/Program Files/Google/Chrome/Application/chrome.exe"
else
  echo "Error: Chrome not found"
  exit 1
fi

echo "Printing: $html"
echo "Output:   $pdf"

"$chrome" --headless --disable-gpu --no-sandbox --no-pdf-header-footer \
  --print-to-pdf="$pdf" "file:///$html" 2>/dev/null

if [ -f "$pdf" ]; then
  echo "Done: $pdf"
else
  echo "Error: PDF not generated"
  exit 1
fi
