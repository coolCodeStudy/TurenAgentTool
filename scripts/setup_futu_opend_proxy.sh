#!/usr/bin/env bash
set -euo pipefail

OPEND_HOST="${OPEND_HOST:-127.0.0.1}"
OPEND_PORT="${OPEND_PORT:-11111}"
PROXY_PORT="${PROXY_PORT:-11112}"
LOG_DIR="${LOG_DIR:-/opt/futu-opend}"
RESTART=false

if [ "${1:-}" = "--restart" ]; then
  RESTART=true
elif [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  cat <<USAGE
Usage: scripts/setup_futu_opend_proxy.sh [--restart]

Start a local-only proxy for Futu OpenD on ECS:
  Docker container -> docker0:${PROXY_PORT} -> ${OPEND_HOST}:${OPEND_PORT}

Environment overrides:
  OPEND_HOST=${OPEND_HOST}
  OPEND_PORT=${OPEND_PORT}
  PROXY_PORT=${PROXY_PORT}
  LOG_DIR=${LOG_DIR}
USAGE
  exit 0
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

install_socat() {
  if command -v socat >/dev/null 2>&1; then
    return
  fi

  echo "Installing socat..."
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y socat
  elif command -v yum >/dev/null 2>&1; then
    $SUDO yum install -y socat
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y socat
  else
    echo "Cannot install socat automatically: unsupported Linux distribution." >&2
    exit 1
  fi
}

detect_docker_host_ip() {
  local ip
  ip="$(ip -4 addr show docker0 | awk '/inet / {print $2}' | cut -d/ -f1)"
  if [ -z "$ip" ]; then
    echo "Cannot detect docker0 IPv4 address. Is Docker running?" >&2
    exit 1
  fi
  printf '%s\n' "$ip"
}

check_opend_local() {
  if ! timeout 3 bash -c "cat < /dev/null > /dev/tcp/${OPEND_HOST}/${OPEND_PORT}" 2>/dev/null; then
    echo "Cannot connect to Futu OpenD at ${OPEND_HOST}:${OPEND_PORT}." >&2
    echo "Start OpenD with -api_ip=${OPEND_HOST} -api_port=${OPEND_PORT}, then rerun this script." >&2
    exit 1
  fi
}

refuse_public_opend() {
  if ss -lntp 2>/dev/null | grep -qE "0\.0\.0\.0:${OPEND_PORT}[[:space:]]"; then
    echo "OpenD appears to be listening on 0.0.0.0:${OPEND_PORT}." >&2
    echo "For Futu trade safety, restart OpenD with -api_ip=${OPEND_HOST}." >&2
    echo "Refusing to start the proxy until OpenD is local-only." >&2
    exit 1
  fi
}

stop_existing_proxy() {
  local docker_host_ip="$1"
  if ! ss -lntp 2>/dev/null | grep -qE "${docker_host_ip}:${PROXY_PORT}[[:space:]]"; then
    return
  fi

  if [ "$RESTART" != true ]; then
    echo "Proxy port ${docker_host_ip}:${PROXY_PORT} is already in use."
    echo "Use --restart if you want this script to restart the socat proxy."
    exit 0
  fi

  echo "Stopping existing socat proxy on ${docker_host_ip}:${PROXY_PORT}..."
  $SUDO pkill -f "socat.*TCP-LISTEN:${PROXY_PORT}.*TCP:${OPEND_HOST}:${OPEND_PORT}" || true
  sleep 1
}

start_proxy() {
  local docker_host_ip="$1"
  $SUDO mkdir -p "$LOG_DIR"
  $SUDO nohup socat \
    "TCP-LISTEN:${PROXY_PORT},bind=${docker_host_ip},fork,reuseaddr" \
    "TCP:${OPEND_HOST}:${OPEND_PORT}" \
    > "${LOG_DIR}/socat.log" 2>&1 &
  sleep 1
}

check_proxy() {
  local docker_host_ip="$1"
  if ! timeout 3 bash -c "cat < /dev/null > /dev/tcp/${docker_host_ip}/${PROXY_PORT}" 2>/dev/null; then
    echo "Proxy did not become reachable at ${docker_host_ip}:${PROXY_PORT}." >&2
    echo "Check ${LOG_DIR}/socat.log for details." >&2
    exit 1
  fi
}

install_socat
DOCKER_HOST_IP="$(detect_docker_host_ip)"
refuse_public_opend
check_opend_local
stop_existing_proxy "$DOCKER_HOST_IP"
start_proxy "$DOCKER_HOST_IP"
check_proxy "$DOCKER_HOST_IP"

echo "Futu OpenD proxy is ready:"
echo "  ${DOCKER_HOST_IP}:${PROXY_PORT} -> ${OPEND_HOST}:${OPEND_PORT}"
echo "Container config should use:"
echo "  FUTU_OPEND_HOST=host.docker.internal"
echo "  FUTU_OPEND_PORT=${PROXY_PORT}"
