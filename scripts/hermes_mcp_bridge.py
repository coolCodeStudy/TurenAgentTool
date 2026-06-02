#!/usr/bin/env python3
from __future__ import annotations

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json
import os

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("HermesInvestmentBridge")


class BridgeError(RuntimeError):
    pass


@mcp.tool()
def hermes_command(command: str, source: str = "codex-app") -> dict[str, Any]:
    """Send a natural-language InvestmentKnowledge command through the cloud command endpoint."""
    command = command.strip()
    if not command:
        return {"ok": False, "message": "command is required"}
    return _post_command(command=command, source=source)


@mcp.tool()
def hermes_cloud_status() -> dict[str, Any]:
    """Read cloud system status through the controlled Ops API."""
    return _ops_get("/ops/status")


@mcp.tool()
def hermes_recent_errors(lines: int = 160) -> dict[str, Any]:
    """Read recent cloud errors through the controlled Ops API."""
    return _ops_get("/ops/recent-errors", {"lines": lines})


@mcp.tool()
def hermes_service_logs(service: str, lines: int = 120) -> dict[str, Any]:
    """Read recent logs for a whitelisted cloud service."""
    return _ops_get("/ops/logs", {"service": service, "lines": lines})


@mcp.tool()
def hermes_coding_status() -> dict[str, Any]:
    """Read cloud Codex worker status through the controlled Ops API."""
    return _ops_get("/ops/coding-status")


def _post_command(command: str, source: str) -> dict[str, Any]:
    url = _required_env("COMMAND_API_URL").rstrip("/") + "/command"
    token = _required_env("COMMAND_API_TOKEN")
    payload = json.dumps({"text": command, "source": source}, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    return _read_json(request, timeout=float(os.getenv("HERMES_BRIDGE_TIMEOUT_SECONDS", "20")))


def _ops_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    base_url = _required_env("OPS_API_URL").rstrip("/")
    token = os.getenv("OPS_API_TOKEN") or os.getenv("COMMAND_API_TOKEN")
    if not token:
        raise BridgeError("OPS_API_TOKEN or COMMAND_API_TOKEN is required")
    query = f"?{urlencode(params)}" if params else ""
    request = Request(
        base_url + path + query,
        headers={"Authorization": f"Bearer {token}"},
    )
    return _read_json(request, timeout=float(os.getenv("HERMES_BRIDGE_TIMEOUT_SECONDS", "20")))


def _read_json(request: Request, timeout: float) -> dict[str, Any]:
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BridgeError(f"HTTP {exc.code}: {body}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise BridgeError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise BridgeError("endpoint returned a non-object JSON payload")
    return payload


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise BridgeError(f"{name} is required")
    return value


if __name__ == "__main__":
    mcp.run()
