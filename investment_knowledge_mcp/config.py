from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:55432/investment_kg"
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
    database_url: str = DEFAULT_DATABASE_URL
    mcp_transport: Literal["stdio", "sse", "streamable-http"] = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"
    command_api_host: str = "127.0.0.1"
    command_api_port: int = 8001
    command_api_token: str | None = None


def get_config() -> AppConfig:
    load_env_file()
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("MCP_TRANSPORT must be one of: stdio, sse, streamable-http")

    return AppConfig(
        database_url=os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL),
        mcp_transport=transport,  # type: ignore[arg-type]
        mcp_host=os.getenv("MCP_HOST", "127.0.0.1"),
        mcp_port=int(os.getenv("MCP_PORT", "8000")),
        mcp_path=os.getenv("MCP_PATH", "/mcp"),
        command_api_host=os.getenv("COMMAND_API_HOST", "127.0.0.1"),
        command_api_port=int(os.getenv("COMMAND_API_PORT", "8001")),
        command_api_token=os.getenv("COMMAND_API_TOKEN") or None,
    )
