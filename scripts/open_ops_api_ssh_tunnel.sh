#!/usr/bin/env bash
set -euo pipefail

ECS_PORT=${ECS_PORT:-22}
OPS_API_LOCAL_PORT=${OPS_API_LOCAL_PORT:-18767}
OPS_API_REMOTE_HOST=${OPS_API_REMOTE_HOST:-172.17.0.1}
OPS_API_REMOTE_PORT=${OPS_API_REMOTE_PORT:-8767}

for name in ECS_HOST ECS_USERNAME ECS_PASSWORD ECS_SSH_KNOWN_HOSTS; do
  if [ -z "${!name:-}" ]; then
    echo "Missing required tunnel setting: $name" >&2
    exit 1
  fi
done

if ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required to open the private Ops API tunnel." >&2
  exit 1
fi

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
printf '%s\n' "$ECS_SSH_KNOWN_HOSTS" > "$HOME/.ssh/known_hosts"
chmod 600 "$HOME/.ssh/known_hosts"

export SSHPASS="$ECS_PASSWORD"
tunnel_open=false
for attempt in 1 2 3; do
  if sshpass -e ssh \
    -p "$ECS_PORT" \
    -o ConnectTimeout=10 \
    -o ExitOnForwardFailure=yes \
    -o LogLevel=ERROR \
    -o ServerAliveCountMax=3 \
    -o ServerAliveInterval=15 \
    -o StrictHostKeyChecking=yes \
    -o UserKnownHostsFile="$HOME/.ssh/known_hosts" \
    -fNT \
    -L "127.0.0.1:${OPS_API_LOCAL_PORT}:${OPS_API_REMOTE_HOST}:${OPS_API_REMOTE_PORT}" \
    "${ECS_USERNAME}@${ECS_HOST}"; then
    tunnel_open=true
    break
  fi
  if [ "$attempt" -lt 3 ]; then
    sleep 3
  fi
done
unset SSHPASS

if [ "$tunnel_open" != "true" ]; then
  echo "Unable to establish the private Ops API SSH tunnel after 3 attempts." >&2
  exit 1
fi

ops_api_url="http://127.0.0.1:${OPS_API_LOCAL_PORT}"
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if curl --connect-timeout 3 --max-time 5 --fail --silent --show-error "$ops_api_url/health" >/dev/null; then
    if [ -n "${GITHUB_ENV:-}" ]; then
      echo "OPS_API_URL=$ops_api_url" >> "$GITHUB_ENV"
    fi
    echo "Private Ops API tunnel is healthy at $ops_api_url."
    exit 0
  fi
  if [ "$attempt" -lt 10 ]; then
    sleep 1
  fi
done

echo "The SSH tunnel opened, but the private Ops API health check failed." >&2
exit 1
