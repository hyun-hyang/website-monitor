#!/usr/bin/env bash

set -a
[ -f "$(dirname "$0")/.env" ] && source "$(dirname "$0")/.env"
set +a

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDDIR="$ROOT/run"
LOGDIR="$ROOT/logs"
PIDFILE="$PIDDIR/website-monitor.pid"
LOCKFILE="$PIDDIR/website-monitor.lock"
PYTHON_BIN="${PYTHON_BIN:-python3}"   # 필요하면 venv 경로로 바꿔도 됨

mkdir -p "$PIDDIR" "$LOGDIR"

is_running() {
  if [[ -f "$PIDFILE" ]]; then
    local pid
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    [[ -n "${pid}" ]] && ps -p "${pid}" >/dev/null 2>&1
  else
    return 1
  fi
}

start() {
  if is_running; then
    echo "Already running (PID $(cat "$PIDFILE"))."
    exit 0
  fi
  echo "Starting website-monitor (daemon mode)..."
  # flock으로 중복 실행 방지
  nohup flock -n "$LOCKFILE" $PYTHON_BIN "$ROOT/website_monitor.py" >> "$LOGDIR/daemon.log" 2>&1 &
  echo $! > "$PIDFILE"
  echo "Started. PID $(cat "$PIDFILE"). Logs: $LOGDIR/daemon.log"
}

stop() {
  if ! is_running; then
    echo "Not running."
    rm -f "$PIDFILE" "$LOCKFILE" || true
    exit 0
  fi
  local pid
  pid="$(cat "$PIDFILE")"
  echo "Stopping PID $pid ..."
  kill -TERM "$pid" || true
  # 최대 10초 대기
  for i in {1..10}; do
    if ! ps -p "$pid" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ps -p "$pid" >/dev/null 2>&1; then
    echo "Force kill..."
    kill -KILL "$pid" || true
  fi
  rm -f "$PIDFILE" "$LOCKFILE" || true
  echo "Stopped."
}

status() {
  if is_running; then
    echo "Running (PID $(cat "$PIDFILE"))."
    return 0   # 성공
  else
    echo "Not running."
    return 1   # 실패
  fi
}

restart() {
  stop || true
  start
}

logs() { /usr/bin/tail -n 200 -f "$LOGDIR/daemon.log"; }

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  logs) logs ;;          # ← 변경
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac