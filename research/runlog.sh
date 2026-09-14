#!/usr/bin/env bash
# Run a research script so its output is LIVE, not discovered at the end.
#
# Three things go wrong without this, and all three bit this session:
#   1. `python x.py > file.log` sends stdout to the file, so the task's own output is EMPTY and
#      every attempt to read it says "no output".
#   2. Python line-buffers to a TTY and BLOCK-buffers to a pipe or file, so even the log stays
#      empty for minutes. `-u` turns that off.
#   3. `... | tail -N` cannot stream: tail holds the whole stream until the writer exits, so a
#      long run shows nothing at all until it is already finished.
#
# Usage: research/runlog.sh <logfile> <command...>
set -uo pipefail
LOG="$1"; shift
mkdir -p "$(dirname "$LOG")"
: > "$LOG"
echo "### START $(date -u +%H:%M:%S)  $*" | tee -a "$LOG"
PYTHONUNBUFFERED=1 stdbuf -oL -eL "$@" 2>&1 | tee -a "$LOG"
rc=${PIPESTATUS[0]}
echo "### END $(date -u +%H:%M:%S) rc=$rc" | tee -a "$LOG"
exit $rc
