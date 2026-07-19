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
    parser.add_argument("--futu-opend-host", default="127.0.0.1")
    parser.add_argument("--futu-opend-port", default="11112")
    parser.add_argument("--futu-security-firm", default="FUTUSECURITIES")
    parser.add_argument("--futu-trade-market", default="HK")
    parser.add_argument("--futu-trade-env", default="REAL")
    parser.add_argument("--futu-account-id", default="0")
    parser.add_argument("--futu-account-index", default="0")
    parser.add_argument("--futu-position-cache-seconds", default="20")
    parser.add_argument("--futu-position-refresh-cache", default="true")
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
            ops_api_token=_secret(40),
            dingtalk_secret=args.dingtalk_secret,
            dingtalk_send_webhook=args.dingtalk_send_webhook,
            dingtalk_send_secret=args.dingtalk_send_secret,
            dingtalk_stream_client_id=args.dingtalk_stream_client_id,
            dingtalk_stream_client_secret=args.dingtalk_stream_client_secret,
            dingtalk_stream_write_allowed_senders=args.dingtalk_stream_write_allowed_senders,
            dingtalk_stream_allow_write=args.allow_dingtalk_stream_write,
            futu_opend_host=args.futu_opend_host,
            futu_opend_port=args.futu_opend_port,
            futu_security_firm=args.futu_security_firm,
            futu_trade_market=args.futu_trade_market,
            futu_trade_env=args.futu_trade_env,
            futu_account_id=args.futu_account_id,
            futu_account_index=args.futu_account_index,
            futu_position_cache_seconds=args.futu_position_cache_seconds,
            futu_position_refresh_cache=args.futu_position_refresh_cache,
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
    ops_api_token: str,
    dingtalk_secret: str,
    dingtalk_send_webhook: str,
    dingtalk_send_secret: str,
    dingtalk_stream_client_id: str,
    dingtalk_stream_client_secret: str,
    dingtalk_stream_write_allowed_senders: str,
    dingtalk_stream_allow_write: bool,
    futu_opend_host: str,
    futu_opend_port: str,
    futu_security_firm: str,
    futu_trade_market: str,
    futu_trade_env: str,
    futu_account_id: str,
    futu_account_index: str,
    futu_position_cache_seconds: str,
    futu_position_refresh_cache: str,
    openai_api_key: str,
    openai_model: str,
    pip_index_url: str,
) -> str:
    return f"""COMPOSE_PROJECT_NAME=turenagenttool_prod
COMPOSE_PROFILES=stream,http
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

COMMAND_API_HOST_PORT=8001
APP_ACCESS_TOKEN={command_api_token}
COMMAND_API_TOKEN={command_api_token}
OPS_API_TOKEN={ops_api_token}

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
DINGTALK_IPO_REMINDERS_ENABLED=true
DINGTALK_IPO_REMINDER_INTERVAL_SECONDS=300
ACCOUNT_SNAPSHOT_SCHEDULER_ENABLED=true
ACCOUNT_SNAPSHOT_TIME=00:05
ACCOUNT_SNAPSHOT_INTERVAL_SECONDS=300

FUTU_OPEND_HOST={futu_opend_host}
FUTU_OPEND_PORT={futu_opend_port}
FUTU_SECURITY_FIRM={futu_security_firm}
FUTU_TRADE_MARKET={futu_trade_market}
FUTU_TRADE_ENV={futu_trade_env}
FUTU_ACCOUNT_ID={futu_account_id}
FUTU_ACCOUNT_INDEX={futu_account_index}
FUTU_POSITION_CACHE_SECONDS={futu_position_cache_seconds}
FUTU_POSITION_REFRESH_CACHE={futu_position_refresh_cache}

OPENAI_API_KEY={openai_api_key}
OPENAI_MODEL={openai_model}
OPENAI_ANALYSIS_ENABLED=true
"""


def _secret(length: int) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


if __name__ == "__main__":
    main()
