#!/usr/bin/env bash
# A robust launcher for the pypoker services (backend service + web client)
# Features: pid files, retries, log rotation, port checks, start/stop/restart/status/tail

set -euo pipefail
IFS=$'\n\t'

########################
# Configurable settings #
########################
APP_HOME="/home/pypoker_v03"
PYTHON_BIN="python3"                  # or absolute path, e.g. /usr/bin/python3
VENV_ACTIVATE=""                      # e.g. /home/pypoker_v03/venv/bin/activate (leave empty if none)

# Web app bind
HOST="127.0.0.1"
PORT="5000"

# Gunicorn settings
GUNICORN_BIN="gunicorn"
GUNICORN_WORKER="geventwebsocket.gunicorn.workers.GeventWebSocketWorker"
GUNICORN_TIMEOUT="120"
GUNICORN_WORKERS="1"                  # gevent-based, typically 1 worker with many greenlets

# Process entrypoints
SERVICE_ENTRY="${APP_HOME}/texasholdem_poker_service.py"
WEB_MODULE="client_web:app"

# Logs & PIDs
LOG_DIR="${APP_HOME}/logs"
PID_DIR="${APP_HOME}/run"
SERVICE_LOG="${LOG_DIR}/poker_service.log"
WEB_LOG="${LOG_DIR}/poker_web.log"
SERVICE_PID="${PID_DIR}/poker_service.pid"
WEB_PID="${PID_DIR}/poker_web.pid"
MAX_LOG_SIZE=$((10*1024*1024))   # 10MB

#################################
# Helpers                       #
#################################
mkdir -p "${LOG_DIR}" "${PID_DIR}"

log()   { printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn()  { printf "[%s] [WARN] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }
error() { printf "[%s] [ERROR] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

rotate_log_if_needed() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local size
    size=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo 0)
    if [[ "$size" -ge "$MAX_LOG_SIZE" ]]; then
      local ts
      ts=$(date '+%Y%m%d-%H%M%S')
      mv "$file" "${file}.${ts}.1" || true
      : > "$file"
    fi
  fi
}

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "Required command '$cmd' not found in PATH"
    exit 1
  fi
}

port_in_use() {
  local host="$1" port="$2"
  if command -v ss >/dev/null 2>&1; then
    ss -ltn | awk '{print $4}' | grep -E "(^|:)${port}$" | grep -q "${host}\\|0.0.0.0\\|::" && return 0 || return 1
  elif command -v lsof >/dev/null 2>&1; then
    lsof -i TCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 && return 0 || return 1
  else
    warn "Neither 'ss' nor 'lsof' available; skipping port check"
    return 1
  fi
}

pid_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid=$(cat "$pid_file" 2>/dev/null || echo "")
  [[ -n "$pid" && -d "/proc/$pid" ]] && return 0 || return 1
}

kill_pidfile() {
  local pid_file="$1"
  if pid_running "$pid_file"; then
    local pid
    pid=$(cat "$pid_file")
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$pid_file"
        return 0
      fi
      sleep 0.3
    done
    warn "Process $pid did not stop with SIGTERM; sending SIGKILL"
    kill -9 "$pid" 2>/dev/null || true
    rm -f "$pid_file"
  else
    rm -f "$pid_file" 2>/dev/null || true
  fi
}

activate_venv_if_set() {
  if [[ -n "$VENV_ACTIVATE" ]]; then
    # shellcheck disable=SC1090
    source "$VENV_ACTIVATE"
  fi
}

#################################
# Actions                       #
#################################
start_service() {
  if pid_running "$SERVICE_PID"; then
    warn "Service already running (pid $(cat "$SERVICE_PID"))"
  else
    rotate_log_if_needed "$SERVICE_LOG"
    activate_venv_if_set
    require_cmd "$PYTHON_BIN"
    log "Starting poker service…"
    nohup "$PYTHON_BIN" "$SERVICE_ENTRY" >>"$SERVICE_LOG" 2>&1 &
    echo $! > "$SERVICE_PID"
    log "Service started with pid $(cat "$SERVICE_PID") (log: $SERVICE_LOG)"
  fi
}

start_web() {
  if pid_running "$WEB_PID"; then
    warn "Web already running (pid $(cat "$WEB_PID"))"
  else
    if port_in_use "$HOST" "$PORT"; then
      error "Port ${HOST}:${PORT} already in use. Aborting web start."
      exit 1
    fi
    rotate_log_if_needed "$WEB_LOG"
    activate_venv_if_set
    require_cmd "$GUNICORN_BIN"
    log "Starting web (gunicorn ${WEB_MODULE} on ${HOST}:${PORT})…"
    nohup "$GUNICORN_BIN" \
      --worker-class "$GUNICORN_WORKER" \
      --workers "$GUNICORN_WORKERS" \
      --timeout "$GUNICORN_TIMEOUT" \
      --bind "${HOST}:${PORT}" \
      --pid "$WEB_PID" \
      "$WEB_MODULE" >>"$WEB_LOG" 2>&1 &
    # gunicorn writes PID itself, but ensure pid file exists
    sleep 0.5
    if [[ ! -f "$WEB_PID" ]]; then
      echo $! > "$WEB_PID"
    fi
    log "Web started with pid $(cat "$WEB_PID") (log: $WEB_LOG)"
  fi
}

start_all() {
  start_service
  start_web
}

stop_service() { kill_pidfile "$SERVICE_PID"; log "Service stopped"; }
stop_web()     { kill_pidfile "$WEB_PID";     log "Web stopped"; }
stop_all()     { stop_web; stop_service; }

status() {
  local s="stopped" w="stopped"
  pid_running "$SERVICE_PID" && s="running (pid $(cat "$SERVICE_PID"))"
  pid_running "$WEB_PID" && w="running (pid $(cat "$WEB_PID"))"
  echo "Service: $s"
  echo "Web:     $w"
}

tail_logs() {
  tail -n 200 -F "$SERVICE_LOG" "$WEB_LOG"
}

clean_stale() {
  for f in "$SERVICE_PID" "$WEB_PID"; do
    if [[ -f "$f" ]]; then
      local pid
      pid=$(cat "$f" 2>/dev/null || true)
      if [[ -n "$pid" && ! -d "/proc/$pid" ]]; then
        warn "Removing stale pid file $f (pid $pid not running)"
        rm -f "$f"
      fi
    fi
  done
}

usage() {
  cat <<USAGE
Usage: $0 {start|stop|restart|status|tail|start-service|start-web|stop-service|stop-web}

Environment variables you can override:
  APP_HOME, PYTHON_BIN, VENV_ACTIVATE, HOST, PORT, GUNICORN_BIN, GUNICORN_WORKER,
  GUNICORN_TIMEOUT, GUNICORN_WORKERS, SERVICE_ENTRY, WEB_MODULE,
  LOG_DIR, PID_DIR, MAX_LOG_SIZE
USAGE
}

trap 'error "Unexpected error on line $LINENO"' ERR

main() {
  clean_stale
  case "${1:-}" in
    start)          start_all ;;
    start-service)  start_service ;;
    start-web)      start_web ;;
    stop)           stop_all ;;
    stop-service)   stop_service ;;
    stop-web)       stop_web ;;
    restart)        stop_all || true; start_all ;;
    status)         status ;;
    tail)           tail_logs ;;
    *)              usage; exit 1 ;;
  esac
}

main "$@"