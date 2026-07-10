#!/usr/bin/env python3
from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from datetime import datetime
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

try:
    from scripts.deploy_contract import DeployMode
    from scripts.deploy_preflight import GIB, MIB, ResourceSnapshot, collect_resources
    from scripts.deploy_release import (
        DeployOutcome,
        DeployRequest,
        DeploymentEngine,
        DeploymentError,
        DockerHealthChecker,
        SystemClock,
    )
    from scripts.deploy_state import SourcePolicyError, load_state, resolve_production_target
    from scripts.deploy_support import CommandResult, SubprocessRunner
except ModuleNotFoundError:  # Direct execution through scripts/ecs_ops_api.py.
    from deploy_contract import DeployMode
    from deploy_preflight import GIB, MIB, ResourceSnapshot, collect_resources
    from deploy_release import (
        DeployOutcome,
        DeployRequest,
        DeploymentEngine,
        DeploymentError,
        DockerHealthChecker,
        SystemClock,
    )
    from deploy_state import SourcePolicyError, load_state, resolve_production_target
    from deploy_support import CommandResult, SubprocessRunner


APP_ROOT = Path(os.getenv("INVESTMENT_APP_ROOT", "/opt/investment-knowledge"))
APP_DIR = Path(os.getenv("INVESTMENT_DIR", str(APP_ROOT / "current")))
REPO_DIR = Path(os.getenv("OPS_DEPLOY_REPO_DIR", "/opt/investment-knowledge-repo"))
RELEASE_ROOT = Path(os.getenv("OPS_DEPLOY_RELEASE_ROOT", str(APP_ROOT / "releases")))
DEPLOY_STATE_PATH = Path(os.getenv("OPS_DEPLOY_STATE_PATH", str(APP_ROOT / "shared" / "deploy-state.json")))
DEPLOY_EVENTS_DIR = Path(os.getenv("OPS_DEPLOY_EVENTS_DIR", str(APP_ROOT / "shared" / "deploy-events")))
COMPOSE_FILE = APP_DIR / "docker-compose.prod.yml"
COMPOSE_PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "turenagenttool_prod")
COMPOSE_ENV_FILE = Path(os.getenv("COMPOSE_ENV_FILE", str(APP_ROOT / ".env")))
HOST = os.getenv("OPS_API_HOST", "127.0.0.1")
PORT = int(os.getenv("OPS_API_PORT", "8767"))
TOKEN = os.getenv("OPS_API_TOKEN") or os.getenv("COMMAND_API_TOKEN") or ""
MAX_LOG_LINES = 400
COMMAND_TIMEOUT_SECONDS = float(os.getenv("OPS_API_COMMAND_TIMEOUT_SECONDS", "8"))
DEPLOY_TIMEOUT_SECONDS = float(os.getenv("OPS_API_DEPLOY_TIMEOUT_SECONDS", "600"))
DEPLOY_LOCK_PATH = Path(os.getenv("OPS_DEPLOY_LOCK_PATH", str(APP_ROOT / "shared" / "deploy.lock")))
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
    (re.compile(r"(?i)SSL:\s*[A-Z0-9_:-]+"), "SSL:<redacted>"),
    (re.compile(r"(?i)certificate[_\s-]*verify[_\s-]*failed"), "certificate verification failed"),
]


class DeploymentBusy(RuntimeError):
    pass


