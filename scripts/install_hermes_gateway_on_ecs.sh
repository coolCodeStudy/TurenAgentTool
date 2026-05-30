#!/usr/bin/env bash
set -euo pipefail

HERMES_DIR=${HERMES_DIR:-/opt/hermes-agent}
HERMES_HOME=${HERMES_HOME:-/root/.hermes}
INVESTMENT_DIR=${INVESTMENT_DIR:-/opt/investment-knowledge}
HERMES_REPO_URL=${HERMES_REPO_URL:-https://github.com/NousResearch/hermes-agent.git}
INVESTMENT_MCP_URL=${INVESTMENT_MCP_URL:-http://127.0.0.1:8000/mcp}
DINGTALK_ALLOWED_USERS=${DINGTALK_ALLOWED_USERS:-0140522255091257971}
OPENAI_MODEL=${OPENAI_MODEL:-gpt-5.2}
OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1}
SWITCH_DINGTALK=false

usage() {
  cat <<'EOF'
Install Hermes Gateway on ECS and configure it to call InvestmentKnowledge MCP.

Usage:
  bash scripts/install_hermes_gateway_on_ecs.sh [--switch-dingtalk]

Options:
  --switch-dingtalk  Stop InvestmentKnowledge dingtalk-stream-bot after Hermes is installed.

Environment overrides:
  HERMES_DIR=/opt/hermes-agent
  HERMES_HOME=/root/.hermes
  INVESTMENT_DIR=/opt/investment-knowledge
  INVESTMENT_MCP_URL=http://127.0.0.1:8000/mcp
  DINGTALK_ALLOWED_USERS=0140522255091257971
  OPENAI_MODEL=gpt-5.2
  OPENAI_BASE_URL=https://api.openai.com/v1
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --switch-dingtalk)
      SWITCH_DINGTALK=true
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
    apt-get update
    apt-get install -y git curl ca-certificates python3 python3-venv
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y git curl ca-certificates python3
  elif command -v yum >/dev/null 2>&1; then
    yum install -y git curl ca-certificates python3
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

  DINGTALK_CLIENT_ID=${DINGTALK_CLIENT_ID:-${DINGTALK_STREAM_CLIENT_ID:-}}
  DINGTALK_CLIENT_SECRET=${DINGTALK_CLIENT_SECRET:-${DINGTALK_STREAM_CLIENT_SECRET:-}}
  OPENAI_API_KEY=${OPENAI_API_KEY:-}

  if [ -z "$DINGTALK_CLIENT_ID" ] || [ -z "$DINGTALK_CLIENT_SECRET" ]; then
    echo "Missing DingTalk credentials. Set DINGTALK_CLIENT_ID/DINGTALK_CLIENT_SECRET or keep DINGTALK_STREAM_* in $INVESTMENT_DIR/.env." >&2
    exit 1
  fi
  if [ -z "$OPENAI_API_KEY" ]; then
    echo "Missing OPENAI_API_KEY. Keep it in $INVESTMENT_DIR/.env or export it before running this script." >&2
    exit 1
  fi
}

install_uv() {
  if command -v uv >/dev/null 2>&1; then
    return
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="/root/.local/bin:$PATH"
}

install_hermes() {
  mkdir -p "$(dirname "$HERMES_DIR")"
  if [ ! -d "$HERMES_DIR/.git" ]; then
    git clone "$HERMES_REPO_URL" "$HERMES_DIR"
  fi

  cd "$HERMES_DIR"
  git fetch origin
  git pull --ff-only

  if command -v uv >/dev/null 2>&1; then
    uv venv venv
    uv pip install -e ".[cli,pty,mcp,dingtalk]"
  else
    python3 -m venv venv
    "$HERMES_DIR/venv/bin/pip" install -U pip
    "$HERMES_DIR/venv/bin/pip" install -e ".[cli,pty,mcp,dingtalk]"
  fi
}

write_hermes_config() {
  mkdir -p "$HERMES_HOME"
  chmod 700 "$HERMES_HOME"

  cat > "$HERMES_HOME/.env" <<EOF
OPENAI_API_KEY=$OPENAI_API_KEY
DINGTALK_CLIENT_ID=$DINGTALK_CLIENT_ID
DINGTALK_CLIENT_SECRET=$DINGTALK_CLIENT_SECRET
DINGTALK_ALLOWED_USERS=$DINGTALK_ALLOWED_USERS
DINGTALK_REQUIRE_MENTION=true
HERMES_HOME=$HERMES_HOME
EOF
  chmod 600 "$HERMES_HOME/.env"

  cat > "$HERMES_HOME/config.yaml" <<EOF
model:
  default: $OPENAI_MODEL
  provider: custom
  base_url: $OPENAI_BASE_URL

group_sessions_per_user: true

mcp_servers:
  investment_knowledge:
    url: $INVESTMENT_MCP_URL
    enabled: true
    timeout: 180
    connect_timeout: 30
    tools:
      include:
        - run_investment_command
      resources: false
      prompts: false
EOF
  chmod 600 "$HERMES_HOME/config.yaml"
}

install_systemd_service() {
  cat > /etc/systemd/system/hermes-gateway.service <<EOF
[Unit]
Description=Hermes Gateway for InvestmentKnowledge
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INVESTMENT_DIR
EnvironmentFile=$HERMES_HOME/.env
Environment=HERMES_HOME=$HERMES_HOME
ExecStart=$HERMES_DIR/venv/bin/hermes gateway
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable --now hermes-gateway.service
}

switch_dingtalk_owner() {
  if [ "$SWITCH_DINGTALK" != "true" ]; then
    return
  fi
  if [ -f "$INVESTMENT_DIR/docker-compose.prod.yml" ]; then
    cd "$INVESTMENT_DIR"
    docker compose -f docker-compose.prod.yml stop dingtalk-stream-bot || true
  fi
}

print_next_steps() {
  cat <<EOF
Hermes Gateway installed.

Status:
  systemctl status hermes-gateway.service --no-pager
  journalctl -u hermes-gateway.service -n 100 --no-pager

InvestmentKnowledge MCP should be available at:
  $INVESTMENT_MCP_URL

If you have not switched DingTalk yet, stop the old Stream bot before testing Hermes:
  cd $INVESTMENT_DIR
  docker compose -f docker-compose.prod.yml stop dingtalk-stream-bot

Rollback:
  systemctl disable --now hermes-gateway.service
  cd $INVESTMENT_DIR
  docker compose -f docker-compose.prod.yml up -d dingtalk-stream-bot
EOF
}

require_root
install_base_tools
load_investment_env
install_uv
install_hermes
write_hermes_config
install_systemd_service
switch_dingtalk_owner
print_next_steps
