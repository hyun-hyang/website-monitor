#!/usr/bin/env bash
# scripts/watchdog.sh  (repo-root 기준, manage.sh 호출)

set -euo pipefail

# ---- 경로 고정: scripts/.. = repo root ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MANAGE="${ROOT}/scripts/manage.sh"
PIDDIR="${ROOT}/run"
PIDFILE="${PIDDIR}/website-monitor.pid"
LOCKFILE="${PIDDIR}/website-monitor.lock"
ENTRY_PY="${ROOT}/src/website_monitor.py"

cd "${ROOT}"

# 1) manage.sh status로 1차 판단 (exit 0/1 활용)
if ! "${MANAGE}" status >/dev/null 2>&1; then
  echo "[watchdog] not running -> start"
  "${MANAGE}" start
  exit 0
fi

# 2) 래퍼 PID 확인 (flock 래퍼 PID)
WRAP_PID="$(sed -n '1p' "${PIDFILE}" 2>/dev/null || true)"
if [[ -z "${WRAP_PID:-}" ]] || ! ps -p "${WRAP_PID}" >/dev/null 2>&1; then
  echo "[watchdog] wrapper pid missing/dead -> restart"
  "${MANAGE}" restart
  exit 0
fi

# 3) 본체 파이썬 프로세스 점검
#    - 전체에서 우리가 띄운 website_monitor.py가 몇 개인지
#    - wrapper의 자식 중 website_monitor.py가 있는지
PYS_ALL=($(pgrep -f "${ENTRY_PY}" || true))

# wrapper의 직/간접 자식들 중에서 website_monitor.py 추적
# (직계만 보면 중간에 shell/flake 등이 있을 수 있어 -a로 커맨드까지 잡고 grep)
PYS_CHILD=($(
  pgrep -P "${WRAP_PID}" -a 2>/dev/null \
    | grep -F "${ENTRY_PY}" \
    | awk '{print $1}' || true
))

if (( ${#PYS_CHILD[@]} == 0 )); then
  echo "[watchdog] wrapper is alive but no child python -> restart"
  "${MANAGE}" restart
  exit 0
fi

if (( ${#PYS_ALL[@]} > 1 )); then
  echo "[watchdog] multiple website_monitor.py detected -> cleanup orphans"
  for PID in "${PYS_ALL[@]}"; do
    # wrapper 자식이 아닌 프로세스는 고아로 간주하고 종료
    if ! printf '%s\n' "${PYS_CHILD[@]}" | grep -qx "${PID}"; then
      echo " - killing orphan ${PID}"
      kill -TERM "${PID}" 2>/dev/null || true
    fi
  done
fi

echo "[watchdog] OK (wrapper ${WRAP_PID}, child ${PYS_CHILD[*]})"