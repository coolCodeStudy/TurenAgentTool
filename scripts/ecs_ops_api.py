#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import hmac
import json
import os
import re
import socket
import subprocess
import time


APP_DIR = Path(os.getenv("INVESTMENT_DIR", "/opt/investment-knowledge"))
COMPOSE_FILE = APP_DIR / "docker-compose.prod.yml"
HOST = os.getenv("OPS_API_HOST", "127.0.0.1")
PORT = int(os.getenv("OPS_API_PORT", "8767"))
TOKEN = os.getenv("OPS_API_TOKEN") or os.getenv("COMMAND_API_TOKEN") or ""
MAX_LOG_LINES = 400
COMMAND_TIMEOUT_SECONDS = float(os.getenv("OPS_API_COMMAND_TIMEOUT_SECONDS", "8"))


COMPOSE_SERVICES = {
    "mcp": "mcp",
    "command-api": "command-api",
    "dingtalk-stream-bot": "dingtalk-stream-bot",
    "postgres": "postgres",
}

SYSTEMD_SERVICES = {
    "hermes": "hermes-gateway.service",
    "codex-worker": "investment-codex-worker.service",
    "futu-opend": "futu-opend.service",
    "futu-proxy": "futu-opend-proxy.service",
    "ops-api": "investment-ops-api.service",
}

SERVICE_ALIASES = {
    "worker": "codex-worker",
    "codex_worker": "codex-worker",
    "codex": "codex-worker",
    "hermes-gateway": "hermes",
    "dingtalk": "dingtalk-stream-bot",
    "stream": "dingtalk-stream-bot",
    "futu": "futu-opend",
    "opend": "futu-opend",
    "futu_proxy": "futu-proxy",
}

SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(access_token=)[^&\s]+"), r"\1<redacted>"),
    (re.compile(r"(?i)(token|secret|password|passwd|pwd|webhook|api[_-]?key)(\s*[=:]\s*)([^\s,'\"}]+)"), r"\1\2<redacted>"),
    (re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
    (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "sk-<redacted>"),
    (re.compile(r"(?i)(login_pwd=)[^\s]+"), r"\1<redacted>"),
    (re.compile(r"(?i)(login_pwd_md5=)[^\s]+"), r"\1<redacted>"),
]


@dataclass
class CommandResult:
    ok: bool
    command: list[str]
    stdout: str
    stderr: str
    returncode: int


class OpsRequestHandler(BaseHTTPRequestHandler):
    server_version = "InvestmentKnowledgeOpsAPI/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(HTTPStatus.OK, {"ok": True, "service": "investment-ops-api"})
            return

        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return

        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/ops/status":
                self._write_json(HTTPStatus.OK, {"ok": True, "data": build_system_status()})
            elif parsed.path == "/ops/recent-errors":
                lines = _int_query(query, "lines", 160, minimum=20, maximum=MAX_LOG_LINES)
                self._write_json(HTTPStatus.OK, {"ok": True, "data": build_recent_errors(lines=lines)})
            elif parsed.path == "/ops/logs":
                service = _first_query(query, "service") or ""
                lines = _int_query(query, "lines", 120, minimum=20, maximum=MAX_LOG_LINES)
                self._write_json(HTTPStatus.OK, {"ok": True, "data": get_service_logs(service=service, lines=lines)})
            elif parsed.path == "/ops/coding-status":
                self._write_json(HTTPStatus.OK, {"ok": True, "data": build_coding_status()})
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": sanitize_text(str(exc))})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _authorized(self) -> bool:
        if not TOKEN:
            return False
        authorization = self.headers.get("Authorization")
        if authorization and authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ").strip()
            return hmac.compare_digest(supplied, TOKEN)
        supplied = self.headers.get("X-Ops-Token")
        return bool(supplied and hmac.compare_digest(supplied.strip(), TOKEN))

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_system_status() -> dict[str, Any]:
    return {
        "timestamp": int(time.time()),
        "host": socket.gethostname(),
        "checks": [
            _check_command("docker", ["docker", "ps", "--format", "{{.Names}}"]),
            _check_compose(),
            _check_systemd("hermes", SYSTEMD_SERVICES["hermes"]),
            _check_systemd("codex-worker", SYSTEMD_SERVICES["codex-worker"]),
            _check_systemd("ops-api", SYSTEMD_SERVICES["ops-api"]),
            _check_systemd("futu-opend", SYSTEMD_SERVICES["futu-opend"]),
            _check_systemd("futu-proxy", SYSTEMD_SERVICES["futu-proxy"]),
            _check_socket("postgres", "127.0.0.1", int(os.getenv("POSTGRES_HOST_PORT", "55432"))),
            _check_socket("mcp", "127.0.0.1", int(os.getenv("MCP_HOST_PORT", "8000"))),
            _check_socket("futu-opend", "127.0.0.1", 11111),
            _check_socket("futu-proxy", "172.17.0.1", 11112),
        ],
    }


