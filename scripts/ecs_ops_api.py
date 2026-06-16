#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
import fcntl
import hmac
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time


APP_ROOT = Path(os.getenv("INVESTMENT_APP_ROOT", "/opt/investment-knowledge"))
APP_DIR = Path(os.getenv("INVESTMENT_DIR", str(APP_ROOT / "current")))
REPO_DIR = Path(os.getenv("OPS_DEPLOY_REPO_DIR", "/opt/investment-knowledge-repo"))
COMPOSE_FILE = APP_DIR / "docker-compose.prod.yml"
COMPOSE_PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "turenagenttool_prod")
COMPOSE_ENV_FILE = Path(os.getenv("COMPOSE_ENV_FILE", str(APP_ROOT / ".env")))
HOST = os.getenv("OPS_API_HOST", "127.0.0.1")
PORT = int(os.getenv("OPS_API_PORT", "8767"))
TOKEN = os.getenv("OPS_API_TOKEN") or os.getenv("COMMAND_API_TOKEN") or ""
MAX_LOG_LINES = 400
COMMAND_TIMEOUT_SECONDS = float(os.getenv("OPS_API_COMMAND_TIMEOUT_SECONDS", "8"))
DEPLOY_TIMEOUT_SECONDS = float(os.getenv("OPS_API_DEPLOY_TIMEOUT_SECONDS", "600"))
DEPLOY_LOCK_PATH = Path(os.getenv("OPS_DEPLOY_LOCK_PATH", "/tmp/investment-knowledge-deploy.lock"))
PYTHON_BIN = os.getenv("OPS_API_PYTHON_BIN") or sys.executable
ALLOWED_NAMED_REFS = {
    ref.strip()
    for ref in os.getenv("OPS_DEPLOY_ALLOWED_REFS", "main").split(",")
    if ref.strip()
}
DEPLOY_MUTEX = threading.Lock()


COMPOSE_SERVICES = {
    "mcp": "mcp",
    "command-api": "command-api",
    "weekly-review-web": "weekly-review-web",
    "dingtalk-stream-bot": "dingtalk-stream-bot",
    "account-snapshot-scheduler": "account-snapshot-scheduler",
    "ipo-reminder-scheduler": "ipo-reminder-scheduler",
    "postgres": "postgres",
}

SYSTEMD_SERVICES = {
    "codex-worker": "investment-codex-worker.service",
    "research-agent-worker": "investment-research-agent-worker.service",
    "futu-opend": "futu-opend.service",
    "futu-proxy": "futu-opend-proxy.service",
    "ops-api": "investment-ops-api.service",
}

SERVICE_ALIASES = {
    "worker": "codex-worker",
    "codex_worker": "codex-worker",
    "codex": "codex-worker",
    "research-worker": "research-agent-worker",
    "research_agent": "research-agent-worker",
    "research": "research-agent-worker",
    "dingtalk": "dingtalk-stream-bot",
    "stream": "dingtalk-stream-bot",
    "account-snapshot": "account-snapshot-scheduler",
    "snapshot": "account-snapshot-scheduler",
    "snapshot-scheduler": "account-snapshot-scheduler",
    "ipo-reminder": "ipo-reminder-scheduler",
    "ipo-reminders": "ipo-reminder-scheduler",
    "ipo-scheduler": "ipo-reminder-scheduler",
    "weekly-review": "weekly-review-web",
    "weekly_review": "weekly-review-web",
    "weekly-review-web": "weekly-review-web",
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


class DeploymentBusy(RuntimeError):
    pass


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
            elif parsed.path == "/ops/deploy-status":
                event_id = _required_int_query(query, "id", minimum=1, maximum=10**12)
                event = read_deploy_event(event_id)
                if event is None:
                    self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "deploy_event_not_found"})
                else:
                    self._write_json(HTTPStatus.OK, {"ok": True, "data": event})
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except ValueError as exc:
            self._write_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._write_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": sanitize_text(str(exc))})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if not self._authorized():
            self._write_json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return

        try:
            payload = self._read_json_body()
            if parsed.path == "/ops/service-action":
                service = str(payload.get("service") or "")
                action = str(payload.get("action") or "")
                self._write_json(HTTPStatus.OK, {"ok": True, "data": control_service(service=service, action=action)})
            elif parsed.path == "/ops/deploy":
                self._write_json(HTTPStatus.ACCEPTED, {"ok": True, "data": deploy_ref(payload)})
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except DeploymentBusy as exc:
            self._write_json(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc), "data": {"status": "busy"}})
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

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload


