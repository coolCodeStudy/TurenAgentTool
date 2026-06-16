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

for required_path in \
  "$SOURCE_DIR/db/schema.sql" \
  "$SOURCE_DIR/investment_knowledge_mcp" \
  "$SOURCE_DIR/scripts/init_db.py" \
  "$SOURCE_DIR/scripts/ecs_ops_api.py" \
  "$SOURCE_DIR/Dockerfile" \
  "$SOURCE_DIR/requirements.txt"
do
  if [ ! -e "$required_path" ]; then
    echo "SOURCE_DIR is incomplete, missing: $required_path" >&2
    exit 1
  fi
done

mkdir -p "$APP_DIR"

STAGING_DIR="$APP_DIR/.deploy-staging-$$"
BACKUP_DIR="$APP_DIR/.deploy-backup-$$"
rm -rf "$STAGING_DIR" "$BACKUP_DIR"
mkdir -p "$STAGING_DIR" "$BACKUP_DIR"

cp -a "$SOURCE_DIR/db" "$STAGING_DIR/db"
cp -a "$SOURCE_DIR/docs" "$STAGING_DIR/docs"
cp -a "$SOURCE_DIR/investment_knowledge_mcp" "$STAGING_DIR/investment_knowledge_mcp"
if [ -d "$SOURCE_DIR/prompts" ]; then
  cp -a "$SOURCE_DIR/prompts" "$STAGING_DIR/prompts"
fi
cp -a "$SOURCE_DIR/scripts" "$STAGING_DIR/scripts"
cp -a "$SOURCE_DIR/Dockerfile" "$STAGING_DIR/Dockerfile"
cp -a "$SOURCE_DIR/requirements.txt" "$STAGING_DIR/requirements.txt"
cp -a "$SOURCE_DIR/docker-compose.prod.yml" "$STAGING_DIR/docker-compose.prod.yml"

for staged_required_path in \
  "$STAGING_DIR/db/schema.sql" \
  "$STAGING_DIR/scripts/init_db.py" \
  "$STAGING_DIR/scripts/ecs_ops_api.py" \
  "$STAGING_DIR/docker-compose.prod.yml"
do
  if [ ! -e "$staged_required_path" ]; then
    echo "staged release is incomplete, missing: $staged_required_path" >&2
    exit 1
  fi
done

ROLLED_BACK=false
rollback_release_files() {
  if [ "$ROLLED_BACK" = "true" ]; then
    return
  fi
  ROLLED_BACK=true
  for path in db docs investment_knowledge_mcp prompts scripts Dockerfile requirements.txt docker-compose.prod.yml; do
    rm -rf "$APP_DIR/$path"
    if [ -e "$BACKUP_DIR/$path" ]; then
      mv "$BACKUP_DIR/$path" "$APP_DIR/$path"
    fi
  done
}

install_staged_release() {
  for path in db docs investment_knowledge_mcp prompts scripts Dockerfile requirements.txt docker-compose.prod.yml; do
    if [ -e "$APP_DIR/$path" ]; then
      mv "$APP_DIR/$path" "$BACKUP_DIR/$path"
    fi
    if [ -e "$STAGING_DIR/$path" ]; then
      mv "$STAGING_DIR/$path" "$APP_DIR/$path"
    fi
  done
}

trap rollback_release_files ERR
install_staged_release

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
  rollback_release_files
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

if [ "$BUILD_IMAGE" = "true" ]; then
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --build postgres mcp weekly-review-web account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
else
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --no-build postgres
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --no-build --force-recreate mcp weekly-review-web account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
fi

$DOCKER_COMPOSE -f docker-compose.prod.yml ps
record_deploy_finish succeeded "deploy_from_local_checkout completed"
trap - ERR
rm -rf "$STAGING_DIR" "$BACKUP_DIR"
