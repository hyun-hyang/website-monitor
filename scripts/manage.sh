#!/usr/bin/env bash
# scripts/manage.sh
export LANG=en_US.UTF-8
export LC_CTYPE=ko_KR.UTF-8
unset LC_ALL

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDDIR="$ROOT/run"
LOGDIR="$ROOT/logs"
PIDFILE="$PIDDIR/website-monitor.pid"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$PIDDIR" "$LOGDIR"

# .env 로드 (선택)
if [ -f "$ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi

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

  "${ROOT}/scripts/install_browser.sh"
  
  # 외부 flock 제거 — 파이썬 내부 fcntl lock(instance.lock) 사용
  nohup "$PYTHON_BIN" "$ROOT/src/website_monitor.py" >> "$LOGDIR/daemon.log" 2>&1 &
  echo $! > "$PIDFILE"
  echo "Started. PID $(cat "$PIDFILE"). Logs: $LOGDIR/daemon.log"
}

stop() {
  if ! is_running; then
    echo "Not running."
    rm -f "$PIDFILE" || true
    exit 0
  fi
  local pid
  pid="$(cat "$PIDFILE")"
  echo "Stopping PID $pid ..."
  kill -TERM "$pid" || true
  for _ in {1..10}; do
    ps -p "$pid" >/dev/null 2>&1 || break
    sleep 1
  done
  if ps -p "$pid" >/dev/null 2>&1; then
    echo "Force kill..."
    kill -KILL "$pid" || true
  fi
  rm -f "$PIDFILE" || true
  echo "Stopped."
}

status() {
  if is_running; then
    echo "Running (PID $(cat "$PIDFILE"))."
    return 0
  else
    echo "Not running."
    return 1
  fi
}

restart() { stop || true; start; }
logs()    { /usr/bin/tail -n 200 -f "$LOGDIR/daemon.log"; }

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) restart ;;
  status) status ;;
  logs) logs ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|logs}"
    exit 1
    ;;
esac