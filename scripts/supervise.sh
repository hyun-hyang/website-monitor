#!/usr/bin/env bash
# scripts/supervise.sh
# 프로세스 감시 및 자동 재시작 래퍼
# - 크래시 시 자동 재시작 (최대 백오프 5분)
# - 워크스페이스 시작 시 자동 실행용

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PIDDIR="${ROOT}/run"
LOGDIR="${ROOT}/logs"
PIDFILE="${PIDDIR}/supervise.pid"
LOCKFILE="${PIDDIR}/supervise.lock"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "${PIDDIR}" "${LOGDIR}"

# .env 로드
if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ROOT}/.env"
  set +a
fi

# 이미 실행 중인지 확인 (flock 기반)
exec 200>"${LOCKFILE}"
if ! flock -n 200; then
  echo "[supervise] 이미 실행 중입니다."
  exit 0
fi

# 현재 PID 저장
echo $$ > "${PIDFILE}"

# 종료 시 정리
cleanup() {
  echo "[supervise] 종료 신호 수신 → 정리 중..."
  if [[ -n "${CHILD_PID:-}" ]] && kill -0 "${CHILD_PID}" 2>/dev/null; then
    kill -TERM "${CHILD_PID}" 2>/dev/null || true
    wait "${CHILD_PID}" 2>/dev/null || true
  fi
  rm -f "${PIDFILE}"
  exit 0
}
trap cleanup SIGTERM SIGINT SIGHUP

# 백오프 설정
BASE_DELAY=5
MAX_DELAY=300
consecutive_failures=0

echo "[supervise] 감시 시작 (PID $$)"

while true; do
  echo "[supervise] $(date '+%Y-%m-%d %H:%M:%S') 모니터링 프로세스 시작..."

  "${PYTHON_BIN}" "${ROOT}/src/website_monitor.py" &
  CHILD_PID=$!

  wait "${CHILD_PID}" 2>/dev/null
  EXIT_CODE=$?

  # 정상 종료(SIGTERM 등)면 루프 탈출
  if [[ ${EXIT_CODE} -eq 0 ]]; then
    echo "[supervise] 프로세스 정상 종료 (exit 0)"
    break
  fi

  consecutive_failures=$((consecutive_failures + 1))
  delay=$(( BASE_DELAY * (2 ** (consecutive_failures - 1)) ))
  if (( delay > MAX_DELAY )); then
    delay=${MAX_DELAY}
  fi

  echo "[supervise] $(date '+%Y-%m-%d %H:%M:%S') 프로세스 비정상 종료 (exit ${EXIT_CODE}), 연속 실패: ${consecutive_failures}회"
  echo "[supervise] ${delay}초 후 재시작..."
  sleep "${delay}"
done

rm -f "${PIDFILE}"
echo "[supervise] 감시 종료"
