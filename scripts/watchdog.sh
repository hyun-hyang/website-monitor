#!/usr/bin/env bash
# scripts/watchdog.sh  (repo-root 기준)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MANAGE="${ROOT}/scripts/manage.sh"
PIDDIR="${ROOT}/run"
PIDFILE="${PIDDIR}/website-monitor.pid"
ENTRY_PY="${ROOT}/src/website_monitor.py"
ENTRY_BASENAME="$(basename "$ENTRY_PY")"

# STRICT_KILL=1 이면 중복 인스턴스(고아) 강제 종료
STRICT_KILL="${STRICT_KILL:-0}"

cd "${ROOT}"

# 1) manage.sh status 로 1차 판단
if ! "${MANAGE}" status >/dev/null 2>&1; then
  echo "[watchdog] not running -> start"
  "${MANAGE}" start
  exit 0
fi

# 2) 래퍼 PID 확인
WRAP_PID="$(sed -n '1p' "${PIDFILE}" 2>/dev/null || true)"
if [[ -z "${WRAP_PID:-}" ]] || ! ps -p "${WRAP_PID}" >/dev/null 2>&1; then
  echo "[watchdog] wrapper pid missing/dead -> restart"
  "${MANAGE}" restart
  exit 0
fi

# 2.5) WRAP_PID 자체가 python(ENTRY_PY)을 실행 중이면 OK
if ps -o args= -p "${WRAP_PID}" 2>/dev/null | grep -Fq "${ENTRY_PY}"; then
  echo "[watchdog] OK (wrapper is python: ${WRAP_PID})"
  exit 0
fi

# 3) 래퍼의 프로세스 그룹에서 본체 파이썬 유무 확인
#    - pgid를 구해 같은 그룹 내에서 website_monitor.py 를 찾음
PGID="$(ps -o pgid= -p "${WRAP_PID}" | awk '{print $1}')"
if [[ -z "${PGID:-}" ]]; then
  echo "[watchdog] cannot get PGID -> restart"
  "${MANAGE}" restart
  exit 0
fi

# 같은 PGID의 프로세스 목록에서 엔트리 매칭(경로/베이스네임 둘 다 시도)
mapfile -t PYS_IN_GROUP < <(
  ps -o pid=,cmd= -g "${PGID}" 2>/dev/null \
  | grep -E "[p]ython.*(${ENTRY_PY//\//\\/}|${ENTRY_BASENAME})" \
  | awk '{print $1}'
)

if (( ${#PYS_IN_GROUP[@]} == 0 )); then
  echo "[watchdog] wrapper alive but no python child in PG(${PGID}) -> restart"
  "${MANAGE}" restart
  exit 0
fi

# (선택) 시스템 전체에서 같은 엔트리 다중 실행 여부 체크
mapfile -t PYS_ALL < <(pgrep -f "${ENTRY_BASENAME}" || true)
if (( ${#PYS_ALL[@]} > ${#PYS_IN_GROUP[@]} )); then
  if [[ "${STRICT_KILL}" == "1" ]]; then
    echo "[watchdog] multiple instances detected -> killing orphans"
    for PID in "${PYS_ALL[@]}"; do
      # 우리 PGID 내의 프로세스는 건드리지 않음
      if ! ps -o pgid= -p "$PID" | grep -q "^\s*${PGID}\s*$"; then
        echo " - kill -TERM $PID"
        kill -TERM "$PID" 2>/dev/null || true
      fi
    done
  else
    echo "[watchdog] warning: multiple instances detected (leaving them untouched)"
  fi
fi

echo "[watchdog] OK (wrapper ${WRAP_PID}, pgid ${PGID}, child(s) ${PYS_IN_GROUP[*]})"