def build_recent_errors(lines: int = 160) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for name in ("hermes", "codex-worker", "ops-api", "futu-opend", "futu-proxy"):
        unit = SYSTEMD_SERVICES[name]
        result = _run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-p", "warning..alert"])
        text = _combine_output(result)
        entries.append(
            {
                "service": name,
                "ok": result.ok,
                "lines": _tail_nonempty_lines(text, limit=40),
            }
        )

    for name in ("mcp", "dingtalk-stream-bot", "command-api", "postgres"):
        try:
            result = _run(_compose_command(["logs", "--tail", str(lines), name]))
            text = _filter_error_lines(_combine_output(result))
            entries.append({"service": name, "ok": result.ok, "lines": _tail_nonempty_lines(text, limit=40)})
        except ValueError as exc:
            entries.append({"service": name, "ok": False, "lines": [str(exc)]})

    return {"entries": entries}


def get_service_logs(service: str, lines: int = 120) -> dict[str, Any]:
    normalized = _normalize_service(service)
    if normalized in SYSTEMD_SERVICES:
        unit = SYSTEMD_SERVICES[normalized]
        result = _run(["journalctl", "-u", unit, "-n", str(lines), "--no-pager"])
        return {
            "service": normalized,
            "kind": "systemd",
            "ok": result.ok,
            "logs": _tail_nonempty_lines(_combine_output(result), limit=lines),
        }

    if normalized in COMPOSE_SERVICES:
        result = _run(_compose_command(["logs", "--tail", str(lines), COMPOSE_SERVICES[normalized]]))
        return {
            "service": normalized,
            "kind": "docker-compose",
            "ok": result.ok,
            "logs": _tail_nonempty_lines(_combine_output(result), limit=lines),
        }

    raise ValueError(f"unsupported service: {service}")


def build_coding_status() -> dict[str, Any]:
    worker_status = _check_systemd("codex-worker", SYSTEMD_SERVICES["codex-worker"])
    logs = get_service_logs("codex-worker", lines=80)
    return {
        "worker": worker_status,
        "recent_logs": logs.get("logs", [])[-30:],
    }


def _check_command(name: str, command: list[str]) -> dict[str, Any]:
    result = _run(command)
    if result.ok:
        return {"name": name, "ok": True, "message": _first_line(result.stdout) or "ok"}
    return {"name": name, "ok": False, "message": _first_line(result.stderr or result.stdout) or "failed"}


def _check_compose() -> dict[str, Any]:
    try:
        command = _compose_command(["ps", "--format", "json"])
    except ValueError as exc:
        return {"name": "docker_compose", "ok": False, "message": str(exc)}
    return _check_command("docker_compose", command)


def _check_systemd(name: str, unit: str) -> dict[str, Any]:
    result = _run(["systemctl", "is-active", unit])
    active = result.stdout.strip()
    return {
        "name": name,
        "ok": active == "active",
        "message": active or _first_line(result.stderr) or "unknown",
        "unit": unit,
    }


def _check_socket(name: str, host: str, port: int) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=2):
            pass
    except Exception as exc:
        return {"name": name, "ok": False, "message": f"{host}:{port} unavailable: {exc}"}
    return {"name": name, "ok": True, "message": f"{host}:{port} reachable"}


def _compose_command(args: list[str]) -> list[str]:
    if not COMPOSE_FILE.exists():
        raise ValueError(f"compose file not found: {COMPOSE_FILE}")
    return ["docker", "compose", "-f", str(COMPOSE_FILE), *args]


def _run(command: list[str]) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=str(APP_DIR) if APP_DIR.exists() else None,
            text=True,
            capture_output=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(
            ok=False,
            command=command,
            stdout=sanitize_text(stdout),
            stderr=sanitize_text(stderr or f"command timed out after {COMMAND_TIMEOUT_SECONDS}s"),
            returncode=124,
        )
    except Exception as exc:
        return CommandResult(ok=False, command=command, stdout="", stderr=sanitize_text(str(exc)), returncode=1)

    return CommandResult(
        ok=completed.returncode == 0,
        command=command,
        stdout=sanitize_text(completed.stdout or ""),
        stderr=sanitize_text(completed.stderr or ""),
        returncode=completed.returncode,
    )


def sanitize_text(text: str) -> str:
    sanitized = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _normalize_service(service: str) -> str:
    value = service.strip().lower().replace("_", "-")
    return SERVICE_ALIASES.get(value, value)


def _combine_output(result: CommandResult) -> str:
    if result.stderr:
        return result.stdout + ("\n" if result.stdout else "") + result.stderr
    return result.stdout


def _first_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _tail_nonempty_lines(text: str, limit: int) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def _filter_error_lines(text: str) -> str:
    keywords = ("error", "failed", "traceback", "exception", "fatal", "panic", "失败", "错误", "异常")
    lines = [line for line in text.splitlines() if any(keyword in line.lower() for keyword in keywords)]
    return "\n".join(lines)


def _first_query(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _int_query(query: dict[str, list[str]], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = _first_query(query, key)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def main() -> None:
    if not TOKEN:
        raise SystemExit("OPS_API_TOKEN or COMMAND_API_TOKEN is required")
    server = ThreadingHTTPServer((HOST, PORT), OpsRequestHandler)
    print(f"InvestmentKnowledge Ops API listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