class DeployApiError(ValueError):
    def __init__(self, status: HTTPStatus, error_code: str, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.data = data or {}


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
                raw_event_id = _first_query(query, "id")
                if raw_event_id is None:
                    self._write_json(HTTPStatus.OK, {"ok": True, "data": build_deploy_status()})
                else:
                    event_id = _required_int_query(query, "id", minimum=1, maximum=10**12)
                    event = read_deploy_event(event_id)
                    if event is None:
                        self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "deploy_event_not_found"})
                    else:
                        self._write_json(HTTPStatus.OK, {"ok": True, "data": event})
            elif parsed.path == "/deploy/status":
                self._write_json(HTTPStatus.OK, {"ok": True, "data": build_deploy_status()})
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except DeployApiError as exc:
            self._write_json(exc.status, _api_error_payload(exc))
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
            elif parsed.path in {"/ops/deploy", "/deploy"}:
                self._write_json(HTTPStatus.ACCEPTED, {"ok": True, "data": deploy_ref(payload)})
            else:
                self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except DeployApiError as exc:
            self._write_json(exc.status, _api_error_payload(exc))
        except DeploymentBusy as exc:
            error = DeployApiError(HTTPStatus.CONFLICT, "deployment_busy", str(exc), {"status": "busy"})
            self._write_json(error.status, _api_error_payload(error))
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
                "ok": _command_ok(result),
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
            entries.append({"service": name, "ok": _command_ok(result), "lines": _tail_nonempty_lines(text, limit=40)})
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
            "ok": _command_ok(result),
            "logs": _tail_nonempty_lines(_combine_output(result), limit=lines),
        }

    if normalized in COMPOSE_SERVICES:
        result = _run(_compose_command(["logs", "--tail", str(lines), COMPOSE_SERVICES[normalized]]))
        return {
            "service": normalized,
            "kind": "docker-compose",
            "ok": _command_ok(result),
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


def build_deploy_status() -> dict[str, Any]:
    state = load_state(DEPLOY_STATE_PATH)
    resources = collect_deploy_resources()
    return {
        "current_sha": state.current_sha,
        "previous_sha": state.previous_sha,
        "active_mode": state.last_mode,
        "requested_ref": state.requested_ref,
        "resolved_ref": state.resolved_ref,
        "targets": list(state.targets),
        "preflight": _sanitize_payload(state.preflight),
        "resources": _resource_payload(resources),
        "resource_thresholds": {
            "min_free_disk_bytes": 8 * GIB,
            "max_disk_used_percent": 80.0,
            "min_available_memory_bytes": 512 * MIB,
        },
        "last_outcome": _read_last_outcome(state.last_event_id, state.final_health),
    }


def collect_deploy_resources() -> ResourceSnapshot:
    return collect_resources(SubprocessRunner())


def _read_last_outcome(event_id: str | None, fallback_health: str | None) -> dict[str, Any]:
    if event_id:
        path = DEPLOY_EVENTS_DIR / f"{event_id}.json"
        try:
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                return _sanitize_payload(payload)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            pass
    return {"final_health": sanitize_text(fallback_health or "unknown")}


def _resource_payload(snapshot: ResourceSnapshot) -> dict[str, int | float]:
    return {
        "free_disk_bytes": snapshot.free_disk_bytes,
        "disk_used_percent": snapshot.disk_used_percent,
        "available_memory_bytes": snapshot.available_memory_bytes,
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
        "ok": _command_ok(result) if normalized_action != "status" else status["ok"],
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "status": status,
    }


def deploy_ref(payload: dict[str, Any]) -> dict[str, Any]:
    if not DEPLOY_MUTEX.acquire(blocking=False):
        raise DeployApiError(
            HTTPStatus.CONFLICT,
            "deployment_busy",
            "deployment is already running",
            {"status": "busy"},
        )

    try:
        ref = _validate_deploy_ref(str(payload.get("ref") or ""))
        mode = _validate_deploy_mode(str(payload.get("mode") or "targeted_quick"))
        targets = _validate_deploy_targets(payload.get("targets"))
        emergency_reason = _optional_text(payload.get("emergency_reason"))
        archive_path = _optional_path(
            payload.get("archive_path")
            or payload.get("archive")
            or payload.get("full_image_archive_path")
        )
        feature_routes = _validate_feature_routes(payload.get("feature_routes"))

        if (
            mode is DeployMode.FULL_IMAGE
            and archive_path is None
            and (emergency_reason is None or len(emergency_reason.strip()) < 20)
        ):
            raise DeployApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "deployment_rejected",
                "emergency reason must be at least 20 characters",
            )

        try:
            target_sha = _resolve_deploy_source_policy(ref)
        except DeployApiError:
            raise
        except ValueError as exc:
            raise DeployApiError(
                HTTPStatus.BAD_REQUEST,
                "source_policy_rejected",
                sanitize_text(str(exc)),
            ) from exc
        deploy_event_id = _new_deploy_event_id()
        request = DeployRequest(
            requested_ref=ref,
            requested_mode=mode,
            requested_targets=targets,
            archive_path=archive_path,
            emergency_reason=emergency_reason,
            feature_routes=feature_routes,
            external_event_id=str(deploy_event_id),
        )
        engine = build_deployment_engine()
        try:
            outcome = engine.deploy(request)
        except DeploymentError as exc:
            raise DeployApiError(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                "deployment_rejected",
                sanitize_text(str(exc)),
            ) from exc
        if not outcome.ok:
            status = (
                HTTPStatus.CONFLICT
                if _is_shared_lock_contention(outcome)
                else HTTPStatus.UNPROCESSABLE_ENTITY
            )
            error_code = (
                "deployment_busy"
                if status is HTTPStatus.CONFLICT
                else "deployment_rejected"
            )
            raise DeployApiError(
                status,
                error_code,
                outcome.message,
                {"outcome": _deploy_outcome_payload(outcome)},
            )
    except Exception:
        DEPLOY_MUTEX.release()
        raise
    DEPLOY_MUTEX.release()

    return {
        "deploy_event_id": deploy_event_id,
        "ref": ref,
        "commit_sha": outcome.target_sha or target_sha,
        "mode": outcome.mode.value,
        "targets": list(outcome.activated_services or targets),
        "status": "completed",
        "summary": sanitize_text(outcome.message),
        "status_url": f"/ops/deploy-status?id={deploy_event_id}",
        "aggregate_status_url": "/deploy/status",
        "outcome": _deploy_outcome_payload(outcome),
    }


