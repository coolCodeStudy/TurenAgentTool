#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/investment-knowledge}
SOURCE_DIR=${SOURCE_DIR:-$(pwd)}
BUILD_IMAGE=${BUILD_IMAGE:-false}
PYTHON_BIN=${PYTHON_BIN:-python3}
DEPLOY_EVENT_ID="${DEPLOY_EVENT_ID:-}"
DEPLOY_EVENT_MANAGED_EXTERNALLY=false
if [ -n "$DEPLOY_EVENT_ID" ]; then
  DEPLOY_EVENT_MANAGED_EXTERNALLY=true
fi

if [ ! -f "$SOURCE_DIR/docker-compose.prod.yml" ]; then
  echo "SOURCE_DIR does not look like the InvestmentKnowledge repo: $SOURCE_DIR" >&2
  exit 1
fi

mkdir -p "$APP_DIR"

rm -rf \
  "$APP_DIR/db" \
  "$APP_DIR/docs" \
  "$APP_DIR/investment_knowledge_mcp" \
  "$APP_DIR/prompts" \
  "$APP_DIR/scripts"

cp -a "$SOURCE_DIR/db" "$APP_DIR/db"
cp -a "$SOURCE_DIR/docs" "$APP_DIR/docs"
cp -a "$SOURCE_DIR/investment_knowledge_mcp" "$APP_DIR/investment_knowledge_mcp"
if [ -d "$SOURCE_DIR/prompts" ]; then
  cp -a "$SOURCE_DIR/prompts" "$APP_DIR/prompts"
fi
cp -a "$SOURCE_DIR/scripts" "$APP_DIR/scripts"
cp -a "$SOURCE_DIR/Dockerfile" "$APP_DIR/Dockerfile"
cp -a "$SOURCE_DIR/requirements.txt" "$APP_DIR/requirements.txt"
cp -a "$SOURCE_DIR/docker-compose.prod.yml" "$APP_DIR/docker-compose.prod.yml"

chmod +x "$APP_DIR"/scripts/*.sh "$APP_DIR"/scripts/*.py 2>/dev/null || true

cd "$APP_DIR"

record_deploy_start() {
  if [ -n "$DEPLOY_EVENT_ID" ]; then
    return
  fi
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 || [ ! -f "$APP_DIR/scripts/record_deploy_event.py" ]; then
    return
  fi
  commit_sha="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)"
  branch_name="$(git -C "$SOURCE_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  deploy_mode="quick"
  if [ "$BUILD_IMAGE" = "true" ]; then
    deploy_mode="full"
  fi
  DEPLOY_EVENT_ID="$("$PYTHON_BIN" "$APP_DIR/scripts/record_deploy_event.py" start \
    --source local_codex \
    --deploy-mode "$deploy_mode" \
    --commit-sha "$commit_sha" \
    --branch-name "$branch_name" \
    --summary "deploy_from_local_checkout started" 2>/dev/null || true)"
}

record_deploy_finish() {
  status="$1"
  summary="$2"
  if [ "$DEPLOY_EVENT_MANAGED_EXTERNALLY" = "true" ]; then
    return
  fi
  if [ -z "$DEPLOY_EVENT_ID" ] || ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    return
  fi
  "$PYTHON_BIN" "$APP_DIR/scripts/record_deploy_event.py" finish \
    --id "$DEPLOY_EVENT_ID" \
    --status "$status" \
    --summary "$summary" >/dev/null 2>&1 || true
}

on_deploy_error() {
  record_deploy_finish failed "deploy_from_local_checkout failed"
}

trap on_deploy_error ERR
record_deploy_start

if docker ps >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE="docker compose"
elif sudo docker compose version >/dev/null 2>&1; then
  DOCKER_COMPOSE="sudo docker compose"
else
  echo "Docker Compose plugin is not available." >&2
  exit 1
fi

if systemctl cat hermes-gateway.service >/dev/null 2>&1; then
  systemctl stop hermes-gateway.service || true
fi

if [ "$BUILD_IMAGE" = "true" ]; then
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --build postgres mcp weekly-review-web account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
else
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --no-build postgres
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --no-build --force-recreate mcp weekly-review-web account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
fi

$DOCKER_COMPOSE -f docker-compose.prod.yml ps
record_deploy_finish succeeded "deploy_from_local_checkout completed"
trap - ERR
