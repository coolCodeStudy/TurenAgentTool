#!/usr/bin/env bash
set -euo pipefail

OPEND_DIR="${OPEND_DIR:-}"
CONFIG_DIR="${CONFIG_DIR:-/etc/futu-opend}"
CONFIG_FILE="${CONFIG_FILE:-${CONFIG_DIR}/FutuOpenD.xml}"
OPEND_HOST="${OPEND_HOST:-127.0.0.1}"
OPEND_PORT="${OPEND_PORT:-11111}"
PROXY_PORT="${PROXY_PORT:-11112}"
LANGUAGE="${LANGUAGE:-chs}"
LOG_LEVEL="${LOG_LEVEL:-info}"
FUTU_LOGIN_ACCOUNT="${FUTU_LOGIN_ACCOUNT:-}"
FUTU_LOGIN_PWD_MD5="${FUTU_LOGIN_PWD_MD5:-}"

usage() {
  cat <<USAGE
Usage: scripts/install_futu_opend_systemd.sh --opend-dir /opt/path/to/Futu_OpenD_dir

Installs two ECS host services:
  futu-opend.service        Runs FutuOpenD from a root-only XML config.
  futu-opend-proxy.service  Proxies docker0:${PROXY_PORT} -> ${OPEND_HOST}:${OPEND_PORT}.

Environment overrides:
  FUTU_LOGIN_ACCOUNT        Optional; prompted if empty.
  FUTU_LOGIN_PWD_MD5        Optional; prompted password is hashed if empty.
  OPEND_HOST                Default: ${OPEND_HOST}
  OPEND_PORT                Default: ${OPEND_PORT}
  PROXY_PORT                Default: ${PROXY_PORT}
  CONFIG_FILE               Default: ${CONFIG_FILE}

This script deliberately does not accept plaintext password flags, because
command-line flags often end up in shell history and process listings.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --opend-dir)
      OPEND_DIR="${2:-}"
      shift 2
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

if [ -z "$OPEND_DIR" ]; then
  echo "--opend-dir is required." >&2
  exit 1
fi

OPEND_DIR="${OPEND_DIR%/}"
OPEND_BIN="${OPEND_DIR}/FutuOpenD"
TEMPLATE_XML="${OPEND_DIR}/FutuOpenD.xml"

if [ ! -x "$OPEND_BIN" ]; then
  echo "FutuOpenD executable not found or not executable: $OPEND_BIN" >&2
  exit 1
fi

if [ ! -f "${OPEND_DIR}/Appdata.dat" ]; then
  echo "WARNING: Appdata.dat not found in $OPEND_DIR." >&2
  echo "Continuing because some OpenD builds generate or locate Appdata.dat at runtime." >&2
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to update FutuOpenD.xml safely." >&2
  exit 1
fi

if ! command -v socat >/dev/null 2>&1; then
  echo "Installing socat..."
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y socat
  elif command -v yum >/dev/null 2>&1; then
    $SUDO yum install -y socat
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y socat
  else
    echo "Cannot install socat automatically: unsupported Linux distribution." >&2
    exit 1
  fi
fi

BASH_BIN="$(command -v bash)"
SOCAT_BIN="$(command -v socat)"

if [ -z "$FUTU_LOGIN_ACCOUNT" ]; then
  read -r -p "Futu login account: " FUTU_LOGIN_ACCOUNT
fi

if [ -z "$FUTU_LOGIN_PWD_MD5" ]; then
  read -r -s -p "Futu login password, will be stored as MD5 in root-only XML: " FUTU_LOGIN_PWD
  printf '\n'
  FUTU_LOGIN_PWD_MD5="$(FUTU_LOGIN_PWD="$FUTU_LOGIN_PWD" python3 - <<'PY'
import hashlib
import os

print(hashlib.md5(os.environ["FUTU_LOGIN_PWD"].encode("utf-8")).hexdigest())
PY
)"
  unset FUTU_LOGIN_PWD
fi

if ! printf '%s' "$FUTU_LOGIN_PWD_MD5" | grep -Eq '^[0-9a-fA-F]{32}$'; then
  echo "FUTU_LOGIN_PWD_MD5 must be a 32-character hex MD5 string." >&2
  exit 1
fi

$SUDO mkdir -p "$CONFIG_DIR"
$SUDO chmod 700 "$CONFIG_DIR"

