#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON_BIN:-python3}"
app_root="${APP_ROOT:-${INVESTMENT_APP_ROOT:-/opt/investment-knowledge}}"
source_dir="${SOURCE_DIR:-$(pwd)}"
deploy_mode="${DEPLOY_MODE:-}"
deploy_ref="${DEPLOY_REF:-}"
deploy_archive="${DEPLOY_ARCHIVE:-}"
deploy_archive_sha256="${DEPLOY_ARCHIVE_SHA256:-}"
conventional_archive="${IMAGE_TAR:-/tmp/investment-knowledge-images.tar.gz}"

if [[ -z "$deploy_archive" && -f "$conventional_archive" ]]; then
  deploy_archive="$conventional_archive"
fi

if [[ -z "$deploy_ref" ]]; then
  deploy_ref="$(git -C "$source_dir" rev-parse HEAD 2>/dev/null || true)"
fi
deploy_ref="${deploy_ref:-main}"

if [[ -z "$deploy_mode" ]]; then
  if [[ "${BUILD_IMAGE:-false}" == "true" || -n "$deploy_archive" ]]; then
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

if [[ "$deploy_mode" == "full_image" && -n "$deploy_archive" && -z "$deploy_archive_sha256" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    deploy_archive_sha256="$(sha256sum "$deploy_archive" | awk '{print $1}')"
  else
    deploy_archive_sha256="$(shasum -a 256 "$deploy_archive" | awk '{print $1}')"
  fi
fi

args=(
  "$python_bin"
  "$script_dir/deploy_release.py"
  --ref "$deploy_ref"
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
if [[ -n "$deploy_archive" ]]; then
  args+=(--archive "$deploy_archive")
fi
if [[ -n "$deploy_archive_sha256" ]]; then
  args+=(--archive-sha256 "$deploy_archive_sha256")
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
