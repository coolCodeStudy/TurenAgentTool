#!/usr/bin/env bash
set -euo pipefail

INVESTMENT_DIR=${INVESTMENT_DIR:-/opt/investment-knowledge}
WORKER_HOME=${WORKER_HOME:-/opt/investment-knowledge-codex}
WORKER_ENV=${WORKER_ENV:-/etc/investment-knowledge/codex-worker.env}
CODEX_WORKER_REPO_URL=${CODEX_WORKER_REPO_URL:-https://github.com/coolCodeStudy/TurenAgentTool.git}
CODEX_WORKER_BASE_BRANCH=${CODEX_WORKER_BASE_BRANCH:-main}
CODEX_WORKER_MODEL=${CODEX_WORKER_MODEL:-}
CODEX_WORKER_DANGER_FULL_ACCESS=${CODEX_WORKER_DANGER_FULL_ACCESS:-true}
CODEX_WORKER_AUTO_PUSH=${CODEX_WORKER_AUTO_PUSH:-true}
CODEX_WORKER_AUTO_DEPLOY=${CODEX_WORKER_AUTO_DEPLOY:-false}
CODEX_WORKER_LOCAL_DEPLOY=${CODEX_WORKER_LOCAL_DEPLOY:-true}
CODEX_WORKER_LOCAL_DEPLOY_BUILD=${CODEX_WORKER_LOCAL_DEPLOY_BUILD:-false}
CODEX_WORKER_DEPLOY_WORKFLOW=${CODEX_WORKER_DEPLOY_WORKFLOW:-deploy.yml}
CODEX_WORKER_DEPLOY_MODE=${CODEX_WORKER_DEPLOY_MODE:-auto}
CODEX_WORKER_POLL_SECONDS=${CODEX_WORKER_POLL_SECONDS:-30}
CODEX_WORKER_AUTH_MODE=${CODEX_WORKER_AUTH_MODE:-chatgpt}
CODEX_WORKER_RUN_DEVICE_LOGIN=${CODEX_WORKER_RUN_DEVICE_LOGIN:-false}
CODEX_WORKER_FORCE_LOGIN=${CODEX_WORKER_FORCE_LOGIN:-false}
CODEX_WORKER_STARTUP_ERROR_NOTIFY_COOLDOWN_SECONDS=${CODEX_WORKER_STARTUP_ERROR_NOTIFY_COOLDOWN_SECONDS:-3600}

usage() {
  cat <<'EOF'
Install the InvestmentKnowledge Codex task worker on ECS.

Usage:
  bash scripts/install_codex_worker_on_ecs.sh [--start]

Required for useful operation:
  CODEX_WORKER_GITHUB_TOKEN       GitHub PAT with repo write/workflow access, used to push branches and trigger deploy.

Codex authentication:
  Default auth mode is ChatGPT subscription login, not API-key billing.
  To sign in on a headless ECS host, run with CODEX_WORKER_RUN_DEVICE_LOGIN=true
  and complete the device-code flow in your browser.

Optional:
  CODEX_WORKER_AUTH_MODE=api       Use OPENAI_API_KEY for API-billed Codex CLI usage.
  OPENAI_API_KEY                   Required only when CODEX_WORKER_AUTH_MODE=api.

The worker reads pending coding_tasks, runs `codex exec` in a dedicated clone,
commits changes, pushes a codex/task-* branch, deploys locally on ECS by default,
and can optionally trigger GitHub Actions deploy.
EOF
}

START_WORKER=false
while [ "$#" -gt 0 ]; do
  case "$1" in
    --start)
      START_WORKER=true
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

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root on the ECS host." >&2
    exit 1
  fi
}

install_base_tools() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y git curl ca-certificates python3 python3-venv nodejs npm
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y git curl ca-certificates python3 python3-pip nodejs npm
  elif command -v yum >/dev/null 2>&1; then
    yum install -y git curl ca-certificates python3 python3-pip nodejs npm
  else
    echo "Unsupported Linux distribution: cannot install base tools automatically." >&2
    exit 1
  fi
}