def build_system_status() -> dict[str, Any]:
    return {
        "timestamp": int(time.time()),
        "host": socket.gethostname(),
        "checks": [
            _check_command("docker", ["docker", "ps", "--format", "{{.Names}}"]),
            _check_compose(),
            _check_systemd("codex-worker", SYSTEMD_SERVICES["codex-worker"]),
            _check_systemd("research-agent-worker", SYSTEMD_SERVICES["research-agent-worker"]),
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
    for name in ("codex-worker", "research-agent-worker", "ops-api", "futu-opend", "futu-proxy"):
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

    for name in (
        "mcp",
        "dingtalk-stream-bot",
        "account-snapshot-scheduler",
        "ipo-reminder-scheduler",
        "command-api",
        "postgres",
    ):
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


def control_service(service: str, action: str) -> dict[str, Any]:
    normalized = _normalize_service(service)
    normalized_action = action.strip().lower().replace("_", "-")
    if normalized not in SYSTEMD_SERVICES:
        raise ValueError(f"unsupported systemd service: {service}")
    if normalized_action not in {"start", "stop", "restart", "status"}:
        raise ValueError(f"unsupported service action: {action}")

    unit = SYSTEMD_SERVICES[normalized]
    if normalized_action == "status":
        result = _run(["systemctl", "is-active", unit])
    else:
        result = _run(["systemctl", normalized_action, unit])
    status = _check_systemd(normalized, unit)
    return {
        "service": normalized,
        "unit": unit,
        "action": normalized_action,
        "ok": result.ok if normalized_action != "status" else status["ok"],
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": status,
    }


def deploy_ref(payload: dict[str, Any]) -> dict[str, Any]:
    ref = _validate_deploy_ref(str(payload.get("ref") or ""))
    mode = _validate_deploy_mode(str(payload.get("mode") or "quick"))
    source = _safe_label(str(payload.get("source") or "codex_app"), default="codex_app")
    requested_by = _safe_label(str(payload.get("requested_by") or "codex"), default="codex")

    if not REPO_DIR.exists() or not (REPO_DIR / ".git").exists():
        raise ValueError(f"deploy repo is not initialized: {REPO_DIR}")
    if not (REPO_DIR / "scripts" / "deploy_from_local_checkout.sh").exists():
        raise ValueError(f"deploy script not found in repo: {REPO_DIR}")

    if not DEPLOY_MUTEX.acquire(blocking=False):
        raise DeploymentBusy("deployment is already running")

    branch_name = ref if ref in ALLOWED_NAMED_REFS else ""
    metadata: dict[str, Any] = {
        "requested_ref": ref,
        "requested_by": requested_by,
        "repo_dir": str(REPO_DIR),
        "app_root": str(APP_ROOT),
        "app_dir": str(APP_DIR),
        "async": True,
    }
    try:
        event_id = _record_deploy_start(
            source=source,
            mode=mode,
            commit_sha=ref if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref) else "",
            branch_name=branch_name,
            metadata=metadata,
        )
        thread = threading.Thread(
            target=_deploy_ref_background,
            kwargs={
                "event_id": event_id,
                "ref": ref,
                "mode": mode,
                "source": source,
                "requested_by": requested_by,
                "metadata": metadata,
            },
            daemon=True,
        )
        thread.start()
    except Exception:
        DEPLOY_MUTEX.release()
        raise

    return {
        "deploy_event_id": int(event_id),
        "ref": ref,
        "commit_sha": ref if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref) else "",
        "mode": mode,
        "status": "started",
        "summary": "deployment started",
        "status_url": f"/ops/deploy-status?id={event_id}",
    }


