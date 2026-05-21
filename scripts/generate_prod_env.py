from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import string


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a production .env file template with strong secrets.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / ".env.prod.local",
        help="Output path. Defaults to .env.prod.local.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite output file if it already exists.")
    parser.add_argument("--openai-api-key", default="", help="Optional OpenAI API key.")
    parser.add_argument("--openai-model", default="gpt-5.2", help="OpenAI model name.")
    parser.add_argument("--pip-index-url", default="https://mirrors.aliyun.com/pypi/simple/", help="Python package index URL.")
    parser.add_argument("--dingtalk-secret", default="", help="Optional DingTalk outgoing robot secret.")
    parser.add_argument("--dingtalk-send-webhook", default="", help="Optional DingTalk custom robot send webhook.")
    parser.add_argument("--dingtalk-send-secret", default="", help="Optional DingTalk custom robot send secret.")
    parser.add_argument("--dingtalk-stream-client-id", default="", help="Optional DingTalk Stream Mode client id.")
    parser.add_argument("--dingtalk-stream-client-secret", default="", help="Optional DingTalk Stream Mode secret.")
    parser.add_argument(
        "--dingtalk-stream-write-allowed-senders",
        default="",
        help="Comma-separated DingTalk sender ids allowed to run write commands.",
    )
    parser.add_argument("--allow-dingtalk-stream-write", action="store_true", help="Allow write commands in Stream Mode.")
    parser.add_argument("--postgres-user", default="postgres")
    parser.add_argument("--postgres-db", default="investment_kg")
    args = parser.parse_args()

    output_path = args.output
    if output_path.exists() and not args.force:
        raise SystemExit(f"{output_path} already exists. Use --force to overwrite.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        _render_env(
            postgres_user=args.postgres_user,
            postgres_password=_secret(32),
            postgres_db=args.postgres_db,
            command_api_token=_secret(40),
            dingtalk_secret=args.dingtalk_secret,
            dingtalk_send_webhook=args.dingtalk_send_webhook,
            dingtalk_send_secret=args.dingtalk_send_secret,
            dingtalk_stream_client_id=args.dingtalk_stream_client_id,
            dingtalk_stream_client_secret=args.dingtalk_stream_client_secret,
            dingtalk_stream_write_allowed_senders=args.dingtalk_stream_write_allowed_senders,
            dingtalk_stream_allow_write=args.allow_dingtalk_stream_write,
            openai_api_key=args.openai_api_key,
            openai_model=args.openai_model,
            pip_index_url=args.pip_index_url,
        ),
        encoding="utf-8",
    )
    print(f"Production env written to {output_path}")
    print("Review it, then copy it to .env on the server.")


def _render_env(
    *,
    postgres_user: str,
    postgres_password: str,
    postgres_db: str,
    command_api_token: str,
    dingtalk_secret: str,
    dingtalk_send_webhook: str,
    dingtalk_send_secret: str,
    dingtalk_stream_client_id: str,
    dingtalk_stream_client_secret: str,
    dingtalk_stream_write_allowed_senders: str,
    dingtalk_stream_allow_write: bool,
    openai_api_key: str,
    openai_model: str,
    pip_index_url: str,
) -> str:
    return f"""COMPOSE_PROJECT_NAME=turenagenttool_prod
COMPOSE_PROFILES=stream
APP_IMAGE_TAG=prod
PIP_INDEX_URL={pip_index_url}

POSTGRES_USER={postgres_user}
POSTGRES_PASSWORD={postgres_password}
POSTGRES_DB={postgres_db}

MCP_TRANSPORT=streamable-http
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_HOST_PORT=8000
MCP_PATH=/mcp

COMMAND_API_HOST=0.0.0.0
COMMAND_API_PORT=8001
COMMAND_API_HOST_PORT=8001
COMMAND_API_TOKEN={command_api_token}

DINGTALK_API_HOST=0.0.0.0
DINGTALK_API_PORT=8002
DINGTALK_API_HOST_PORT=8002
DINGTALK_OUTGOING_SECRET={dingtalk_secret}
DINGTALK_ALLOW_WRITE_COMMANDS=false
DINGTALK_SEND_WEBHOOK={dingtalk_send_webhook}
DINGTALK_SEND_SECRET={dingtalk_send_secret}
DINGTALK_STREAM_CLIENT_ID={dingtalk_stream_client_id}
DINGTALK_STREAM_CLIENT_SECRET={dingtalk_stream_client_secret}
DINGTALK_STREAM_ALLOW_WRITE={str(dingtalk_stream_allow_write).lower()}
DINGTALK_STREAM_WRITE_ALLOWED_SENDERS={dingtalk_stream_write_allowed_senders}

OPENAI_API_KEY={openai_api_key}
OPENAI_MODEL={openai_model}
OPENAI_ANALYSIS_ENABLED=true
"""


def _secret(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


if __name__ == "__main__":
    main()