def build_deployment_engine() -> DeploymentEngine:
    runner = SubprocessRunner()
    return DeploymentEngine(
        repo=REPO_DIR,
        app_root=APP_ROOT,
        runner=runner,
        health=DockerHealthChecker(
            runner,
            APP_DIR,
            compose_project_name=COMPOSE_PROJECT_NAME,
        ),
        clock=SystemClock(),
        compose_project_name=COMPOSE_PROJECT_NAME,
        env_file=COMPOSE_ENV_FILE,
    )


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
        if not _command_ok(fetch):
            raise RuntimeError(f"git fetch failed: {_summarize_command_error(fetch.stderr or fetch.stdout)}")

        checkout_target = f"origin/{ref}" if ref in ALLOWED_NAMED_REFS else ref
        checkout = _run_git(["checkout", "--detach", checkout_target], timeout=DEPLOY_TIMEOUT_SECONDS)
        if not _command_ok(checkout):
            raise RuntimeError(f"git checkout failed: {_summarize_command_error(checkout.stderr or checkout.stdout)}")

        commit_result = _run_git(["rev-parse", "HEAD"])
        if not _command_ok(commit_result):
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
        if not _command_ok(deploy):
            raise RuntimeError(f"deploy script failed: {_summarize_command_error(deploy.stderr or deploy.stdout)}")

        health = wait_for_deploy_health()
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


