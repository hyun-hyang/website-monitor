#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDDIR="$ROOT/run"
PIDFILE="$PIDDIR/website-monitor.pid"
LOCKFILE="$PIDDIR/website-monitor.lock"

cd "$ROOT"

# 1) manage.sh status로 1차 판단
if ! ./manage.sh status | grep -q "Running (PID"; then
  echo "[watchdog] not running -> start"
  ./manage.sh start
  exit 0
fi

# 2) 래퍼 PID
WRAP_PID="$(sed -n '1p' "$PIDFILE" 2>/dev/null || true)"
if [[ -z "${WRAP_PID:-}" ]] || ! ps -p "$WRAP_PID" >/dev/null 2>&1; then
  echo "[watchdog] wrapper pid missing/dead -> restart"
  ./manage.sh restart
  exit 0
fi

# 3) 본체 파이썬 개수 점검
#    래퍼의 자식 중 website_monitor.py를 찾고,
#    전체에서 떠 있는 website_monitor.py가 여러 개면 고아를 정리
PYS_ALL=($(pgrep -f "/home/.*/website_monitor\.py" || true))
# 래퍼의 자식(트리) 중 website_monitor.py
PYS_CHILD=($(ps --ppid "$WRAP_PID" -o pid= | xargs -r -I{} ps -o pid=,cmd= -p {} | grep "website_monitor.py" | awk '{print $1}' || true))

if (( ${#PYS_CHILD[@]} == 0 )); then
  echo "[watchdog] wrapper is alive but no child python -> restart"
  ./manage.sh restart
  exit 0
fi

if (( ${#PYS_ALL[@]} > 1 )); then
  echo "[watchdog] multiple python website_monitor.py detected -> cleanup orphans"
  # 래퍼 자식 외의 모든 본체를 종료
  for PID in "${PYS_ALL[@]}"; do
    if ! printf '%s\n' "${PYS_CHILD[@]}" | grep -qx "$PID"; then
      echo " - killing orphan $PID"
      kill -TERM "$PID" 2>/dev/null || true
    fi
  done
fi

echo "[watchdog] OK (wrapper $WRAP_PID, child ${PYS_CHILD[*]})"