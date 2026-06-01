#!/usr/bin/env bash
set -u

APP_DIR=${APP_DIR:-/opt/investment-knowledge}
WORKER_ENV=${WORKER_ENV:-/etc/investment-knowledge/codex-worker.env}
SERVICE=${SERVICE:-investment-codex-worker.service}

env_value() {
  local key=$1
  if [ ! -f "$WORKER_ENV" ]; then
    return 1
  fi
  awk -F= -v key="$key" '
    $1 == key {
      value = substr($0, length(key) + 2)
      if (value ~ /^".*"$/ || value ~ /^'\''.*'\''$/) {
        value = substr(value, 2, length(value) - 2)
      }
      print value
      exit
    }
  ' "$WORKER_ENV"
}

echo "== docker compose =="
cd "$APP_DIR" 2>/dev/null || true
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && [ -f docker-compose.prod.yml ]; then
  docker compose -f docker-compose.prod.yml ps || true
else
  echo "docker compose unavailable or docker-compose.prod.yml missing"
fi

echo
echo "== worker env =="
if [ -f "$WORKER_ENV" ]; then
  awk -F= '
    /^(CODEX_WORKER_DATABASE_URL|POSTGRES_HOST|POSTGRES_PORT|POSTGRES_DB|CODEX_BIN|CODEX_HOME|CODEX_WORKER_AUTH_MODE)=/ {
      if ($1 == "CODEX_WORKER_DATABASE_URL") {
        print $1"=<redacted>"
      } else {
        print
      }
    }
  ' "$WORKER_ENV"
else
  echo "worker env file missing: $WORKER_ENV"
fi

echo
echo "== codex login status =="
CODEX_BIN_VALUE=$(env_value CODEX_BIN || true)
CODEX_HOME_VALUE=$(env_value CODEX_HOME || true)
CODEX_BIN_VALUE=${CODEX_BIN_VALUE:-codex}
CODEX_HOME_VALUE=${CODEX_HOME_VALUE:-/root/.codex}
CODEX_HOME="$CODEX_HOME_VALUE" "$CODEX_BIN_VALUE" login status || true

echo
echo "== worker database socket =="
POSTGRES_HOST_VALUE=$(env_value POSTGRES_HOST || true)
POSTGRES_PORT_VALUE=$(env_value POSTGRES_PORT || true)
POSTGRES_HOST_VALUE=${POSTGRES_HOST_VALUE:-127.0.0.1}
POSTGRES_PORT_VALUE=${POSTGRES_PORT_VALUE:-55432}
POSTGRES_HOST="$POSTGRES_HOST_VALUE" POSTGRES_PORT="$POSTGRES_PORT_VALUE" python3 -c 'import os, socket; host=os.environ["POSTGRES_HOST"]; port=int(os.environ["POSTGRES_PORT"]); socket.create_connection((host, port), timeout=5).close(); print(f"database socket reachable: {host}:{port}")' || true

echo
echo "== systemd status =="
systemctl status "$SERVICE" --no-pager || true

echo
echo "== recent worker logs =="
journalctl -u "$SERVICE" -n 80 --no-pager || true
