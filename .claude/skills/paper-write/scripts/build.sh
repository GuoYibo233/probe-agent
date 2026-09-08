#!/usr/bin/env bash
# Build gate: full latexmk pipeline (handles bibtex and multiple passes automatically), extracts error context on failure.
# Usage: build.sh <main.tex>
# Exit code: 0 compile succeeded; 1 failed (error summary already printed)
set -u

TEX="${1:?usage: build.sh <main.tex>}"
TEX="$(realpath "$TEX")"
DIR="$(dirname "$TEX")"
BASE="$(basename "$TEX" .tex)"
LOG="$DIR/$BASE.log"

cd "$DIR"
latexmk -pdf -interaction=nonstopmode -halt-on-error -file-line-error "$BASE.tex" >/dev/null 2>&1
RC=$?

if [ $RC -ne 0 ]; then
    echo "== COMPILE FAILED =="
    # -file-line-error format: ./file.tex:LINE: message; plus classic errors starting with "! "
    grep -nE "^(\./)?[^ :]+\.tex:[0-9]+:|^! " "$LOG" | head -20
    echo "-- context --"
    awk '/^!|\.tex:[0-9]+:/{c=4} c&&c--' "$LOG" | head -40
    exit 1
fi

echo "== COMPILE OK =="
grep -oE "Output written on .+ \([0-9]+ pages?" "$LOG" | tail -1
OVER=$(grep -c "Overfull \\\\hbox" "$LOG")
UNDER=$(grep -c "Underfull \\\\hbox" "$LOG")
echo "Overfull hbox: $OVER   Underfull hbox: $UNDER"
grep -E "Citation .+ undefined|Reference .+ undefined|There were undefined" "$LOG" | sort -u | head -10
exit 0
