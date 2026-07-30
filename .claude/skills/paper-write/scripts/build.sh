#!/usr/bin/env bash
# 编译门禁：latexmk 全链路编译（自动处理 bibtex 与多趟），失败时提取错误上下文。
# 用法: build.sh <main.tex>
# 退出码: 0 编译成功；1 失败（错误摘要已打印）
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
    # -file-line-error 格式: ./file.tex:LINE: message；外加 "! " 开头的经典错误
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
