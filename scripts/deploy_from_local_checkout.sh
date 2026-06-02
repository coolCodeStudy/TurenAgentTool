#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/investment-knowledge}
SOURCE_DIR=${SOURCE_DIR:-$(pwd)}
BUILD_IMAGE=${BUILD_IMAGE:-false}

if [ ! -f "$SOURCE_DIR/docker-compose.prod.yml" ]; then
  echo "SOURCE_DIR does not look like the InvestmentKnowledge repo: $SOURCE_DIR" >&2
  exit 1
fi

mkdir -p "$APP_DIR"

rm -rf \
  "$APP_DIR/db" \
  "$APP_DIR/docs" \
  "$APP_DIR/investment_knowledge_mcp" \
  "$APP_DIR/scripts"

cp -a "$SOURCE_DIR/db" "$APP_DIR/db"
cp -a "$SOURCE_DIR/docs" "$APP_DIR/docs"
cp -a "$SOURCE_DIR/investment_knowledge_mcp" "$APP_DIR/investment_knowledge_mcp"
cp -a "$SOURCE_DIR/scripts" "$APP_DIR/scripts"
cp -a "$SOURCE_DIR/Dockerfile" "$APP_DIR/Dockerfile"
cp -a "$SOURCE_DIR/requirements.txt" "$APP_DIR/requirements.txt"
cp -a "$SOURCE_DIR/docker-compose.prod.yml" "$APP_DIR/docker-compose.prod.yml"

chmod +x "$APP_DIR"/scripts/*.sh "$APP_DIR"/scripts/*.py 2>/dev/null || true

cd "$APP_DIR"

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
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --build postgres mcp account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
else
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --no-build postgres
  $DOCKER_COMPOSE -f docker-compose.prod.yml up -d --no-build --force-recreate mcp account-snapshot-scheduler ipo-reminder-scheduler dingtalk-stream-bot
fi

$DOCKER_COMPOSE -f docker-compose.prod.yml ps
