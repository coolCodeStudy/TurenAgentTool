#!/usr/bin/env bash
set -euo pipefail

OPEND_DIR="${OPEND_DIR:-}"
CONFIG_DIR="${CONFIG_DIR:-/etc/futu-opend}"
ENV_FILE="${ENV_FILE:-${CONFIG_DIR}/futu-opend.env}"
START_SCRIPT="${START_SCRIPT:-/usr/local/bin/futu-opend-start.sh}"
PROXY_SCRIPT="${PROXY_SCRIPT:-/usr/local/bin/futu-opend-proxy.sh}"
OPEND_HOST="${OPEND_HOST:-127.0.0.1}"
OPEND_PORT="${OPEND_PORT:-11111}"
PROXY_PORT="${PROXY_PORT:-11112}"
TELNET_HOST="${TELNET_HOST:-127.0.0.1}"
TELNET_PORT="${TELNET_PORT:-22222}"
TELNET_PROXY_PORT="${TELNET_PROXY_PORT:-22222}"
LANGUAGE="${LANGUAGE:-chs}"
FUTU_LOGIN_ACCOUNT="${FUTU_LOGIN_ACCOUNT:-}"
FUTU_LOGIN_PWD="${FUTU_LOGIN_PWD:-}"

usage() {
  cat <<USAGE
Usage: scripts/install_futu_opend_simple_systemd.sh --opend-dir /opt/path/to/Futu_OpenD_dir

Installs:
  futu-opend.service        Runs FutuOpenD with the known-good command-line flags.
  futu-opend-proxy.service  Proxies docker0:${PROXY_PORT} -> ${OPEND_HOST}:${OPEND_PORT}.

This is the pragmatic fallback for OpenD builds where -cfg_file exits with
status=14. It stores credentials in ${ENV_FILE} with mode 600, then uses the
same startup shape that has already worked manually.

Tradeoff: the running FutuOpenD process may still expose -login_pwd in ps output.
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

if [ ! -x "$OPEND_BIN" ]; then
  echo "FutuOpenD executable not found or not executable: $OPEND_BIN" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required for safe shell quoting." >&2
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

if [ -z "$FUTU_LOGIN_ACCOUNT" ]; then
  read -r -p "Futu login account: " FUTU_LOGIN_ACCOUNT
fi

if [ -z "$FUTU_LOGIN_PWD" ]; then
  read -r -s -p "Futu login password, will be stored in root-only env file: " FUTU_LOGIN_PWD
  printf '\n'
fi

shell_quote() {
  python3 -c 'import shlex, sys; print(shlex.quote(sys.argv[1]))' "$1"
}

BASH_BIN="$(command -v bash)"
SOCAT_BIN="$(command -v socat)"

$SUDO mkdir -p "$CONFIG_DIR"
$SUDO chmod 700 "$CONFIG_DIR"

TMP_ENV="$(mktemp)"
{
  printf 'OPEND_DIR=%s\n' "$(shell_quote "$OPEND_DIR")"
  printf 'OPEND_BIN=%s\n' "$(shell_quote "$OPEND_BIN")"
  printf 'FUTU_LOGIN_ACCOUNT=%s\n' "$(shell_quote "$FUTU_LOGIN_ACCOUNT")"
  printf 'FUTU_LOGIN_PWD=%s\n' "$(shell_quote "$FUTU_LOGIN_PWD")"
  printf 'OPEND_HOST=%s\n' "$(shell_quote "$OPEND_HOST")"
  printf 'OPEND_PORT=%s\n' "$(shell_quote "$OPEND_PORT")"
  printf 'TELNET_HOST=%s\n' "$(shell_quote "$TELNET_HOST")"
  printf 'TELNET_PORT=%s\n' "$(shell_quote "$TELNET_PORT")"
  printf 'LANGUAGE=%s\n' "$(shell_quote "$LANGUAGE")"
} > "$TMP_ENV"
$SUDO install -m 600 "$TMP_ENV" "$ENV_FILE"
rm -f "$TMP_ENV"
unset FUTU_LOGIN_PWD

cat > /tmp/futu-opend-start.sh <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail

source ${ENV_FILE}
cd "\$OPEND_DIR"

exec "\$OPEND_BIN" \\
  -login_account="\$FUTU_LOGIN_ACCOUNT" \\
  -login_pwd="\$FUTU_LOGIN_PWD" \\
  -api_ip="\$OPEND_HOST" \\
  -api_port="\$OPEND_PORT" \\
  -telnet_ip="\$TELNET_HOST" \\
  -telnet_port="\$TELNET_PORT" \\
  -lang="\$LANGUAGE"
SCRIPT

cat > /tmp/futu-opend.service <<SERVICE
[Unit]
Description=Futu OpenD local gateway
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${START_SCRIPT}
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
SERVICE

cat > /tmp/futu-opend-proxy.sh <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail

DOCKER_HOST_IP="\$(ip -4 addr show docker0 | awk '/inet / {print \$2}' | cut -d/ -f1)"
if [ -z "\$DOCKER_HOST_IP" ]; then
  echo "Cannot detect docker0 IPv4 address. Is Docker running?" >&2
  exit 1
fi

api_pid=""
telnet_pid=""

cleanup() {
  if [ -n "\$api_pid" ]; then kill "\$api_pid" >/dev/null 2>&1 || true; fi
  if [ -n "\$telnet_pid" ]; then kill "\$telnet_pid" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT INT TERM

${SOCAT_BIN} "TCP-LISTEN:${PROXY_PORT},bind=\${DOCKER_HOST_IP},fork,reuseaddr" "TCP:${OPEND_HOST}:${OPEND_PORT}" &
api_pid="\$!"

${SOCAT_BIN} "TCP-LISTEN:${TELNET_PROXY_PORT},bind=\${DOCKER_HOST_IP},fork,reuseaddr" "TCP:${TELNET_HOST}:${TELNET_PORT}" &
telnet_pid="\$!"

wait -n "\$api_pid" "\$telnet_pid"
SCRIPT

cat > /tmp/futu-opend-proxy.service <<SERVICE
[Unit]
Description=Futu OpenD docker bridge proxy
After=network-online.target docker.service futu-opend.service
Requires=futu-opend.service
Wants=docker.service

[Service]
Type=simple
ExecStartPre=${BASH_BIN} -lc 'timeout 30 bash -c "until cat < /dev/null > /dev/tcp/${OPEND_HOST}/${OPEND_PORT}; do sleep 1; done"'
ExecStartPre=${BASH_BIN} -lc 'timeout 30 bash -c "until cat < /dev/null > /dev/tcp/${TELNET_HOST}/${TELNET_PORT}; do sleep 1; done"'
ExecStart=${PROXY_SCRIPT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

$SUDO install -m 755 /tmp/futu-opend-start.sh "$START_SCRIPT"
$SUDO install -m 755 /tmp/futu-opend-proxy.sh "$PROXY_SCRIPT"
$SUDO install -m 644 /tmp/futu-opend.service /etc/systemd/system/futu-opend.service
$SUDO install -m 644 /tmp/futu-opend-proxy.service /etc/systemd/system/futu-opend-proxy.service
rm -f /tmp/futu-opend-start.sh /tmp/futu-opend.service /tmp/futu-opend-proxy.sh /tmp/futu-opend-proxy.service

$SUDO systemctl daemon-reload
$SUDO systemctl stop futu-opend-proxy.service futu-opend.service >/dev/null 2>&1 || true
$SUDO pkill -f "socat.*TCP-LISTEN:${PROXY_PORT}" >/dev/null 2>&1 || true
$SUDO pkill -f FutuOpenD >/dev/null 2>&1 || true
$SUDO systemctl enable futu-opend.service futu-opend-proxy.service
$SUDO systemctl start futu-opend.service
$SUDO systemctl start futu-opend-proxy.service

echo "Installed simple Futu OpenD systemd services."
echo "Credential env file: $ENV_FILE"
echo
echo "Check status:"
echo "  systemctl status futu-opend.service --no-pager"
echo "  systemctl status futu-opend-proxy.service --no-pager"
echo "  ss -lntp | grep -E '11111|11112'"