TMP_CONFIG="$(mktemp)"
TEMPLATE_XML="$TEMPLATE_XML" \
CONFIG_FILE="$TMP_CONFIG" \
FUTU_LOGIN_ACCOUNT="$FUTU_LOGIN_ACCOUNT" \
FUTU_LOGIN_PWD_MD5="$FUTU_LOGIN_PWD_MD5" \
OPEND_HOST="$OPEND_HOST" \
OPEND_PORT="$OPEND_PORT" \
LANGUAGE="$LANGUAGE" \
LOG_LEVEL="$LOG_LEVEL" \
python3 - <<'PY'
import os
import xml.etree.ElementTree as ET
from pathlib import Path

template = Path(os.environ["TEMPLATE_XML"])
target = Path(os.environ["CONFIG_FILE"])

if template.exists():
    tree = ET.parse(template)
    root = tree.getroot()
else:
    root = ET.Element("FutuOpenD")
    tree = ET.ElementTree(root)


def matching_name(element_name, names):
    return element_name.lower() in {name.lower() for name in names}


def set_text(names, value):
    for element in root.iter():
        if matching_name(element.tag, names):
            element.text = value
            return
    ET.SubElement(root, names[0]).text = value


set_text(("ip", "api_ip"), os.environ["OPEND_HOST"])
set_text(("api_port",), os.environ["OPEND_PORT"])
set_text(("login_account",), os.environ["FUTU_LOGIN_ACCOUNT"])
set_text(("login_pwd_md5",), os.environ["FUTU_LOGIN_PWD_MD5"])
set_text(("login_pwd",), "")
set_text(("Lang", "lang"), os.environ["LANGUAGE"])
set_text(("log_level",), os.environ["LOG_LEVEL"])
set_text(("no_monitor",), "1")

ET.indent(tree, space="  ")
tree.write(target, encoding="utf-8", xml_declaration=True)
PY

$SUDO install -m 600 "$TMP_CONFIG" "$CONFIG_FILE"
rm -f "$TMP_CONFIG"

cat > /tmp/futu-opend.service <<SERVICE
[Unit]
Description=Futu OpenD local gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${OPEND_DIR}
ExecStart=${OPEND_BIN} -cfg_file=${CONFIG_FILE}
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
SERVICE

cat > /tmp/futu-opend-proxy.service <<SERVICE
[Unit]
Description=Futu OpenD docker bridge proxy
After=network-online.target docker.service futu-opend.service
Requires=futu-opend.service
Wants=docker.service

[Service]
Type=simple
ExecStartPre=${BASH_BIN} -lc 'timeout 30 bash -c "until cat < /dev/null > /dev/tcp/${OPEND_HOST}/${OPEND_PORT}; do sleep 1; done"'
ExecStart=${BASH_BIN} -lc 'DOCKER_HOST_IP="\$(ip -4 addr show docker0 | awk "/inet / {print \\\$2}" | cut -d/ -f1)"; test -n "\$DOCKER_HOST_IP"; exec ${SOCAT_BIN} TCP-LISTEN:${PROXY_PORT},bind=\${DOCKER_HOST_IP},fork,reuseaddr TCP:${OPEND_HOST}:${OPEND_PORT}'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

$SUDO install -m 644 /tmp/futu-opend.service /etc/systemd/system/futu-opend.service
$SUDO install -m 644 /tmp/futu-opend-proxy.service /etc/systemd/system/futu-opend-proxy.service
rm -f /tmp/futu-opend.service /tmp/futu-opend-proxy.service

$SUDO systemctl daemon-reload
$SUDO systemctl stop futu-opend-proxy.service futu-opend.service >/dev/null 2>&1 || true
$SUDO pkill -f "socat.*TCP-LISTEN:${PROXY_PORT}" >/dev/null 2>&1 || true
$SUDO pkill -f FutuOpenD >/dev/null 2>&1 || true
$SUDO systemctl enable futu-opend.service futu-opend-proxy.service
$SUDO systemctl start futu-opend.service
$SUDO systemctl start futu-opend-proxy.service

echo "Installed Futu OpenD systemd services."
echo "Config file: $CONFIG_FILE"
echo
echo "Check status:"
echo "  systemctl status futu-opend.service --no-pager"
echo "  systemctl status futu-opend-proxy.service --no-pager"
echo "  ss -lntp | grep -E '11111|11112'"
