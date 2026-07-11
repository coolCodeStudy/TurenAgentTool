#!/usr/bin/env bash
set -euo pipefail

REPO_URL=${REPO_URL:-https://github.com/coolCodeStudy/TurenAgentTool.git}
BOOTSTRAP_REF=${BOOTSTRAP_REF:-main}
REPO_DIR=${OPS_DEPLOY_REPO_DIR:-/opt/investment-knowledge-repo}
APP_ROOT=${APP_ROOT:-${INVESTMENT_APP_ROOT:-/opt/investment-knowledge}}
OPS_HOME=${OPS_HOME:-/opt/investment-ops}
OPS_API_PORT=${OPS_API_PORT:-8767}
OPS_API_HOST=${OPS_API_HOST:-}
OPS_DEPLOY_STATE_PATH=${OPS_DEPLOY_STATE_PATH:-/opt/investment-knowledge/shared/deploy-state.json}
OPS_DEPLOY_LOCK_PATH=${OPS_DEPLOY_LOCK_PATH:-/opt/investment-knowledge/shared/deploy.lock}
OPS_DEPLOY_RELEASE_ROOT=${OPS_DEPLOY_RELEASE_ROOT:-/opt/investment-knowledge/releases}
OPS_API_DEPLOY_TIMEOUT_SECONDS=${OPS_API_DEPLOY_TIMEOUT_SECONDS:-1800}
OPS_DEPLOY_ALLOWED_REFS=${OPS_DEPLOY_ALLOWED_REFS:-main}

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root on the ECS host." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    apt-get install -y git ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    yum install -y git ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y git ca-certificates
  else
    echo "Unsupported Linux distribution: cannot install git automatically." >&2
    exit 1
  fi
fi

mkdir -p "$APP_ROOT" "$OPS_HOME" "$(dirname "$REPO_DIR")"

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" remote set-url origin "$REPO_URL"
  git -C "$REPO_DIR" fetch --prune origin
else
  rm -rf "$REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR"
fi

if git -C "$REPO_DIR" cat-file -e "$BOOTSTRAP_REF^{commit}" 2>/dev/null; then
  git -C "$REPO_DIR" checkout --detach "$BOOTSTRAP_REF"
else
  git -C "$REPO_DIR" checkout --detach "origin/$BOOTSTRAP_REF"
fi

resolved_commit="$(git -C "$REPO_DIR" rev-parse HEAD)"
echo "Bootstrapping Ops API from $resolved_commit"

INVESTMENT_APP_ROOT="$APP_ROOT" \
INVESTMENT_DIR="$APP_ROOT/current" \
OPS_HOME="$OPS_HOME" \
OPS_DEPLOY_REPO_DIR="$REPO_DIR" \
OPS_DEPLOY_STATE_PATH="$OPS_DEPLOY_STATE_PATH" \
OPS_DEPLOY_LOCK_PATH="$OPS_DEPLOY_LOCK_PATH" \
OPS_DEPLOY_RELEASE_ROOT="$OPS_DEPLOY_RELEASE_ROOT" \
OPS_API_DEPLOY_TIMEOUT_SECONDS="$OPS_API_DEPLOY_TIMEOUT_SECONDS" \
OPS_DEPLOY_ALLOWED_REFS="$OPS_DEPLOY_ALLOWED_REFS" \
OPS_API_PORT="$OPS_API_PORT" \
OPS_API_HOST="$OPS_API_HOST" \
bash "$REPO_DIR/scripts/install_ops_api_on_ecs.sh" --start

if [ -f /etc/investment-knowledge/ops-api.env ]; then
  set -a
  # shellcheck disable=SC1091
  . /etc/investment-knowledge/ops-api.env
  set +a
fi

health_url="http://${OPS_API_HOST:-127.0.0.1}:${OPS_API_PORT:-8767}/health"
echo "Checking $health_url"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "$health_url"; then
    break
  fi
  if [ "$attempt" = "10" ]; then
    echo "Ops API health check failed after $attempt attempts." >&2
    exit 1
  fi
  sleep 1
done
echo

if [ -n "${OPS_API_TOKEN:-}" ]; then
  status_url="http://${OPS_API_HOST:-127.0.0.1}:${OPS_API_PORT:-8767}/ops/status"
  echo "Checking $status_url"
  curl -fsS -H "Authorization: Bearer $OPS_API_TOKEN" "$status_url" >/tmp/investment-ops-status.json
  echo "Ops status response saved to /tmp/investment-ops-status.json"
fi
