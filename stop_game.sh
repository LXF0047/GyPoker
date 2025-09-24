#!/usr/bin/env bash
# stop_game.sh - Stop the pypoker services (backend service + web client)

set -euo pipefail
IFS=$'\n\t'

APP_HOME="/home/pypoker_v03"
PID_DIR="${APP_HOME}/run"
SERVICE_PID="${PID_DIR}/poker_service.pid"
WEB_PID="${PID_DIR}/poker_web.pid"

log()   { printf "[%s] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
warn()  { printf "[%s] [WARN] %s\n" "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2; }

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

log "Stopping web service..."
kill_pidfile "$WEB_PID"

log "Stopping poker service..."
kill_pidfile "$SERVICE_PID"

log "All services stopped."