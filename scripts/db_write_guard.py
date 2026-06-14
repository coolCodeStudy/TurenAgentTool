from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from investment_knowledge_mcp.config import get_config


LOCAL_WRITE_ENV = "IKG_ALLOW_LOCAL_DB_WRITE"


def db_target_summary() -> str:
    config = get_config()
    if config.database_url:
        return f"DATABASE_URL={_redact_url(config.database_url)}"
    return (
        "POSTGRES="
        f"{config.postgres_user}@{config.postgres_host}:{config.postgres_port}/{config.postgres_db}"
    )


def ensure_not_default_local_write(*, allow_local_db: bool = False) -> None:
    if allow_local_db or _env_allows_local_write():
        return
    config = get_config()
    if not _is_default_local_database_url(config.database_url):
        return

    raise SystemExit(
        "Refusing to write to the default local database target.\n"
        f"- target: {db_target_summary()}\n"
        "- reason: this local DB is not the Codex MCP knowledge base; writing here can look successful "
        "while MCP still cannot see the data.\n"
        f"- to intentionally write local dev data, pass --allow-local-db or set {LOCAL_WRITE_ENV}=1.\n"
        "- to update the active MCP knowledge base, use MCP tools or the cloud Command API."
    )


def _env_allows_local_write() -> bool:
    return os.getenv(LOCAL_WRITE_ENV, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _is_default_local_database_url(database_url: str | None) -> bool:
    if not database_url:
        return False
    try:
        parsed = urlsplit(database_url)
    except ValueError:
        return False
    host = parsed.hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"} and parsed.port == 55432


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.password:
        return url
    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{username}:<redacted>@{host}{port}" if username else f"{host}{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
