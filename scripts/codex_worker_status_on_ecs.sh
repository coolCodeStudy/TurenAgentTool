#!/usr/bin/env bash
set -u

APP_DIR=${APP_DIR:-/opt/investment-knowledge}
WORKER_ENV=${WORKER_ENV:-/etc/investment-knowledge/codex-worker.env}
SERVICE=${SERVICE:-investment-codex-worker.service}

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
(
  set -a
  [ -f "$WORKER_ENV" ] && . "$WORKER_ENV"
  set +a
  "${CODEX_BIN:-codex}" login status
) || true

echo
echo "== worker database socket =="
(
  set -a
  [ -f "$WORKER_ENV" ] && . "$WORKER_ENV"
  set +a
  python3 -c 'import os, socket; host=os.environ.get("POSTGRES_HOST", "127.0.0.1"); port=int(os.environ.get("POSTGRES_PORT", "55432")); socket.create_connection((host, port), timeout=5).close(); print(f"database socket reachable: {host}:{port}")'
) || true

echo
echo "== systemd status =="
systemctl status "$SERVICE" --no-pager || true

echo
echo "== recent worker logs =="
journalctl -u "$SERVICE" -n 80 --no-pager || true
