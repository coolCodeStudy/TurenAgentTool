#!/usr/bin/env bash
set -euo pipefail

INVESTMENT_DIR=${INVESTMENT_DIR:-/opt/investment-knowledge}
OPS_API_PORT=${OPS_API_PORT:-8767}
OPS_API_VENV=${OPS_API_VENV:-$INVESTMENT_DIR/.ops-api-venv}
START_OPS=false

usage() {
  cat <<'EOF'
Install InvestmentKnowledge ECS Ops API as a systemd service.

Usage:
  bash scripts/install_ops_api_on_ecs.sh [--start]

Environment:
  INVESTMENT_DIR=/opt/investment-knowledge
  OPS_API_VENV=/opt/investment-knowledge/.ops-api-venv
  OPS_API_HOST=...              Optional; defaults to docker0 bridge IP, then 127.0.0.1.
  OPS_API_PORT=8767
  OPS_API_TOKEN=...             Optional; defaults to COMMAND_API_TOKEN from .env.
  OPS_DEPLOY_REPO_DIR=...       Optional; defaults to /opt/investment-knowledge-repo.
  OPS_API_DEPLOY_TIMEOUT_SECONDS=600
  OPS_DEPLOY_ALLOWED_REFS=main
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --start)
      START_OPS=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root on the ECS host." >&2
  exit 1
fi

if [ ! -f "$INVESTMENT_DIR/scripts/ecs_ops_api.py" ]; then
  echo "Missing $INVESTMENT_DIR/scripts/ecs_ops_api.py. Deploy latest code first." >&2
  exit 1
fi

if [ -f "$INVESTMENT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$INVESTMENT_DIR/.env"
  set +a
fi

if [ -z "${OPS_API_HOST:-}" ]; then
  OPS_API_HOST=$(
    ip -4 addr show docker0 2>/dev/null |
      awk '/inet / {print $2}' |
      cut -d/ -f1 |
      head -1
  )
fi
OPS_API_HOST=${OPS_API_HOST:-127.0.0.1}

OPS_API_TOKEN=${OPS_API_TOKEN:-${COMMAND_API_TOKEN:-}}
if [ -z "$OPS_API_TOKEN" ]; then
  echo "OPS_API_TOKEN or COMMAND_API_TOKEN is required." >&2
  exit 1
fi

if [ ! -x "$OPS_API_VENV/bin/python" ]; then
  python3 -m venv "$OPS_API_VENV"
fi

if ! "$OPS_API_VENV/bin/python" -c "import psycopg" >/dev/null 2>&1; then
  "$OPS_API_VENV/bin/python" -m pip install \
    --index-url "${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}" \
    "psycopg[binary]>=3.2.0"
fi

mkdir -p /etc/investment-knowledge
cat > /etc/investment-knowledge/ops-api.env <<EOF
INVESTMENT_DIR=$INVESTMENT_DIR
OPS_API_VENV=$OPS_API_VENV
OPS_API_PYTHON_BIN=$OPS_API_VENV/bin/python
OPS_API_HOST=$OPS_API_HOST
OPS_API_PORT=$OPS_API_PORT
OPS_API_TOKEN=$OPS_API_TOKEN
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=${POSTGRES_HOST_PORT:-55432}
POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}
POSTGRES_DB=${POSTGRES_DB:-investment_kg}
POSTGRES_HOST_PORT=${POSTGRES_HOST_PORT:-55432}
MCP_HOST_PORT=${MCP_HOST_PORT:-8000}
OPS_DEPLOY_REPO_DIR=${OPS_DEPLOY_REPO_DIR:-/opt/investment-knowledge-repo}
OPS_API_DEPLOY_TIMEOUT_SECONDS=${OPS_API_DEPLOY_TIMEOUT_SECONDS:-600}
OPS_DEPLOY_ALLOWED_REFS=${OPS_DEPLOY_ALLOWED_REFS:-main}
EOF
chmod 600 /etc/investment-knowledge/ops-api.env

chmod +x "$INVESTMENT_DIR/scripts/ecs_ops_api.py"

cat > /etc/systemd/system/investment-ops-api.service <<EOF
[Unit]
Description=InvestmentKnowledge controlled ECS Ops API
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INVESTMENT_DIR
EnvironmentFile=/etc/investment-knowledge/ops-api.env
ExecStart=$OPS_API_VENV/bin/python $INVESTMENT_DIR/scripts/ecs_ops_api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable investment-ops-api.service

if [ "$START_OPS" = "true" ]; then
  systemctl restart investment-ops-api.service
fi

cat <<EOF
InvestmentKnowledge Ops API installed.

Status:
  systemctl status investment-ops-api.service --no-pager
  journalctl -u investment-ops-api.service -n 80 --no-pager

Health:
  curl -s http://$OPS_API_HOST:$OPS_API_PORT/health
EOF