load_investment_env() {
  if [ -f "$INVESTMENT_DIR/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$INVESTMENT_DIR/.env"
    set +a
  fi

  if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "Missing POSTGRES_PASSWORD. Keep it in $INVESTMENT_DIR/.env or export it before running." >&2
    exit 1
  fi
}

install_codex_cli() {
  if ! command -v codex >/dev/null 2>&1; then
    npm install -g @openai/codex
  fi

  if [ "$CODEX_WORKER_FORCE_LOGIN" = "true" ]; then
    codex logout >/dev/null 2>&1 || true
  fi

  if ! codex login status >/dev/null 2>&1; then
    case "$CODEX_WORKER_AUTH_MODE" in
      chatgpt)
        if [ "$CODEX_WORKER_RUN_DEVICE_LOGIN" = "true" ]; then
          codex login --device-auth
        else
          cat >&2 <<'EOF'
Codex CLI is not signed in.
Run the Codex Worker workflow with mode=login, or SSH to ECS and run:
  sudo CODEX_WORKER_RUN_DEVICE_LOGIN=true CODEX_WORKER_AUTH_MODE=chatgpt bash /opt/investment-knowledge/scripts/install_codex_worker_on_ecs.sh
EOF
          exit 1
        fi
        ;;
      api)
        if [ -z "${OPENAI_API_KEY:-}" ]; then
          echo "Missing OPENAI_API_KEY for CODEX_WORKER_AUTH_MODE=api." >&2
          exit 1
        fi
        printf "%s" "$OPENAI_API_KEY" | codex login --with-api-key
        ;;
      *)
        echo "Unknown CODEX_WORKER_AUTH_MODE: $CODEX_WORKER_AUTH_MODE" >&2
        exit 1
        ;;
    esac
  fi
}

install_worker_venv() {
  mkdir -p "$WORKER_HOME"
  if [ ! -d "$WORKER_HOME/venv" ]; then
    python3 -m venv "$WORKER_HOME/venv"
  fi
  "$WORKER_HOME/venv/bin/pip" install -U pip
  "$WORKER_HOME/venv/bin/pip" install "psycopg[binary]>=3.2.0"
  if [ -f "$INVESTMENT_DIR/requirements.txt" ]; then
    "$WORKER_HOME/venv/bin/pip" install -r "$INVESTMENT_DIR/requirements.txt"
  fi
}

write_worker_env() {
  mkdir -p "$(dirname "$WORKER_ENV")"
  chmod 700 "$(dirname "$WORKER_ENV")"
  CODEX_BIN_PATH="$(command -v codex || true)"
  CODEX_WORKER_DATABASE_URL_VALUE="$(
    POSTGRES_HOST=127.0.0.1 \
    POSTGRES_PORT="${POSTGRES_HOST_PORT:-55432}" \
    POSTGRES_USER="${POSTGRES_USER:-postgres}" \
    POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    POSTGRES_DB="${POSTGRES_DB:-investment_kg}" \
    python3 - <<'PY'
import os
from urllib.parse import quote

user = quote(os.environ["POSTGRES_USER"], safe="")
password = quote(os.environ["POSTGRES_PASSWORD"], safe="")
host = os.environ["POSTGRES_HOST"]
port = os.environ["POSTGRES_PORT"]
db = quote(os.environ["POSTGRES_DB"], safe="")
print(f"postgresql://{user}:{password}@{host}:{port}/{db}")
PY
  )"

  cat > "$WORKER_ENV" <<EOF
CODEX_WORKER_DATABASE_URL=$CODEX_WORKER_DATABASE_URL_VALUE
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=${POSTGRES_HOST_PORT:-55432}
POSTGRES_USER=${POSTGRES_USER:-postgres}
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=${POSTGRES_DB:-investment_kg}

DINGTALK_SEND_WEBHOOK=${DINGTALK_SEND_WEBHOOK:-}
DINGTALK_SEND_SECRET=${DINGTALK_SEND_SECRET:-}
CODEX_BIN=${CODEX_BIN_PATH:-codex}
CODEX_HOME=/root/.codex
CODEX_WORKER_AUTH_MODE=$CODEX_WORKER_AUTH_MODE
CODEX_WORKER_GITHUB_TOKEN=${CODEX_WORKER_GITHUB_TOKEN:-}
CODEX_WORKER_REPO_URL=$CODEX_WORKER_REPO_URL
CODEX_WORKER_BASE_BRANCH=$CODEX_WORKER_BASE_BRANCH
CODEX_WORKER_DIR=$WORKER_HOME/repo
CODEX_WORKER_MODEL=$CODEX_WORKER_MODEL
CODEX_WORKER_DANGER_FULL_ACCESS=$CODEX_WORKER_DANGER_FULL_ACCESS
CODEX_WORKER_AUTO_PUSH=$CODEX_WORKER_AUTO_PUSH
CODEX_WORKER_AUTO_DEPLOY=$CODEX_WORKER_AUTO_DEPLOY
CODEX_WORKER_LOCAL_DEPLOY=$CODEX_WORKER_LOCAL_DEPLOY
CODEX_WORKER_LOCAL_DEPLOY_BUILD=$CODEX_WORKER_LOCAL_DEPLOY_BUILD
CODEX_WORKER_DEPLOY_WORKFLOW=$CODEX_WORKER_DEPLOY_WORKFLOW
CODEX_WORKER_DEPLOY_MODE=$CODEX_WORKER_DEPLOY_MODE
CODEX_WORKER_POLL_SECONDS=$CODEX_WORKER_POLL_SECONDS
CODEX_WORKER_NOTIFY_STATE_DIR=/var/lib/investment-knowledge-codex
CODEX_WORKER_STARTUP_ERROR_NOTIFY_COOLDOWN_SECONDS=$CODEX_WORKER_STARTUP_ERROR_NOTIFY_COOLDOWN_SECONDS
CODEX_WORKER_GIT_USER_NAME="InvestmentKnowledge Codex Worker"
CODEX_WORKER_GIT_USER_EMAIL=codex-worker@users.noreply.github.com

