#!/usr/bin/env bash
# scripts/manage.sh  (repo-root 기준 경로 고정)

export LANG=en_US.UTF-8
export LC_CTYPE=ko_KR.UTF-8
unset LC_ALL

set -euo pipefail

# ---- 경로 고정: scripts/.. = repo root ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---- 환경 변수(.env) 로드: repo root ----
set -a
[ -f "${ROOT}/.env" ] && source "${ROOT}/.env"
set +a

# ---- 디렉토리/파일 경로 (전부 루트 기준) ----
PIDDIR="${ROOT}/run"
LOGDIR="${ROOT}/logs"
PIDFILE="${PIDDIR}/website-monitor.pid"
LOCKFILE="${PIDDIR}/website-monitor.lock"
PYTHON_BIN="${PYTHON_BIN:-python3}"      # 필요 시 venv 경로로 바꿔 사용
ENTRY_PY="${ROOT}/src/website_monitor.py"
DAEMON_LOG="${LOGDIR}/daemon.log"

mkdir -p "${PIDDIR}" "${LOGDIR}"

is_running() {
  if [[ -f "${PIDFILE}" ]]; then
    local pid
    pid="$(cat "${PIDFILE}" 2>/dev/null || true)"
    [[ -n "${pid}" ]] && ps -p "${pid}" >/dev/null 2>&1
  else
    return 1
  fi
}

start() {
  if is_running; then
    echo "Already running (PID $(cat "${PIDFILE}"))."
    exit 0
  fi
  if [[ ! -f "${ENTRY_PY}" ]]; then
    echo "Entry script not found: ${ENTRY_PY}" >&2
    exit 1
  fi
  echo "Starting website-monitor (daemon mode)..."
  # flock으로 중복 실행 방지. 백그라운드 PID를 pidfile에 기록
  nohup flock -n "${LOCKFILE}" ${PYTHON_BIN} "${ENTRY_PY}" >> "${DAEMON_LOG}" 2>&1 &
  echo $! > "${PIDFILE}"
  echo "Started. PID $(cat "${PIDFILE}"). Logs: ${DAEMON_LOG}"
}

stop() {
  if ! is_running; then
    echo "Not running."
    rm -f "${PIDFILE}" "${LOCKFILE}" || true
    exit 0
  fi
  local pid
  pid="$(cat "${PIDFILE}")"
  echo "Stopping PID ${pid} ..."
  kill -TERM "${pid}" || true

  # 최대 10초 대기
  for _ in {1..10}; do
    if ! ps -p "${pid}" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  if ps -p "${pid}" >/dev/null 2>&1; then
    echo "Force kill..."
    kill -KILL "${pid}" || true
  fi

  rm -f "${PIDFILE}" "${LOCKFILE}" || true
  echo "Stopped."
}

status() {
  if is_running; then
    echo "Running (PID $(cat "${PIDFILE}"))."
    return 0
  else
    echo "Not running."
    return 1
  fi
}

restart() { stop || true; start; }

logs() {
  /usr/bin/tail -n 200 -f "${DAEMON_LOG}"
}

usage() {
  echo "Usage: $0 {start|stop|restart|status|logs}"
  exit 1
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) restart ;;
  status)  status ;;
  logs)    logs ;;
  *)       usage ;;
esac