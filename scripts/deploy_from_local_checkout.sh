#!/usr/bin/env bash
set -euo pipefail

APP_ROOT=${APP_ROOT:-${INVESTMENT_APP_ROOT:-/opt/investment-knowledge}}
APP_DIR=${APP_DIR:-$APP_ROOT/current}
RELEASES_DIR=${RELEASES_DIR:-$APP_ROOT/releases}
SHARED_DIR=${SHARED_DIR:-$APP_ROOT/shared}
COMPOSE_ENV_FILE=${COMPOSE_ENV_FILE:-$APP_ROOT/.env}
COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-turenagenttool_prod}
SOURCE_DIR=${SOURCE_DIR:-$(pwd)}
BUILD_IMAGE=${BUILD_IMAGE:-false}
PYTHON_BIN=${PYTHON_BIN:-python3}
DEPLOY_EVENT_ID="${DEPLOY_EVENT_ID:-}"
DEPLOY_EVENT_MANAGED_EXTERNALLY=false
DEPLOY_ERROR_HANDLED=false
RELEASE_ACTIVATED=false
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

mkdir -p "$APP_ROOT" "$RELEASES_DIR" "$SHARED_DIR"
if [ ! -e "$SHARED_DIR/drafts" ] && [ -e "$APP_ROOT/drafts" ]; then
  cp -a "$APP_ROOT/drafts" "$SHARED_DIR/drafts"
fi
mkdir -p "$SHARED_DIR/drafts"

commit_sha="$(git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)"
if [ -n "$commit_sha" ]; then
  release_name="$commit_sha"
else
  release_name="manual-$(date +%Y%m%d%H%M%S)"
fi

RELEASE_DIR=${RELEASE_DIR:-$RELEASES_DIR/$release_name}
STAGING_DIR="$RELEASES_DIR/.staging-$release_name-$$"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

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
ln -sfn "$SHARED_DIR/drafts" "$STAGING_DIR/drafts"
if [ -f "$COMPOSE_ENV_FILE" ]; then
  ln -sfn "$COMPOSE_ENV_FILE" "$STAGING_DIR/.env"
fi

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

resolve_path() {
  path="$1"
  if command -v realpath >/dev/null 2>&1; then
    realpath "$path" 2>/dev/null || true
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$path" <<'PY'
from pathlib import Path
import sys
try:
    print(Path(sys.argv[1]).resolve(strict=True))
except Exception:
    pass
PY
    return
  fi
  readlink -f "$path" 2>/dev/null || true
}

if [ -e "$RELEASE_DIR" ]; then
  current_target="$(resolve_path "$APP_DIR")"
  release_target="$(resolve_path "$RELEASE_DIR")"
  if [ "$current_target" != "$release_target" ]; then
    rm -rf "$RELEASE_DIR"
  fi
fi
if [ ! -e "$RELEASE_DIR" ]; then
  mv "$STAGING_DIR" "$RELEASE_DIR"
else
  rm -rf "$STAGING_DIR"
fi

PREVIOUS_RELEASE="$(resolve_path "$APP_DIR")"
replace_symlink() {
  target="$1"
  link="$2"
  tmp_link="$link.next"
  if [ -e "$link" ] && [ ! -L "$link" ]; then
    echo "refusing to replace non-symlink path: $link" >&2
    exit 1
  fi
  rm -f "$tmp_link"
  ln -s "$target" "$tmp_link"
  if mv -Tf "$tmp_link" "$link" 2>/dev/null; then
    return
  fi
  rm -f "$link"
  mv -f "$tmp_link" "$link"
}

activate_release() {
  replace_symlink "$RELEASE_DIR" "$APP_DIR"
  RELEASE_ACTIVATED=true
}

rollback_release() {
  if [ "$RELEASE_ACTIVATED" != "true" ]; then
    return
  fi
  if [ -n "$PREVIOUS_RELEASE" ] && [ -d "$PREVIOUS_RELEASE" ]; then
    replace_symlink "$PREVIOUS_RELEASE" "$APP_DIR"
  else
    rm -f "$APP_DIR" "$APP_DIR.rollback" "$APP_DIR.next"
  fi
}

record_deploy_start() {
  if [ -n "$DEPLOY_EVENT_ID" ]; then
    return
  fi
  deploy_event_script="$APP_DIR/scripts/record_deploy_event.py"
  if [ ! -f "$deploy_event_script" ] && [ -f "$SOURCE_DIR/scripts/record_deploy_event.py" ]; then
    deploy_event_script="$SOURCE_DIR/scripts/record_deploy_event.py"
  fi
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1 || [ ! -f "$deploy_event_script" ]; then
    return
  fi
  branch_name="$(git -C "$SOURCE_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
  deploy_mode="quick"
  if [ "$BUILD_IMAGE" = "true" ]; then
    deploy_mode="full"
  fi
  DEPLOY_EVENT_ID="$("$PYTHON_BIN" "$deploy_event_script" start \
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
  deploy_event_script="$APP_DIR/scripts/record_deploy_event.py"
  if [ ! -f "$deploy_event_script" ] && [ -f "$SOURCE_DIR/scripts/record_deploy_event.py" ]; then
    deploy_event_script="$SOURCE_DIR/scripts/record_deploy_event.py"
  fi
  if [ ! -f "$deploy_event_script" ]; then
    return
  fi
  "$PYTHON_BIN" "$deploy_event_script" finish \
    --id "$DEPLOY_EVENT_ID" \
    --status "$status" \
    --summary "$summary" >/dev/null 2>&1 || true
}

on_deploy_error() {
  if [ "$DEPLOY_ERROR_HANDLED" = "true" ]; then
    return
  fi
  DEPLOY_ERROR_HANDLED=true
  rollback_release
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
  record_deploy_finish failed "Docker Compose plugin is not available"
  exit 1
fi

compose() {
  if [ -f "$COMPOSE_ENV_FILE" ]; then
    env -u POSTGRES_HOST -u POSTGRES_PORT \
      $DOCKER_COMPOSE --project-name "$COMPOSE_PROJECT_NAME" --env-file "$COMPOSE_ENV_FILE" -f docker-compose.prod.yml "$@"
  else
    env -u POSTGRES_HOST -u POSTGRES_PORT \
      $DOCKER_COMPOSE --project-name "$COMPOSE_PROJECT_NAME" -f docker-compose.prod.yml "$@"
  fi
}

run_compose_step() {
  if ! compose "$@"; then
    on_deploy_error
    exit 1
  fi
}

activate_release
chmod +x "$APP_DIR"/scripts/*.sh "$APP_DIR"/scripts/*.py 2>/dev/null || true
cd "$APP_DIR"

if [ "$BUILD_IMAGE" = "true" ]; then
  run_compose_step up -d --build postgres mcp command-api weekly-review-web account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
else
  run_compose_step up -d --no-build postgres
  run_compose_step up -d --no-build --force-recreate mcp command-api weekly-review-web account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
fi

run_compose_step ps
record_deploy_finish succeeded "deploy_from_local_checkout completed"
trap - ERR
rm -rf "$STAGING_DIR"