RESEARCH_WORKER_NAME=${RESEARCH_WORKER_NAME:-research-agent-worker}
RESEARCH_WORK_DIR=$INVESTMENT_DIR
RESEARCH_ARTIFACT_ROOT=$INVESTMENT_DIR/drafts/research_jobs
RESEARCH_CODEX_MODEL=${RESEARCH_CODEX_MODEL:-$CODEX_WORKER_MODEL}
RESEARCH_WORKER_DANGER_FULL_ACCESS=${RESEARCH_WORKER_DANGER_FULL_ACCESS:-$CODEX_WORKER_DANGER_FULL_ACCESS}
RESEARCH_WORKER_POLL_SECONDS=${RESEARCH_WORKER_POLL_SECONDS:-30}
RESEARCH_CODEX_TIMEOUT_SECONDS=${RESEARCH_CODEX_TIMEOUT_SECONDS:-3600}
EOF
  chmod 600 "$WORKER_ENV"

  if [ -z "${CODEX_WORKER_GITHUB_TOKEN:-}" ]; then
    echo "WARNING: CODEX_WORKER_GITHUB_TOKEN is empty; worker can commit locally but push may fail." >&2
  fi
}

install_systemd_service() {
  cat > /etc/systemd/system/investment-codex-worker.service <<EOF
[Unit]
Description=InvestmentKnowledge Codex coding task worker
After=network-online.target docker.service turenagenttool_prod-postgres-1.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INVESTMENT_DIR
EnvironmentFile=$WORKER_ENV
Environment=VIRTUAL_ENV=$WORKER_HOME/venv
Environment=PATH=$WORKER_HOME/venv/bin:/usr/local/bin:/usr/bin:/bin:/root/.local/bin
UnsetEnvironment=DATABASE_URL
ExecStart=$WORKER_HOME/venv/bin/python $INVESTMENT_DIR/scripts/codex_task_worker.py --loop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  cat > /etc/systemd/system/investment-research-agent-worker.service <<EOF
[Unit]
Description=InvestmentKnowledge Codex research agent worker
After=network-online.target docker.service turenagenttool_prod-postgres-1.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INVESTMENT_DIR
EnvironmentFile=$WORKER_ENV
Environment=VIRTUAL_ENV=$WORKER_HOME/venv
Environment=PATH=$WORKER_HOME/venv/bin:/usr/local/bin:/usr/bin:/bin:/root/.local/bin
UnsetEnvironment=DATABASE_URL
ExecStart=$WORKER_HOME/venv/bin/python $INVESTMENT_DIR/scripts/research_agent_worker.py --loop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable investment-codex-worker.service
  systemctl enable investment-research-agent-worker.service
}

start_worker() {
  if [ "$START_WORKER" = "true" ]; then
    systemctl restart investment-codex-worker.service
    systemctl restart investment-research-agent-worker.service
  fi
}

print_next_steps() {
  cat <<EOF
Codex worker installed.

Status:
  systemctl status investment-codex-worker.service --no-pager
  systemctl status investment-research-agent-worker.service --no-pager
  journalctl -u investment-codex-worker.service -n 120 --no-pager
  journalctl -u investment-research-agent-worker.service -n 120 --no-pager

Run one task manually:
  $WORKER_HOME/venv/bin/python $INVESTMENT_DIR/scripts/codex_task_worker.py --once
  $WORKER_HOME/venv/bin/python $INVESTMENT_DIR/scripts/research_agent_worker.py --once

Worker env:
  $WORKER_ENV
EOF
}

require_root
install_base_tools
load_investment_env
install_codex_cli
install_worker_venv
write_worker_env
install_systemd_service
start_worker
print_next_steps
