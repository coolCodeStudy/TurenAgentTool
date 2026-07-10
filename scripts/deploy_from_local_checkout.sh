#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-python3}"
app_root="${APP_ROOT:-${INVESTMENT_APP_ROOT:-/opt/investment-knowledge}}"
source_dir="${SOURCE_DIR:-$(pwd)}"
deploy_mode="${DEPLOY_MODE:-}"

if [[ -z "$deploy_mode" ]]; then
  if [[ "${BUILD_IMAGE:-false}" == "true" ]]; then
    deploy_mode="full_image"
  else
    deploy_mode="targeted_quick"
  fi
fi

case "$deploy_mode" in
  quick)
    deploy_mode="targeted_quick"
    ;;
  full)
    deploy_mode="full_image"
    ;;
esac

args=(
  "$python_bin"
  "$script_dir/deploy_release.py"
  --ref "${DEPLOY_REF:-main}"
  --mode "$deploy_mode"
  --repo "$source_dir"
  --app-root "$app_root"
  --project-name "${COMPOSE_PROJECT_NAME:-turenagenttool_prod}"
)

if [[ -n "${COMPOSE_ENV_FILE:-}" ]]; then
  args+=(--env-file "$COMPOSE_ENV_FILE")
fi
if [[ -n "${DEPLOY_TARGETS:-}" ]]; then
  args+=(--targets "$DEPLOY_TARGETS")
fi
deploy_archive="${DEPLOY_ARCHIVE:-}"
if [[ -z "$deploy_archive" && "$deploy_mode" == "full_image" ]]; then
  deploy_archive="${IMAGE_TAR:-/tmp/investment-knowledge-images.tar.gz}"
fi
if [[ -n "$deploy_archive" ]]; then
  args+=(--archive "$deploy_archive")
fi
if [[ -n "${DEPLOY_EMERGENCY_REASON:-}" ]]; then
  args+=(--emergency-reason "$DEPLOY_EMERGENCY_REASON")
fi
if [[ -n "${DEPLOY_FEATURE_ROUTES:-}" ]]; then
  args+=(--feature-routes "$DEPLOY_FEATURE_ROUTES")
fi
if [[ -n "${DEPLOY_EVENT_ID:-}" ]]; then
  args+=(--external-event-id "$DEPLOY_EVENT_ID")
fi

exec "${args[@]}"
