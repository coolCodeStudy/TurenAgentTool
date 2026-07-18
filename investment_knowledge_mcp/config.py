from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


DEFAULT_POSTGRES_HOST = "localhost"
DEFAULT_POSTGRES_PORT = 55432
DEFAULT_POSTGRES_USER = "postgres"
DEFAULT_POSTGRES_PASSWORD = "postgres"
DEFAULT_POSTGRES_DB = "investment_kg"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_env_file(path: Path | None = None) -> None:
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class AppConfig:
    database_url: str | None = None
    postgres_host: str = DEFAULT_POSTGRES_HOST
    postgres_port: int = DEFAULT_POSTGRES_PORT
    postgres_user: str = DEFAULT_POSTGRES_USER
    postgres_password: str = DEFAULT_POSTGRES_PASSWORD
    postgres_db: str = DEFAULT_POSTGRES_DB
    mcp_transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"
    command_api_host: str = "127.0.0.1"
    command_api_port: int = 8001
    command_api_token: str | None = field(default=None, repr=False)
    weekly_review_web_host: str = "127.0.0.1"
    weekly_review_web_port: int = 8010
    weekly_review_web_token: str | None = field(default=None, repr=False)
    dingtalk_api_host: str = "127.0.0.1"
    dingtalk_api_port: int = 8002
    dingtalk_outgoing_secret: str | None = None
    dingtalk_allow_write_commands: bool = False
    dingtalk_send_webhook: str | None = None
    dingtalk_send_secret: str | None = None
    dingtalk_stream_client_id: str | None = None
    dingtalk_stream_client_secret: str | None = None
    dingtalk_stream_write_allowed_senders: tuple[str, ...] = ()
    dingtalk_command_timeout_seconds: int = 25
    dingtalk_ipo_reminders_enabled: bool = True
    dingtalk_ipo_reminder_interval_seconds: int = 300
    account_snapshot_scheduler_enabled: bool = True
    account_snapshot_time: str = "00:05"
    account_snapshot_interval_seconds: int = 300
    futu_opend_host: str = "127.0.0.1"
    futu_opend_port: int = 11112
    futu_opend_telnet_host: str = "127.0.0.1"
    futu_opend_telnet_port: int = 22222
    futu_security_firm: str = "FUTUSECURITIES"
    futu_trade_market: str = "HK"
    futu_trade_env: str = "REAL"
    futu_account_id: int = 0
    futu_account_index: int = 0
    futu_position_cache_seconds: int = 20
    futu_position_refresh_cache: bool = True
    ops_api_url: str | None = None
    ops_api_token: str | None = None
    ops_api_timeout_seconds: float = 8.0
    ops_api_deploy_timeout_seconds: float = 600.0
    app_access_token: str | None = field(default=None, repr=False)