def _deploy_ref_background(
    event_id: str,
    ref: str,
    mode: str,
    source: str,
    requested_by: str,
    metadata: dict[str, Any],
) -> None:
    try:
        DEPLOY_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DEPLOY_LOCK_PATH.open("w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            lock_file.write(f"{time.time()} {ref} {mode} {source} {requested_by} event={event_id}\n")
            lock_file.flush()
            _run_deploy_with_event(event_id=event_id, ref=ref, mode=mode, requested_by=requested_by, metadata=metadata)
    except Exception as exc:
        print(f"deploy background failed for event {event_id}: {sanitize_text(str(exc))}", flush=True)
    finally:
        DEPLOY_MUTEX.release()


def _run_deploy_with_event(
    event_id: str,
    ref: str,
    mode: str,
    requested_by: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = time.monotonic()
    commit_sha = ""
    logs_tail = ""
    warnings: list[str] = []
    metadata = dict(metadata or {})
    metadata.update(
        {
            "requested_ref": ref,
            "requested_by": requested_by,
            "repo_dir": str(REPO_DIR),
            "app_root": str(APP_ROOT),
            "app_dir": str(APP_DIR),
        }
    )

    try:
        _ensure_clean_repo()
        fetch = _run_git(["fetch", "--prune", "origin"], timeout=DEPLOY_TIMEOUT_SECONDS)
        if not fetch.ok:
            raise RuntimeError(f"git fetch failed: {_summarize_command_error(fetch.stderr or fetch.stdout)}")

        checkout_target = f"origin/{ref}" if ref in ALLOWED_NAMED_REFS else ref
        checkout = _run_git(["checkout", "--detach", checkout_target], timeout=DEPLOY_TIMEOUT_SECONDS)
        if not checkout.ok:
            raise RuntimeError(f"git checkout failed: {_summarize_command_error(checkout.stderr or checkout.stdout)}")

        commit_result = _run_git(["rev-parse", "HEAD"])
        if not commit_result.ok:
            raise RuntimeError(f"git rev-parse failed: {_summarize_command_error(commit_result.stderr or commit_result.stdout)}")
        commit_sha = commit_result.stdout.strip()
        metadata["resolved_commit_sha"] = commit_sha

        env = {
            **os.environ,
            "SOURCE_DIR": str(REPO_DIR),
            "APP_ROOT": str(APP_ROOT),
            "APP_DIR": str(APP_DIR),
            "RELEASES_DIR": str(APP_ROOT / "releases"),
            "COMPOSE_PROJECT_NAME": COMPOSE_PROJECT_NAME,
            "COMPOSE_ENV_FILE": str(COMPOSE_ENV_FILE),
            "BUILD_IMAGE": "true" if mode == "full" else "false",
            "DEPLOY_EVENT_ID": event_id,
        }
        deploy = _run(
            ["bash", str(REPO_DIR / "scripts" / "deploy_from_local_checkout.sh")],
            cwd=REPO_DIR,
            env=env,
            timeout=DEPLOY_TIMEOUT_SECONDS,
        )
        logs_tail = _tail_text(_combine_output(deploy), limit=80)
        if not deploy.ok:
            raise RuntimeError(f"deploy script failed: {_summarize_command_error(deploy.stderr or deploy.stdout)}")

        health = build_deploy_health()
        metadata["health"] = health
        if warnings:
            metadata["warnings"] = warnings
        duration_seconds = round(time.monotonic() - started_at, 3)
        if not health.get("ok"):
            failed_checks = ", ".join(str(item.get("name")) for item in health.get("checks", []) if not item.get("ok"))
            summary = f"deploy health check failed: {failed_checks or 'unknown'}"
            finish_warning = _try_record_deploy_finish(event_id, "failed", summary, logs_tail, metadata)
            if finish_warning:
                warnings.append(finish_warning)
            return {
                "deploy_event_id": int(event_id),
                "ref": ref,
                "commit_sha": commit_sha,
                "mode": mode,
                "status": "failed",
                "duration_seconds": duration_seconds,
                "summary": summary,
                "health": health,
                "warnings": warnings,
            }

        summary = f"{mode} deploy completed"
        finish_warning = _try_record_deploy_finish(event_id, "succeeded", summary, logs_tail, metadata)
        if finish_warning:
            warnings.append(finish_warning)
        return {
            "deploy_event_id": int(event_id),
            "ref": ref,
            "commit_sha": commit_sha,
            "mode": mode,
            "status": "succeeded",
            "duration_seconds": duration_seconds,
            "summary": summary,
            "health": health,
            "warnings": warnings,
        }
    except Exception as exc:
        summary = sanitize_text(str(exc))
        metadata["error"] = summary
        if warnings:
            metadata["warnings"] = warnings
        finish_warning = _try_record_deploy_finish(event_id, "failed", summary, logs_tail, metadata)
        if finish_warning:
            summary = f"{summary}; {finish_warning}"
        raise RuntimeError(summary) from exc


def build_deploy_health() -> dict[str, Any]:
    checks = [
        _check_required_file("schema", APP_DIR / "db" / "schema.sql"),
        _check_required_file("compose_file", COMPOSE_FILE),
        _check_compose(),
        _check_socket("postgres", "127.0.0.1", int(os.getenv("POSTGRES_HOST_PORT", "55432"))),
        _check_socket("mcp", "127.0.0.1", int(os.getenv("MCP_HOST_PORT", "8000"))),
        _check_socket("weekly-review-web", "127.0.0.1", int(os.getenv("WEEKLY_REVIEW_WEB_HOST_PORT", "8010"))),
    ]
    for service in ("weekly-review-web", "dingtalk-stream-bot", "account-snapshot-scheduler", "ipo-reminder-scheduler"):
        checks.append(_check_compose_service_running(service))
    return {
        "ok": all(bool(check.get("ok")) for check in checks),
        "checks": checks,
    }


def read_deploy_event(event_id: int) -> dict[str, Any] | None:
    result = _run(
        [
            PYTHON_BIN,
            str(_script_path("get_deploy_event.py")),
            str(event_id),
        ],
        cwd=APP_DIR,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if not result.ok:
        raise RuntimeError(f"read deploy event failed: {_summarize_command_error(_combine_output(result))}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"read deploy event returned invalid JSON: {_summarize_command_error(result.stdout)}") from exc
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RuntimeError("read deploy event returned a non-object JSON payload")
    return value


def _check_compose_service_running(service: str) -> dict[str, Any]:
    result = _run(_compose_command(["ps", "--status", "running", "--services", service]))
    if not result.ok:
        return {"name": service, "ok": False, "message": _first_line(result.stderr or result.stdout) or "failed"}
    running = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if service in running:
        return {"name": service, "ok": True, "message": "running"}
    return {"name": service, "ok": False, "message": "not running"}


def _record_deploy_start(
    source: str,
    mode: str,
    commit_sha: str,
    branch_name: str,
    metadata: dict[str, Any],
) -> str:
    result = _run(
        [
            PYTHON_BIN,
            str(_script_path("record_deploy_event.py")),
            "start",
            "--source",
            source,
            "--deploy-mode",
            mode,
            "--commit-sha",
            commit_sha,
            "--branch-name",
            branch_name,
            "--summary",
            "cloud pull deploy started",
            "--metadata-json",
            json.dumps(metadata, ensure_ascii=False),
        ],
        cwd=APP_DIR,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if not result.ok:
        raise RuntimeError(f"record deploy start failed: {_summarize_command_error(_combine_output(result))}")
    event_id = result.stdout.strip().splitlines()[-1].strip()
    if not event_id.isdigit():
        raise RuntimeError(f"record deploy start returned invalid id: {event_id}")
    return event_id


def _record_deploy_finish(
    event_id: str,
    status: str,
    summary: str,
    logs_tail: str,
    metadata: dict[str, Any],
) -> None:
    result = _run(
        [
            PYTHON_BIN,
            str(_script_path("record_deploy_event.py")),
            "finish",
            "--id",
            event_id,
            "--status",
            status,
            "--summary",
            summary,
            "--logs-tail",
            logs_tail,
            "--metadata-json",
            json.dumps(metadata, ensure_ascii=False),
        ],
        cwd=APP_DIR,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if not result.ok:
        raise RuntimeError(f"record deploy finish failed: {_summarize_command_error(_combine_output(result))}")


def _try_record_deploy_finish(
    event_id: str,
    status: str,
    summary: str,
    logs_tail: str,
    metadata: dict[str, Any],
) -> str | None:
    try:
        _record_deploy_finish(event_id, status, summary, logs_tail, metadata)
    except Exception as exc:
        return f"deploy event finish recording failed: {sanitize_text(str(exc))}"
    return None


def _ensure_clean_repo() -> None:
    status = _run_git(["status", "--porcelain"])
    if not status.ok:
        raise RuntimeError(f"git status failed: {_first_line(status.stderr or status.stdout) or 'unknown error'}")
    if status.stdout.strip():
        raise RuntimeError("deploy repo has local changes; refusing to deploy")


def _run_git(args: list[str], timeout: float | None = None) -> CommandResult:
    return _run(["git", "-C", str(REPO_DIR), *args], timeout=timeout)


def _validate_deploy_ref(ref: str) -> str:
    value = ref.strip()
    if not value:
        raise ValueError("ref is required")
    if value in ALLOWED_NAMED_REFS:
        return value
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", value):
        return value
    raise ValueError("ref must be a commit SHA or an allowed named ref")


def _validate_deploy_mode(mode: str) -> str:
    value = mode.strip().lower()
    if value not in {"quick", "full"}:
        raise ValueError("mode must be quick or full")
    return value


def _safe_label(value: str, default: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return default
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", cleaned):
        return default
    return cleaned


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

    result = _run(command)
    if not result.ok:
        return {"name": "docker_compose", "ok": False, "message": _first_line(result.stderr or result.stdout) or "failed"}

    summary = _summarize_compose_ps(result.stdout)
    return {"name": "docker_compose", "ok": True, "message": summary or "ok"}


def _summarize_compose_ps(output: str) -> str:
    services: list[dict[str, Any]] = []
    for line in _tail_nonempty_lines(output, limit=200):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            services.extend(item for item in value if isinstance(item, dict))
        elif isinstance(value, dict):
            services.append(value)

    if not services:
        return _first_line(output) or "ok"

    running: list[str] = []
    not_running: list[str] = []
    for item in services:
        name = str(item.get("Service") or item.get("Name") or item.get("Names") or "-")
        state = str(item.get("State") or "").lower()
        status = str(item.get("Status") or "")
        if state == "running" or status.startswith("Up"):
            running.append(name)
        else:
            not_running.append(f"{name}={state or status or 'unknown'}")

    parts: list[str] = []
    if running:
        parts.append("running: " + ", ".join(sorted(running)))
    if not_running:
        parts.append("not running: " + ", ".join(sorted(not_running)))
    return "; ".join(parts)


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


def _check_required_file(name: str, path: Path) -> dict[str, Any]:
    if path.is_file():
        return {"name": name, "ok": True, "message": str(path)}
    return {"name": name, "ok": False, "message": f"missing: {path}"}


def _compose_command(args: list[str]) -> list[str]:
    if not COMPOSE_FILE.exists():
        raise ValueError(f"compose file not found: {COMPOSE_FILE}")
    command = ["docker", "compose", "--project-name", COMPOSE_PROJECT_NAME]
    if COMPOSE_ENV_FILE.is_file():
        command.extend(["--env-file", str(COMPOSE_ENV_FILE)])
    command.extend(["-f", str(COMPOSE_FILE), *args])
    return command


def _script_path(name: str) -> Path:
    app_path = APP_DIR / "scripts" / name
    if app_path.is_file():
        return app_path
    repo_path = REPO_DIR / "scripts" / name
    if repo_path.is_file():
        return repo_path
    return app_path


def _run(
    command: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> CommandResult:
    command_timeout = timeout if timeout is not None else COMMAND_TIMEOUT_SECONDS
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd or APP_DIR) if (cwd or APP_DIR).exists() else None,
            env=env,
            text=True,
            capture_output=True,
            timeout=command_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return CommandResult(
            ok=False,
            command=command,
            stdout=sanitize_text(stdout),
            stderr=sanitize_text(stderr or f"command timed out after {command_timeout}s"),
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


def _summarize_command_error(text: str) -> str:
    lines = [line.strip() for line in sanitize_text(text).splitlines() if line.strip()]
    if not lines:
        return "unknown error"

    for line in reversed(lines):
        lower = line.lower()
        if (
            lower.startswith(("error:", "fatal:", "exception:", "runtimeerror:", "valueerror:"))
            or "no such file or directory" in lower
            or "connection refused" in lower
            or "could not" in lower
        ):
            return line
    return lines[-1]


def _tail_nonempty_lines(text: str, limit: int) -> list[str]:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    return lines[-limit:]


def _tail_text(text: str, limit: int) -> str:
    return "\n".join(_tail_nonempty_lines(sanitize_text(text), limit=limit))


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


def _required_int_query(query: dict[str, list[str]], key: str, minimum: int, maximum: int) -> int:
    raw = _first_query(query, key)
    if raw is None:
        raise ValueError(f"{key} is required")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc
    return max(minimum, min(value, maximum))


def main() -> None:
    if not TOKEN:
        raise SystemExit("OPS_API_TOKEN or COMMAND_API_TOKEN is required")
    server = ThreadingHTTPServer((HOST, PORT), OpsRequestHandler)
    print(f"InvestmentKnowledge Ops API listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