def wait_for_deploy_health(timeout_seconds: float = 90.0, stable_seconds: float = 12.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    first_healthy_at: float | None = None
    last_health = build_deploy_health()
    while time.monotonic() < deadline:
        last_health = build_deploy_health()
        if last_health.get("ok"):
            if first_healthy_at is None:
                first_healthy_at = time.monotonic()
            if time.monotonic() - first_healthy_at >= stable_seconds:
                last_health["stable_seconds"] = stable_seconds
                return last_health
        else:
            first_healthy_at = None
        time.sleep(3)
    last_health["stable_seconds"] = 0
    last_health["message"] = f"deploy health did not stay healthy for {stable_seconds:.0f}s"
    return last_health


def read_deploy_event(event_id: int) -> dict[str, Any] | None:
    shared_event = _read_shared_deploy_event(str(event_id))
    if shared_event is not None:
        return shared_event

    result = _run(
        [
            PYTHON_BIN,
            str(_script_path("get_deploy_event.py")),
            str(event_id),
        ],
        cwd=APP_DIR,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if not _command_ok(result):
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


def _read_shared_deploy_event(event_id: str) -> dict[str, Any] | None:
    if not event_id or Path(event_id).name != event_id:
        return None
    path = DEPLOY_EVENTS_DIR / f"{event_id}.json"
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return _shared_event_status_payload(payload, event_id)


def _shared_event_status_payload(payload: dict[str, Any], event_id: str) -> dict[str, Any]:
    final_health = str(payload.get("final_health") or "")
    status = "succeeded" if final_health == "healthy" else "failed"
    completed_at = str(payload.get("completed_at") or "")
    started_at = str(payload.get("started_at") or "")
    metadata = {
        "targets": payload.get("targets") if isinstance(payload.get("targets"), list) else [],
        "preflight": payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {},
        "final_health": final_health or "unknown",
        "rollback_status": str(payload.get("rollback_status") or ""),
    }
    return _sanitize_payload(
        {
            "id": int(event_id) if event_id.isdigit() else event_id,
            "deploy_mode": str(payload.get("requested_mode") or payload.get("computed_mode") or ""),
            "status": status,
            "commit_sha": str(payload.get("deployed_sha") or payload.get("target_sha") or ""),
            "branch_name": "",
            "duration_seconds": _duration_seconds(started_at, completed_at),
            "summary": f"shared deployment event {status}",
            "metadata": metadata,
            "logs_tail": "",
        }
    )


def _new_deploy_event_id() -> int:
    return time.time_ns() // 1_000_000


def _duration_seconds(started_at: str, completed_at: str) -> float | None:
    try:
        if not started_at or not completed_at:
            return None
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        completed = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((completed - started).total_seconds(), 3)


def _check_compose_service_running(service: str) -> dict[str, Any]:
    result = _run(_compose_command(["ps", "--status", "running", "--services", service]))
    if not _command_ok(result):
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
    if not _command_ok(result):
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
    if not _command_ok(result):
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
    if not _command_ok(status):
        raise RuntimeError(f"git status failed: {_first_line(status.stderr or status.stdout) or 'unknown error'}")
    if status.stdout.strip():
        raise RuntimeError("deploy repo has local changes; refusing to deploy")


def _run_git(args: list[str], timeout: float | None = None) -> CommandResult:
    return _run(["git", "-C", str(REPO_DIR), *args], timeout=timeout)


def _validate_deploy_ref(ref: str) -> str:
    value = ref.strip()
    if not value:
        raise DeployApiError(HTTPStatus.BAD_REQUEST, "source_policy_rejected", "ref is required")
    if value in ALLOWED_NAMED_REFS or re.fullmatch(r"[0-9a-fA-F]{40}", value):
        return value
    raise DeployApiError(
        HTTPStatus.BAD_REQUEST,
        "source_policy_rejected",
        "ref must be main or a 40-character commit SHA reachable from origin/main",
    )


def _validate_deploy_mode(mode: str) -> DeployMode:
    value = mode.strip().lower()
    aliases = {
        "quick": DeployMode.TARGETED_QUICK,
        "full": DeployMode.FULL_IMAGE,
    }
    if value in aliases:
        return aliases[value]
    try:
        return DeployMode(value)
    except ValueError as exc:
        raise DeployApiError(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "deployment_rejected",
            "mode must be no_deploy, targeted_quick, config_restart, or full_image",
        ) from exc


def _validate_deploy_targets(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise DeployApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "deployment_rejected", "targets must be a list of strings")
    targets = tuple(sorted({item.strip() for item in raw if item.strip()}))
    if len(targets) != len([item for item in raw if isinstance(item, str) and item.strip()]):
        return targets
    return targets


def _validate_feature_routes(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise DeployApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "deployment_rejected", "feature_routes must be a list of strings")
    routes = tuple(dict.fromkeys(item.strip() for item in raw if item.strip()))
    if any(not route.startswith("/") or route.startswith("//") for route in routes):
        raise DeployApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "deployment_rejected", "feature routes must be absolute local paths")
    return routes


def _optional_text(raw: object) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DeployApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "deployment_rejected", "emergency_reason must be a string")
    value = raw.strip()
    return value or None


