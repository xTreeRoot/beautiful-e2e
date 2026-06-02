#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${BEAUTIFUL_E2E_RUNTIME_DIR:-/tmp/beautiful-e2e-dev}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_LAUNCHCTL_LABEL="beautiful-e2e-backend"
FRONTEND_LAUNCHCTL_LABEL="beautiful-e2e-frontend"

BACKEND_PID_FILE="$RUNTIME_DIR/backend.pid"
FRONTEND_PID_FILE="$RUNTIME_DIR/frontend.pid"
BACKEND_LOG="$RUNTIME_DIR/backend.log"
FRONTEND_LOG="$RUNTIME_DIR/frontend.log"

mkdir -p "$RUNTIME_DIR"

print_usage() {
  cat <<EOF
用法：
  ./dev.sh start    重启后端和前端。默认执行该动作。
  ./dev.sh stop     停止后端和前端。
  ./dev.sh restart  重启后端和前端。
  ./dev.sh status   查看进程状态。
  ./dev.sh logs     查看日志文件路径。

环境变量：
  BACKEND_PORT=$BACKEND_PORT
  FRONTEND_PORT=$FRONTEND_PORT
  BEAUTIFUL_E2E_RUNTIME_DIR=$RUNTIME_DIR
EOF
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "缺少命令：$command_name"
    return 1
  fi
}

is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

kill_tree() {
  local pid="$1"
  local children=""

  if ! is_running "$pid"; then
    return 0
  fi

  children="$(pgrep -P "$pid" 2>/dev/null || true)"
  for child in $children; do
    kill_tree "$child"
  done

  kill "$pid" >/dev/null 2>&1 || true
}

force_kill_if_running() {
  local pid="$1"

  if is_running "$pid"; then
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
}

join_pids() {
  local pids="$1"

  echo "$pids" | tr '\n' ' ' | sed 's/[[:space:]]*$//'
}

shell_quote() {
  printf "%q" "$1"
}

use_launchctl() {
  [[ "$(uname)" == "Darwin" ]] && command -v launchctl >/dev/null 2>&1
}

launchctl_domain() {
  echo "gui/$(id -u)"
}

launchctl_pid() {
  local label="$1"

  launchctl print "$(launchctl_domain)/$label" 2>/dev/null | awk '/pid = / { print $3; exit }'
}

stop_launchctl_job() {
  local label="$1"
  local domain=""

  if ! use_launchctl; then
    return 0
  fi

  domain="$(launchctl_domain)"
  if launchctl print "$domain/$label" >/dev/null 2>&1; then
    echo "正在停止 launchctl 作业 ${label}..."
    launchctl bootout "$domain/$label" >/dev/null 2>&1 || launchctl remove "$label" >/dev/null 2>&1 || true
  fi
}

start_launchctl_service() {
  local label="$1"
  local workdir="$2"
  local command="$3"
  local log_file="$4"
  local pid_file="$5"

  if ! use_launchctl; then
    return 1
  fi

  stop_launchctl_job "$label"
  launchctl submit -l "$label" -o "$log_file" -e "$log_file" -- /bin/zsh -lc "cd $(shell_quote "$workdir") && $command"
  launchctl_pid "$label" >"$pid_file"
}

kill_pid_file() {
  local pid_file="$1"
  local label="$2"
  local pid=""

  if [[ ! -f "$pid_file" ]]; then
    return 0
  fi

  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if is_running "$pid"; then
    echo "正在停止 $label 进程 $pid..."
    kill_tree "$pid"
    sleep 1
    force_kill_if_running "$pid"
  fi

  rm -f "$pid_file"
}

kill_port() {
  local port="$1"
  local label="$2"
  local pids=""

  for _ in {1..10}; do
    pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    if [[ -z "$pids" ]]; then
      return 0
    fi

    echo "正在停止 $label 在端口 $port 的监听进程：$pids"
    for pid in $pids; do
      kill_tree "$pid"
    done
    sleep 0.5
  done

  pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  for pid in $pids; do
    force_kill_if_running "$pid"
  done

  sleep 0.5
  pids="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "无法停止 $label 在端口 $port 的监听进程：$pids"
    return 1
  fi
}

stop_services() {
  stop_launchctl_job "beautiful-e2e-frontend"
  stop_launchctl_job "beautiful-e2e-backend"
  kill_pid_file "$FRONTEND_PID_FILE" "frontend"
  kill_pid_file "$BACKEND_PID_FILE" "backend"
  kill_port "$FRONTEND_PORT" "frontend"
  kill_port "$BACKEND_PORT" "backend"
  echo "后端和前端已停止。"
}

