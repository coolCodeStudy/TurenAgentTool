#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${TARGET_DIR:-/opt/futu-opend}"
FLAVOR="${FLAVOR:-ubuntu}"
FORCE=false

usage() {
  cat <<USAGE
Usage: scripts/download_futu_opend.sh [--target-dir /opt/futu-opend] [--flavor ubuntu|centos] [--force]

Downloads the official Futu OpenD command-line package, extracts it, and prints
the exact --opend-dir value for scripts/install_futu_opend_simple_systemd.sh.

This installs the OpenD gateway program. It is different from the Python
futu-api SDK, which only provides client APIs.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --target-dir)
      TARGET_DIR="${2:-}"
      shift 2
      ;;
    --flavor)
      FLAVOR="${2:-}"
      shift 2
      ;;
    --force)
      FORCE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  SUDO="sudo"
fi

case "$FLAVOR" in
  ubuntu)
    DOWNLOAD_URL="https://www.futunn.com/download/fetch-lasted-link?name=opend-ubuntu"
    ;;
  centos)
    DOWNLOAD_URL="https://www.futunn.com/download/fetch-lasted-link?name=opend-centos"
    ;;
  *)
    echo "--flavor must be ubuntu or centos." >&2
    exit 1
    ;;
esac

if ! command -v curl >/dev/null 2>&1; then
  echo "Installing curl..."
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y curl ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    $SUDO yum install -y curl ca-certificates
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y curl ca-certificates
  else
    echo "Cannot install curl automatically: unsupported Linux distribution." >&2
    exit 1
  fi
fi

if ! command -v tar >/dev/null 2>&1; then
  echo "tar is required but not installed." >&2
  exit 1
fi

$SUDO mkdir -p "$TARGET_DIR"
$SUDO chmod 755 "$TARGET_DIR"

ARCHIVE="${TARGET_DIR%/}/futu-opend-${FLAVOR}.tar.gz"
if [ -f "$ARCHIVE" ] && [ "$FORCE" != true ]; then
  echo "Archive already exists: $ARCHIVE"
  echo "Use --force to download it again."
else
  echo "Downloading official Futu OpenD ${FLAVOR} package..."
  echo "Source: $DOWNLOAD_URL"
  $SUDO curl -fL --retry 3 --connect-timeout 20 -o "$ARCHIVE" "$DOWNLOAD_URL"
fi

EXTRACT_DIR="${TARGET_DIR%/}/extract-${FLAVOR}"
if [ -d "$EXTRACT_DIR" ] && [ "$FORCE" != true ]; then
  echo "Extract directory already exists: $EXTRACT_DIR"
  echo "Use --force to re-extract it."
else
  $SUDO rm -rf "$EXTRACT_DIR"
  $SUDO mkdir -p "$EXTRACT_DIR"
  echo "Extracting package..."
  $SUDO tar -xzf "$ARCHIVE" -C "$EXTRACT_DIR"
fi

OPEND_BIN="$(find "$EXTRACT_DIR" -type f -name FutuOpenD -perm -111 | head -n 1 || true)"
if [ -z "$OPEND_BIN" ]; then
  OPEND_BIN="$(find "$EXTRACT_DIR" -type f -name FutuOpenD | head -n 1 || true)"
fi
if [ -z "$OPEND_BIN" ]; then
  echo "FutuOpenD executable was not found after extraction." >&2
  echo "Debug listing:" >&2
  find "$EXTRACT_DIR" -maxdepth 4 -type f | head -50 >&2
  exit 1
fi

OPEND_DIR="$(dirname "$OPEND_BIN")"
$SUDO chmod +x "$OPEND_BIN"

missing=()
for required in FutuOpenD.xml Appdata.dat; do
  if [ ! -f "$OPEND_DIR/$required" ]; then
    missing+=("$required")
  fi
done

echo
echo "Futu OpenD package is ready."
echo "OpenD directory:"
echo "  $OPEND_DIR"
echo

if [ "${#missing[@]}" -gt 0 ]; then
  echo "Warning: missing expected file(s): ${missing[*]}"
  echo "The official command-line package should normally include FutuOpenD.xml and Appdata.dat."
  echo "If OpenD fails to start, download the package again with --force or check the official download page."
  echo
fi

echo "Next command:"
echo "  cd /opt/investment-knowledge"
echo "  bash scripts/install_futu_opend_simple_systemd.sh --opend-dir '$OPEND_DIR'"