def _optional_path(raw: object) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DeployApiError(HTTPStatus.UNPROCESSABLE_ENTITY, "deployment_rejected", "archive path must be a string")
    value = raw.strip()
    return Path(value) if value else None


def _resolve_deploy_source_policy(ref: str) -> str:
    try:
        return resolve_production_target(REPO_DIR, ref, SubprocessRunner())
    except SourcePolicyError as exc:
        raise DeployApiError(
            HTTPStatus.BAD_REQUEST,
            "source_policy_rejected",
            sanitize_text(str(exc)),
        ) from exc
    except Exception as exc:
        raise DeployApiError(
            HTTPStatus.BAD_REQUEST,
            "source_policy_rejected",
            sanitize_text(str(exc)),
        ) from exc


def _deploy_outcome_payload(outcome: DeployOutcome) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "ok": outcome.ok,
            "target_sha": outcome.target_sha,
            "mode": outcome.mode.value,
            "activated_services": list(outcome.activated_services),
            "rolled_back_services": list(outcome.rolled_back_services),
            "message": outcome.message,
            "manual_recovery": outcome.manual_recovery,
            "rollback_failures": list(outcome.rollback_failures),
            "archive_cleanup": outcome.archive_cleanup,
            "audit_status": outcome.audit_status,
            "image_count_after": outcome.image_count_after,
            "disk_used_after": outcome.disk_used_after,
            "cleanup_reclaimed_bytes": outcome.cleanup_reclaimed_bytes,
            "cleanup_status": outcome.cleanup_status,
        }
    )


def _is_shared_lock_contention(outcome: DeployOutcome) -> bool:
    message = outcome.message.lower()
    return (
        outcome.archive_cleanup == "deferred_lock_unavailable"
        or "deployment lock could not be acquired" in message
        or "another deployment is active" in message
        or "deployment is already running" in message
    )


def _api_error_payload(exc: DeployApiError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": exc.error_code,
        "message": sanitize_text(str(exc)),
    }
    if exc.data:
        payload["data"] = _sanitize_payload(exc.data)
    return payload


def _sanitize_payload(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
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
    if _command_ok(result):
        return {"name": name, "ok": True, "message": _first_line(result.stdout) or "ok"}
    return {"name": name, "ok": False, "message": _first_line(result.stderr or result.stdout) or "failed"}


def _check_compose() -> dict[str, Any]:
    try:
        command = _compose_command(["ps", "--format", "json"])
    except ValueError as exc:
        return {"name": "docker_compose", "ok": False, "message": str(exc)}

    result = _run(command)
    if not _command_ok(result):
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
            returncode=124,
            stdout=sanitize_text(stdout),
            stderr=sanitize_text(stderr or f"command timed out after {command_timeout}s"),
        )
    except Exception as exc:
        return CommandResult(returncode=1, stdout="", stderr=sanitize_text(str(exc)))

    return CommandResult(
        returncode=completed.returncode,
        stdout=sanitize_text(completed.stdout or ""),
        stderr=sanitize_text(completed.stderr or ""),
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


def _command_ok(result: CommandResult) -> bool:
    return result.returncode == 0


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