wait_for_port() {
  local port="$1"
  local label="$2"
  local log_file="$3"
  local stable_count=0

  for _ in {1..80}; do
    if lsof -ti tcp:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      stable_count=$((stable_count + 1))
      if [[ "$stable_count" -ge 4 ]]; then
        echo "$label 已在端口 $port 监听。"
        return 0
      fi
    else
      stable_count=0
    fi
    sleep 0.25
  done

  echo "$label 未在端口 $port 开始监听。请检查日志：$log_file"
  tail -n 40 "$log_file" 2>/dev/null || true
  return 1
}

start_backend() {
  require_command uv

  : >"$BACKEND_LOG"
  echo "正在启动后端：http://127.0.0.1:$BACKEND_PORT ..."
  if ! start_launchctl_service \
    "$BACKEND_LAUNCHCTL_LABEL" \
    "$ROOT_DIR/backend" \
    "exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port $(shell_quote "$BACKEND_PORT")" \
    "$BACKEND_LOG" \
    "$BACKEND_PID_FILE"; then
    nohup bash -c '
      cd "$1"
      exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$2"
    ' _ "$ROOT_DIR/backend" "$BACKEND_PORT" >"$BACKEND_LOG" 2>&1 < /dev/null &
    echo "$!" >"$BACKEND_PID_FILE"
  fi

  wait_for_port "$BACKEND_PORT" "后端" "$BACKEND_LOG" || return 1
  if use_launchctl; then
    launchctl_pid "$BACKEND_LAUNCHCTL_LABEL" >"$BACKEND_PID_FILE" 2>/dev/null || true
  fi
}

start_frontend() {
  require_command npm

  : >"$FRONTEND_LOG"
  echo "正在启动前端：http://127.0.0.1:$FRONTEND_PORT ..."
  if ! start_launchctl_service \
    "$FRONTEND_LAUNCHCTL_LABEL" \
    "$ROOT_DIR/frontend" \
    "export VITE_API_PROXY_TARGET=$(shell_quote "http://127.0.0.1:$BACKEND_PORT"); export VITE_API_BASE_URL=/api; exec npm run dev -- --port $(shell_quote "$FRONTEND_PORT") --strictPort" \
    "$FRONTEND_LOG" \
    "$FRONTEND_PID_FILE"; then
    nohup bash -c '
      cd "$1"
      export VITE_API_PROXY_TARGET="$2"
      export VITE_API_BASE_URL="/api"
      exec npm run dev -- --port "$3" --strictPort
    ' _ "$ROOT_DIR/frontend" "http://127.0.0.1:$BACKEND_PORT" "$FRONTEND_PORT" >"$FRONTEND_LOG" 2>&1 < /dev/null &
    echo "$!" >"$FRONTEND_PID_FILE"
  fi

  wait_for_port "$FRONTEND_PORT" "前端" "$FRONTEND_LOG" || return 1
  if use_launchctl; then
    launchctl_pid "$FRONTEND_LAUNCHCTL_LABEL" >"$FRONTEND_PID_FILE" 2>/dev/null || true
  fi
}

start_services() {
  stop_services
  if ! start_backend; then
    echo "后端启动失败。"
    stop_services
    return 1
  fi

  if ! start_frontend; then
    echo "前端启动失败。"
    stop_services
    return 1
  fi

  cat <<EOF

Beautiful E2E 正在运行：
  后端：http://127.0.0.1:$BACKEND_PORT
  前端：http://127.0.0.1:$FRONTEND_PORT

日志：
  后端：$BACKEND_LOG
  前端：$FRONTEND_LOG

停止：
  ./dev.sh stop
EOF
}

show_status() {
  show_service_status "后端" "$BACKEND_PID_FILE" "$BACKEND_PORT"
  show_service_status "前端" "$FRONTEND_PID_FILE" "$FRONTEND_PORT"
}

show_service_status() {
  local label="$1"
  local pid_file="$2"
  local port="$3"
  local pid=""
  local listeners=""
  local listener_text=""

  pid="$(cat "$pid_file" 2>/dev/null || true)"
  listeners="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null || true)"

  if is_running "$pid"; then
    echo "${label}：PID 文件进程 ${pid} 运行中。"
  elif [[ -n "$pid" ]]; then
    echo "${label}：PID 文件进程 ${pid} 已不存在。"
  else
    echo "${label}：没有 PID 文件记录。"
  fi

  if [[ -n "$listeners" ]]; then
    listener_text="$(join_pids "$listeners")"
    echo "${label}：端口 ${port} 监听进程 ${listener_text}，http://127.0.0.1:${port}"
  else
    echo "${label}：端口 ${port} 未监听。"
  fi
}

show_logs() {
  echo "后端日志：$BACKEND_LOG"
  echo "前端日志：$FRONTEND_LOG"
}

action="${1:-start}"

case "$action" in
  start | restart)
    start_services
    ;;
  stop)
    stop_services
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  -h | --help | help)
    print_usage
    ;;
  *)
    echo "未知动作：$action"
    print_usage
    exit 1
    ;;
esac
