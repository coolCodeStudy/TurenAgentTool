#!/usr/bin/env bash
set -euo pipefail

INVESTMENT_DIR=${INVESTMENT_DIR:-/opt/investment-knowledge/current}
WORKER_HOME=${WORKER_HOME:-/opt/investment-knowledge-codex}
WORKER_ENV=${WORKER_ENV:-/etc/investment-knowledge/codex-worker.env}
START_WORKER=false

usage() {
  cat <<'EOF'
Usage:
  bash scripts/install_research_agent_worker_on_ecs.sh [--start]

Installs the InvestmentKnowledge research agent worker service. It reuses the
existing Codex worker venv/env/login and does not perform Codex login.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --start)
      START_WORKER=true
      shift
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
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root, e.g. sudo bash scripts/install_research_agent_worker_on_ecs.sh --start" >&2
  exit 1
fi

if [ ! -f "$WORKER_ENV" ]; then
  echo "Codex worker env not found: $WORKER_ENV" >&2
  echo "Install the Codex worker first: bash scripts/install_codex_worker_on_ecs.sh --start" >&2
  exit 1
fi

if [ ! -x "$WORKER_HOME/venv/bin/python" ]; then
  echo "Codex worker Python venv not found: $WORKER_HOME/venv/bin/python" >&2
  exit 1
fi

if [ ! -f "$INVESTMENT_DIR/scripts/research_agent_worker.py" ]; then
  echo "Research worker script not found: $INVESTMENT_DIR/scripts/research_agent_worker.py" >&2
  exit 1
fi

mkdir -p "$INVESTMENT_DIR/drafts/research_jobs"

if [ -f "$INVESTMENT_DIR/requirements.txt" ]; then
  "$WORKER_HOME/venv/bin/pip" install -r "$INVESTMENT_DIR/requirements.txt"
fi

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
Environment=RESEARCH_WORK_DIR=$INVESTMENT_DIR
Environment=RESEARCH_ARTIFACT_ROOT=$INVESTMENT_DIR/drafts/research_jobs
Environment=RESEARCH_WORKER_NAME=research-agent-worker
Environment=RESEARCH_WORKER_POLL_SECONDS=30
Environment=RESEARCH_WORKER_CONCURRENCY=${RESEARCH_WORKER_CONCURRENCY:-1}
Environment=RESEARCH_CODEX_TIMEOUT_SECONDS=3600
UnsetEnvironment=DATABASE_URL
ExecStart=$WORKER_HOME/venv/bin/python $INVESTMENT_DIR/scripts/research_agent_worker.py --loop
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable investment-research-agent-worker.service

if [ "$START_WORKER" = "true" ]; then
  systemctl restart investment-research-agent-worker.service
fi

systemctl status investment-research-agent-worker.service --no-pager || true
