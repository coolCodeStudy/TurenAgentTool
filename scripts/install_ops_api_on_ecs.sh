#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=${APP_ROOT:-${INVESTMENT_APP_ROOT:-/opt/investment-knowledge}}
INVESTMENT_DIR=${INVESTMENT_DIR:-$APP_ROOT/current}
OPS_HOME=${OPS_HOME:-/opt/investment-ops}
OPS_DEPLOY_ARTIFACTS_DIR=${OPS_DEPLOY_ARTIFACTS_DIR:-$OPS_HOME/deploy-artifacts}
OPS_API_PORT=${OPS_API_PORT:-8767}
OPS_API_VENV=${OPS_API_VENV:-$OPS_HOME/.venv}
OPS_DEPLOY_REPO_DIR=${OPS_DEPLOY_REPO_DIR:-/opt/investment-knowledge-repo}
OPS_DEPLOY_STATE_PATH=${OPS_DEPLOY_STATE_PATH:-/opt/investment-knowledge/shared/deploy-state.json}
OPS_DEPLOY_LOCK_PATH=${OPS_DEPLOY_LOCK_PATH:-/opt/investment-knowledge/shared/deploy.lock}
OPS_DEPLOY_RELEASE_ROOT=${OPS_DEPLOY_RELEASE_ROOT:-/opt/investment-knowledge/releases}
OPS_API_DEPLOY_TIMEOUT_SECONDS=${OPS_API_DEPLOY_TIMEOUT_SECONDS:-1800}
OPS_DEPLOY_ALLOWED_REFS=${OPS_DEPLOY_ALLOWED_REFS:-main}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-turenagenttool_prod}
COMPOSE_ENV_FILE=${COMPOSE_ENV_FILE:-$APP_ROOT/.env}
START_OPS=false
# The bootstrap workflow supplies this credential explicitly.  Preserve it
# before loading the business environment so a historical application value
# cannot silently rebind the independent control plane.
EXPLICIT_OPS_API_TOKEN=${OPS_API_TOKEN:-}

usage() {
  cat <<'EOF'
Install InvestmentKnowledge ECS Ops API as a systemd service.

Usage:
  bash scripts/install_ops_api_on_ecs.sh [--start]

Environment:
  INVESTMENT_APP_ROOT=/opt/investment-knowledge
  INVESTMENT_DIR=/opt/investment-knowledge/current
  OPS_HOME=/opt/investment-ops
  OPS_DEPLOY_ARTIFACTS_DIR=/opt/investment-ops/deploy-artifacts
  OPS_API_VENV=/opt/investment-ops/.venv
  OPS_API_HOST=...              Optional; defaults to docker0 bridge IP, then 127.0.0.1.
  OPS_API_PORT=8767
  OPS_API_TOKEN=...             Required distinct credential for the private Ops API.
  OPS_DEPLOY_REPO_DIR=...       Optional; defaults to /opt/investment-knowledge-repo.
  OPS_DEPLOY_STATE_PATH=/opt/investment-knowledge/shared/deploy-state.json
  OPS_DEPLOY_LOCK_PATH=/opt/investment-knowledge/shared/deploy.lock
  OPS_DEPLOY_RELEASE_ROOT=/opt/investment-knowledge/releases
  OPS_API_DEPLOY_TIMEOUT_SECONDS=1800
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPS_API_MODULES=(
  "ecs_ops_api.py"
  "deploy_contract.py"
  "deploy_preflight.py"
  "deploy_release.py"
  "deploy_retention.py"
  "deploy_state.py"
  "deploy_support.py"
)
for module in "${OPS_API_MODULES[@]}"; do
  if [ ! -f "$SCRIPT_DIR/$module" ]; then
    echo "Missing $SCRIPT_DIR/$module. Run this script from a full repo checkout." >&2
    exit 1
  fi
done

if [ -f "$COMPOSE_ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$COMPOSE_ENV_FILE"
  set +a
elif [ -f "$APP_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$APP_ROOT/.env"
  set +a
elif [ -f "$INVESTMENT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$INVESTMENT_DIR/.env"
  set +a
fi

if [ -n "$EXPLICIT_OPS_API_TOKEN" ]; then
  OPS_API_TOKEN=$EXPLICIT_OPS_API_TOKEN
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

OPS_API_TOKEN=${OPS_API_TOKEN:-}
if [ -z "$OPS_API_TOKEN" ]; then
  echo "OPS_API_TOKEN is required." >&2
  exit 1
fi

for trusted_dir in "$OPS_HOME" "$OPS_DEPLOY_ARTIFACTS_DIR"; do
  if [ -L "$trusted_dir" ]; then
    echo "Refusing symlinked Ops directory: $trusted_dir" >&2
    exit 1
  fi
done
mkdir -p "$OPS_HOME" "$OPS_DEPLOY_ARTIFACTS_DIR"
chown root:root "$OPS_HOME" "$OPS_DEPLOY_ARTIFACTS_DIR"
chmod 0700 "$OPS_HOME" "$OPS_DEPLOY_ARTIFACTS_DIR"
for module in "${OPS_API_MODULES[@]}"; do
  cp -a "$SCRIPT_DIR/$module" "$OPS_HOME/$module"
done
chmod +x "$OPS_HOME/ecs_ops_api.py"

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
INVESTMENT_APP_ROOT=$APP_ROOT
INVESTMENT_DIR=$INVESTMENT_DIR
OPS_HOME=$OPS_HOME
OPS_DEPLOY_ARTIFACTS_DIR=$OPS_DEPLOY_ARTIFACTS_DIR
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
WEEKLY_REVIEW_WEB_HOST_PORT=${WEEKLY_REVIEW_WEB_HOST_PORT:-8010}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-turenagenttool_prod}
COMPOSE_ENV_FILE=$COMPOSE_ENV_FILE
OPS_DEPLOY_REPO_DIR=$OPS_DEPLOY_REPO_DIR
OPS_DEPLOY_STATE_PATH=$OPS_DEPLOY_STATE_PATH
OPS_DEPLOY_LOCK_PATH=$OPS_DEPLOY_LOCK_PATH
OPS_DEPLOY_RELEASE_ROOT=$OPS_DEPLOY_RELEASE_ROOT
OPS_API_DEPLOY_TIMEOUT_SECONDS=$OPS_API_DEPLOY_TIMEOUT_SECONDS
OPS_DEPLOY_ALLOWED_REFS=$OPS_DEPLOY_ALLOWED_REFS
EOF
chmod 600 /etc/investment-knowledge/ops-api.env

cat > /etc/systemd/system/investment-ops-api.service <<EOF
[Unit]
Description=InvestmentKnowledge controlled ECS Ops API
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$OPS_HOME
EnvironmentFile=/etc/investment-knowledge/ops-api.env
ExecStart=$OPS_API_VENV/bin/python $OPS_HOME/ecs_ops_api.py
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