def get_config() -> AppConfig:
    load_env_file()
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("MCP_TRANSPORT must be one of: stdio, sse, streamable-http")

    return AppConfig(
        database_url=os.getenv("DATABASE_URL") or None,
        postgres_host=os.getenv("POSTGRES_HOST", DEFAULT_POSTGRES_HOST),
        postgres_port=int(os.getenv("POSTGRES_PORT", str(DEFAULT_POSTGRES_PORT))),
        postgres_user=os.getenv("POSTGRES_USER", DEFAULT_POSTGRES_USER),
        postgres_password=os.getenv("POSTGRES_PASSWORD", DEFAULT_POSTGRES_PASSWORD),
        postgres_db=os.getenv("POSTGRES_DB", DEFAULT_POSTGRES_DB),
        mcp_transport=transport,  # type: ignore[arg-type]
        mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
        mcp_port=int(os.getenv("MCP_PORT", "8000")),
        mcp_path=os.getenv("MCP_PATH", "/mcp"),
        command_api_host=os.getenv("COMMAND_API_HOST", "127.0.0.1"),
        command_api_port=int(os.getenv("COMMAND_API_PORT", "8001")),
        app_access_token=os.getenv("APP_ACCESS_TOKEN") or None,
        command_api_token=os.getenv("COMMAND_API_TOKEN") or None,
        weekly_review_web_host=os.getenv("WEEKLY_REVIEW_WEB_HOST", "127.0.0.1"),
        weekly_review_web_port=int(os.getenv("WEEKLY_REVIEW_WEB_PORT", "8010")),
        weekly_review_web_token=os.getenv("WEEKLY_REVIEW_WEB_TOKEN") or None,
        dingtalk_api_host=os.getenv("DINGTALK_API_HOST", "127.0.0.1"),
        dingtalk_api_port=int(os.getenv("DINGTALK_API_PORT", "8002")),
        dingtalk_outgoing_secret=os.getenv("DINGTALK_OUTGOING_SECRET") or None,
        dingtalk_allow_write_commands=_get_bool("DINGTALK_ALLOW_WRITE_COMMANDS", default=False),
        dingtalk_send_webhook=os.getenv("DINGTALK_SEND_WEBHOOK") or None,
        dingtalk_send_secret=os.getenv("DINGTALK_SEND_SECRET") or None,
        dingtalk_stream_client_id=os.getenv("DINGTALK_STREAM_CLIENT_ID") or None,
        dingtalk_stream_client_secret=os.getenv("DINGTALK_STREAM_CLIENT_SECRET") or None,
        dingtalk_stream_write_allowed_senders=_get_csv("DINGTALK_STREAM_WRITE_ALLOWED_SENDERS"),
        dingtalk_command_timeout_seconds=int(os.getenv("DINGTALK_COMMAND_TIMEOUT_SECONDS", "25")),
        dingtalk_ipo_reminders_enabled=_get_bool("DINGTALK_IPO_REMINDERS_ENABLED", default=True),
        dingtalk_ipo_reminder_interval_seconds=int(os.getenv("DINGTALK_IPO_REMINDER_INTERVAL_SECONDS", "300")),
        account_snapshot_scheduler_enabled=_get_bool("ACCOUNT_SNAPSHOT_SCHEDULER_ENABLED", default=True),
        account_snapshot_time=os.getenv("ACCOUNT_SNAPSHOT_TIME", "00:05"),
        account_snapshot_interval_seconds=int(os.getenv("ACCOUNT_SNAPSHOT_INTERVAL_SECONDS", "300")),
        futu_opend_host=os.getenv("FUTU_OPEND_HOST", "127.0.0.1"),
        futu_opend_port=int(os.getenv("FUTU_OPEND_PORT", "11112")),
        futu_opend_telnet_host=os.getenv("FUTU_OPEND_TELNET_HOST", "127.0.0.1"),
        futu_opend_telnet_port=int(os.getenv("FUTU_OPEND_TELNET_PORT", "22222")),
        futu_security_firm=os.getenv("FUTU_SECURITY_FIRM", "FUTUSECURITIES"),
        futu_trade_market=os.getenv("FUTU_TRADE_MARKET", "HK"),
        futu_trade_env=os.getenv("FUTU_TRADE_ENV", "REAL"),
        futu_account_id=int(os.getenv("FUTU_ACCOUNT_ID", "0")),
        futu_account_index=int(os.getenv("FUTU_ACCOUNT_INDEX", "0")),
        futu_position_cache_seconds=int(os.getenv("FUTU_POSITION_CACHE_SECONDS", "20")),
        futu_position_refresh_cache=_get_bool("FUTU_POSITION_REFRESH_CACHE", default=True),
        ops_api_url=os.getenv("OPS_API_URL") or None,
        ops_api_token=os.getenv("OPS_API_TOKEN") or None,
        ops_api_timeout_seconds=float(os.getenv("OPS_API_TIMEOUT_SECONDS", "8")),
        ops_api_deploy_timeout_seconds=float(os.getenv("OPS_API_DEPLOY_TIMEOUT_SECONDS", "600")),
    )


def _get_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_csv(key: str) -> tuple[str, ...]:
    value = os.getenv(key)
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())
