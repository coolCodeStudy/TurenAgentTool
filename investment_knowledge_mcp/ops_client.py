from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from investment_knowledge_mcp.config import AppConfig, get_config


_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_DEPLOY_REF = re.compile(r"[0-9a-fA-F]{40}")
_DEPLOY_TARGET = re.compile(r"[a-z0-9][a-z0-9_-]{0,62}")
_FEATURE_ROUTE = re.compile(r"/(?:[A-Za-z0-9._~-]+(?:/[A-Za-z0-9._~-]+)*)?")
_DEPLOY_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}")
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(?:password|passwd|token|api[_-]?key|secret|credential|authorization)\s*=\s*\S+"
)
_SENSITIVE_KEY = re.compile(
    r"(?i)(?:password|passwd|token|api[_-]?key|secret|credential|authorization|private[_-]?key)"
)
_AUTHENTICATED_URI = re.compile(
    r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s@]+@[^\s]+"
)
_CREDENTIAL_SHAPE = re.compile(
    r"(?i)(?:\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{8,}\b|"
    r"\bsk-[A-Za-z0-9_-]{8,}\b|\bAKIA[A-Z0-9]{16}\b|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b)"
)
_ALLOWED_DEPLOY_SOURCES = frozenset(
    {"direct", "github_actions", "ops_client", "mcp", "codex_app", "verification"}
)
_DEPLOY_MODE_ALIASES = {
    "quick": "targeted_quick",
    "targeted_quick": "targeted_quick",
    "config_restart": "config_restart",
    "no_deploy": "no_deploy",
}


class OpsClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: str = "ops_client_error",
        data: dict[str, Any] | None = None,
        next_action: str | None = None,
    ) -> None:
        sanitized_message = _sanitize_text(message) or "Ops API request failed"
        super().__init__(sanitized_message)
        self.http_status = http_status
        self.error_code = error_code if _ERROR_CODE.fullmatch(error_code) else "ops_client_error"
        self.message = sanitized_message
        self.data = _sanitize_json_value(data) if isinstance(data, dict) else None
        self.next_action = _sanitize_text(next_action) if next_action else None

    def as_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": False,
            "error": self.error_code,
            "message": self.message,
        }
        if self.http_status is not None:
            payload["http_status"] = self.http_status
        if self.data is not None:
            payload["data"] = self.data
        if self.next_action:
            payload["next_action"] = self.next_action
        return payload


@dataclass(frozen=True)
class OpsClient:
    base_url: str
    token: str
    timeout: float = 8.0

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        url = f"{self.base_url.rstrip('/')}{path}{query}"
        request = Request(url, headers={"Authorization": f"Bearer {self.token}"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _http_error(exc) from exc
        except (URLError, TimeoutError) as exc:
            raise _transport_error(exc) from exc
        except json.JSONDecodeError as exc:
            raise _invalid_response_error() from exc

        return _response_data(payload)

    def post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise _http_error(exc) from exc
        except (URLError, TimeoutError) as exc:
            raise _transport_error(exc) from exc
        except json.JSONDecodeError as exc:
            raise _invalid_response_error() from exc

        return _response_data(response_payload)


def _http_error(exc: HTTPError) -> OpsClientError:
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if isinstance(payload, dict):
        return _error_from_payload(payload, http_status=exc.code)
    return OpsClientError(
        f"Ops API request failed with HTTP {exc.code}",
        http_status=exc.code,
        error_code="ops_api_http_error",
        next_action="Inspect the controlled Ops API and retry through the same deployment channel.",
    )


def _transport_error(exc: BaseException) -> OpsClientError:
    return OpsClientError(
        "Ops API request could not be completed",
        error_code="ops_api_unreachable",
        data={"exception_type": type(exc).__name__},
        next_action=(
            "Verify the host or container Ops API URL, private tunnel, and internal Ops credentials "
            "before retrying through the same channel."
        ),
    )


def _invalid_response_error() -> OpsClientError:
    return OpsClientError(
        "Ops API returned an invalid JSON response",
        error_code="ops_api_invalid_response",
        next_action="Repair the Ops API response contract before retrying the deployment.",
    )


def _response_data(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _invalid_response_error()
    if not payload.get("ok"):
        raise _error_from_payload(payload)
    data = payload.get("data")
    return data if isinstance(data, dict) else {"value": data}


def _error_from_payload(payload: dict[str, Any], http_status: int | None = None) -> OpsClientError:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    error_code = str(payload.get("error") or "ops_api_error")
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        message = "Ops API request failed"
    next_action = payload.get("next_action")
    if not isinstance(next_action, str) and data is not None:
        handoff = data.get("return_to_coordinator")
        if isinstance(handoff, dict) and isinstance(handoff.get("action"), str):
            next_action = handoff["action"]
    return OpsClientError(
        message,
        http_status=http_status,
        error_code=error_code,
        data=data,
        next_action=next_action if isinstance(next_action, str) else None,
    )


def _sanitize_text(value: object) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = _AUTHENTICATED_URI.sub("[redacted-uri]", text)
    text = _SENSITIVE_ASSIGNMENT.sub("[redacted-credential]", text)
    text = _CREDENTIAL_SHAPE.sub("[redacted-credential]", text)
    return text[:1000]


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, list):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted-credential]"
                if _SENSITIVE_KEY.search(str(key))
                else _sanitize_json_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return _sanitize_text(value)


def get_ops_client(config: AppConfig | None = None) -> OpsClient:
    config = config or get_config()
    if not config.ops_api_url:
        raise OpsClientError(
            "Ops API URL is not configured",
            error_code="ops_api_not_configured",
            next_action=(
                "Configure OPS_API_URL for host callers or MCP_OPS_API_URL for Compose callers."
            ),
        )
    if not config.ops_api_token:
        raise OpsClientError(
            "Internal Ops API credentials are not configured",
            error_code="ops_api_credentials_missing",
            next_action="Configure the internal OPS_API_TOKEN without reusing a browser access token.",
        )
    return OpsClient(
        base_url=config.ops_api_url,
        token=config.ops_api_token,
        timeout=config.ops_api_timeout_seconds,
    )


def get_ops_deploy_client(config: AppConfig | None = None) -> OpsClient:
    config = config or get_config()
    if not config.ops_api_url:
        raise OpsClientError(
            "Ops API URL is not configured",
            error_code="ops_api_not_configured",
            next_action=(
                "Configure OPS_API_URL for host callers or MCP_OPS_API_URL for Compose callers."
            ),
        )
    if not config.ops_api_token:
        raise OpsClientError(
            "Internal Ops API credentials are not configured",
            error_code="ops_api_credentials_missing",
            next_action="Configure the internal OPS_API_TOKEN without reusing a browser access token.",
        )
    return OpsClient(
        base_url=config.ops_api_url,
        token=config.ops_api_token,
        timeout=config.ops_api_deploy_timeout_seconds,
    )


def fetch_cloud_system_status() -> dict[str, Any]:
    return get_ops_client().get("/ops/status")


def fetch_recent_errors(lines: int = 160) -> dict[str, Any]:
    return get_ops_client().get("/ops/recent-errors", {"lines": lines})


def fetch_service_logs(service: str, lines: int = 120) -> dict[str, Any]:
    return get_ops_client().get("/ops/logs", {"service": service, "lines": lines})


def fetch_coding_status() -> dict[str, Any]:
    return get_ops_client().get("/ops/coding-status")


def control_cloud_service(service: str, action: str) -> dict[str, Any]:
    return get_ops_client().post("/ops/service-action", {"service": service, "action": action})


def deploy_cloud_ref(
    ref: str,
    mode: str = "quick",
    source: str = "codex_app",
    requested_by: str = "codex",
    targets: Sequence[str] | None = None,
    feature_routes: Sequence[str] | None = None,
) -> dict[str, Any]:
    request = _validated_deploy_request(
        ref=ref,
        mode=mode,
        targets=targets,
        feature_routes=feature_routes,
        source=source,
        requested_by=requested_by,
    )
    return get_ops_deploy_client().post(
        "/ops/deploy",
        request,
    )


def _validated_deploy_request(
    *,
    ref: str,
    mode: str,
    targets: Sequence[str] | None,
    feature_routes: Sequence[str] | None,
    source: str,
    requested_by: str,
) -> dict[str, Any]:
    normalized_ref = ref.strip() if isinstance(ref, str) else ""
    if normalized_ref != "main" and _DEPLOY_REF.fullmatch(normalized_ref) is None:
        raise OpsClientError(
            "Production ref must be main or a 40-character commit SHA",
            error_code="source_policy_rejected",
            data={"field": "ref"},
            next_action=(
                "Integrate the commit into authoritative main, push main, and dispatch its current tip."
            ),
        )
    if normalized_ref != "main":
        normalized_ref = normalized_ref.lower()

    normalized_mode = mode.strip().lower() if isinstance(mode, str) else ""
    if normalized_mode in {"full", "full_image"}:
        raise OpsClientError(
            "Full-image deployment is not supported by the local or MCP client transport",
            error_code="full_image_requires_workflow",
            data={"field": "mode", "mode": "full_image"},
            next_action=(
                "Use the GitHub Actions deploy workflow so GitHub builds and transports the immutable "
                "SHA-bound image archive. An emergency reason alone is not sufficient."
            ),
        )
    canonical_mode = _DEPLOY_MODE_ALIASES.get(normalized_mode)
    if canonical_mode is None:
        raise _invalid_deploy_field(
            "mode",
            "Mode must be quick, targeted_quick, config_restart, or no_deploy",
        )

    normalized_targets = _validated_targets(targets)
    normalized_routes = _validated_routes(feature_routes)
    normalized_source = source.strip() if isinstance(source, str) else ""
    if normalized_source not in _ALLOWED_DEPLOY_SOURCES:
        raise _invalid_deploy_field(
            "source",
            "Source must name an approved deployment channel",
        )
    normalized_requester = requested_by.strip() if isinstance(requested_by, str) else ""
    if not _is_safe_deploy_label(normalized_requester):
        raise _invalid_deploy_field(
            "requested_by",
            "Requester must be a safe non-secret deployment label",
        )

    return {
        "ref": normalized_ref,
        "mode": canonical_mode,
        "targets": normalized_targets,
        "feature_routes": normalized_routes,
        "source": normalized_source,
        "requested_by": normalized_requester,
    }


def _validated_targets(targets: Sequence[str] | None) -> list[str]:
    if targets is None:
        return []
    if isinstance(targets, (str, bytes)) or not isinstance(targets, Sequence):
        raise _invalid_deploy_field("targets", "Targets must be a list of service names")
    normalized = []
    for target in targets:
        value = target.strip() if isinstance(target, str) else ""
        if _DEPLOY_TARGET.fullmatch(value) is None:
            raise _invalid_deploy_field("targets", "Targets must contain safe service names")
        normalized.append(value)
    return sorted(set(normalized))


def _validated_routes(feature_routes: Sequence[str] | None) -> list[str]:
    if feature_routes is None:
        return []
    if isinstance(feature_routes, (str, bytes)) or not isinstance(feature_routes, Sequence):
        raise _invalid_deploy_field(
            "feature_routes",
            "Feature routes must be a list of canonical local paths",
        )
    normalized: list[str] = []
    for route in feature_routes:
        if (
            not isinstance(route, str)
            or not 1 <= len(route) <= 256
            or _FEATURE_ROUTE.fullmatch(route) is None
            or _SENSITIVE_KEY.search(route) is not None
            or any(segment in {".", ".."} for segment in route.split("/")[1:])
        ):
            raise _invalid_deploy_field(
                "feature_routes",
                "Feature routes must be canonical ASCII local paths",
            )
        if route not in normalized:
            normalized.append(route)
    return normalized


def _is_safe_deploy_label(value: str) -> bool:
    return bool(
        _DEPLOY_LABEL.fullmatch(value)
        and _SENSITIVE_ASSIGNMENT.search(value) is None
        and _AUTHENTICATED_URI.search(value) is None
        and _CREDENTIAL_SHAPE.search(value) is None
    )


def _invalid_deploy_field(field: str, message: str) -> OpsClientError:
    return OpsClientError(
        message,
        error_code="deployment_request_invalid",
        data={"field": field},
        next_action="Correct the request locally before dispatching it to the Ops API.",
    )


def fetch_cloud_deploy_status(deploy_event_id: int) -> dict[str, Any]:
    return get_ops_client().get("/ops/deploy-status", {"id": deploy_event_id})


def render_cloud_deploy(
    ref: str,
    mode: str = "quick",
    source: str = "codex_app",
    requested_by: str = "codex",
    targets: Sequence[str] | None = None,
    feature_routes: Sequence[str] | None = None,
) -> str:
    data = deploy_cloud_ref(
        ref=ref,
        mode=mode,
        targets=targets,
        feature_routes=feature_routes,
        source=source,
        requested_by=requested_by,
    )

    lines = [
        "云端部署已完成：",
        f"- deploy_event：#{data.get('deploy_event_id') or '-'}",
        f"- ref：{data.get('ref') or ref}",
        f"- commit：{data.get('commit_sha') or '-'}",
        f"- mode：{data.get('mode') or mode}",
        f"- 状态：{data.get('status') or '-'}",
    ]
    summary = str(data.get("summary") or "").strip()
    if summary:
        lines.append(f"- 摘要：{summary}")
    status_url = str(data.get("status_url") or "").strip()
    if status_url:
        lines.append(f"- 状态证据：{status_url}")
    lines.append("")
    lines.append("请用该事件证据完成 Coordinator Return Gate；也可继续问 `cloud_deploy_status`。")
    return "\n".join(lines)


def render_cloud_deploy_status(deploy_event_id: int) -> str:
    try:
        data = fetch_cloud_deploy_status(deploy_event_id)
    except OpsClientError as exc:
        return f"云端部署状态暂不可用：{exc}"

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    health = metadata.get("health") if isinstance(metadata.get("health"), dict) else {}
    failed_checks: list[str] = []
    for check in health.get("checks") or []:
        if isinstance(check, dict) and not check.get("ok"):
            failed_checks.append(str(check.get("name") or "-"))

    lines = [
        f"云端部署状态：#{data.get('id') or deploy_event_id}",
        f"- mode：{data.get('deploy_mode') or '-'}",
        f"- 状态：{data.get('status') or '-'}",
        f"- commit：{data.get('commit_sha') or '-'}",
        f"- branch：{data.get('branch_name') or '-'}",
        f"- 耗时：{data.get('duration_seconds') or '-'}s",
    ]
    summary = str(data.get("summary") or "").strip()
    if summary:
        lines.append(f"- 摘要：{summary}")
    if health:
        lines.append(f"- 健康检查：{'OK' if health.get('ok') else 'FAIL'}")
    if failed_checks:
        lines.append("- 失败检查：" + "、".join(failed_checks))
    logs_tail = str(data.get("logs_tail") or "").strip()
    if logs_tail and data.get("status") == "failed":
        lines.append(f"- 日志尾部：{logs_tail[:500]}")
    return "\n".join(lines)


def render_cloud_service_control(service: str, action: str) -> str:
    try:
        data = control_cloud_service(service=service, action=action)
    except OpsClientError as exc:
        return f"{service} {action} 暂不可用：{exc}"

    status = data.get("status") if isinstance(data.get("status"), dict) else {}
    ok = bool(data.get("ok"))
    lines = [
        f"云端服务控制：{data.get('service') or service}",
        f"- 动作：{data.get('action') or action}",
        f"- 执行：{'OK' if ok else 'FAIL'}",
        f"- 当前状态：{status.get('message') or '-'}",
    ]
    stderr = str(data.get("stderr") or "").strip()
    if stderr:
        lines.append(f"- stderr：{stderr[:240]}")
    return "\n".join(lines)


def render_cloud_system_status() -> str:
    try:
        data = fetch_cloud_system_status()
    except OpsClientError as exc:
        return f"云端状态暂不可用：{exc}"

    lines = [
        "云端系统状态：",
        f"- 主机：{data.get('host') or '-'}",
    ]
    failed: list[str] = []
    for check in data.get("checks") or []:
        if not isinstance(check, dict):
            continue
        ok = bool(check.get("ok"))
        name = str(check.get("name") or "-")
        message = str(check.get("message") or "-")
        lines.append(f"- {'OK' if ok else 'FAIL'} {name}：{message}")
        if not ok:
            failed.append(name)

    lines.append("")
    if failed:
        lines.append("需要关注：" + "、".join(failed))
        lines.append("可继续问：`最近错误`、`worker日志`、`mcp日志`。")
    else:
        lines.append("核心链路看起来正常。")
    return "\n".join(lines)


def render_recent_errors(lines: int = 160) -> str:
    try:
        data = fetch_recent_errors(lines=lines)
    except OpsClientError as exc:
        return f"最近错误暂不可用：{exc}"

    output = ["最近云端错误："]
    any_error = False
    for entry in data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        service = str(entry.get("service") or "-")
        log_lines = [str(line) for line in (entry.get("lines") or []) if str(line).strip()]
        if not log_lines:
            continue
        any_error = True
        output.append("")
        output.append(f"[{service}]")
        output.extend(_truncate_lines(log_lines, max_lines=8, max_chars_per_line=220))

    if not any_error:
        output.append("- 没有抓到明显 warning/error 日志。")
    return "\n".join(output)


def render_service_logs(service: str, lines: int = 120) -> str:
    try:
        data = fetch_service_logs(service=service, lines=lines)
    except OpsClientError as exc:
        return f"{service} 日志暂不可用：{exc}"

    log_lines = [str(line) for line in (data.get("logs") or []) if str(line).strip()]
    title = f"{data.get('service') or service} 最近日志："
    if not log_lines:
        return f"{title}\n- 暂无日志。"
    rendered = _truncate_lines(log_lines, max_lines=30, max_chars_per_line=260)
    return "\n".join([title, *rendered])


def render_cloud_coding_status() -> str:
    try:
        data = fetch_coding_status()
    except OpsClientError as exc:
        return f"云端开发状态暂不可用：{exc}"

    worker = data.get("worker") if isinstance(data.get("worker"), dict) else {}
    lines = [
        "云端开发状态：",
        f"- Codex worker：{'OK' if worker.get('ok') else 'FAIL'} {worker.get('message') or '-'}",
    ]
    recent_logs = [str(line) for line in (data.get("recent_logs") or []) if str(line).strip()]
    if recent_logs:
        lines.append("")
        lines.append("最近 worker 日志：")
        lines.extend(_truncate_lines(recent_logs, max_lines=12, max_chars_per_line=240))
    return "\n".join(lines)


def _truncate_lines(lines: list[str], max_lines: int, max_chars_per_line: int) -> list[str]:
    clipped = lines[-max_lines:]
    rendered: list[str] = []
    for line in clipped:
        if len(line) > max_chars_per_line:
            rendered.append(line[:max_chars_per_line] + " ...")
        else:
            rendered.append(line)
    if len(lines) > max_lines:
        rendered.insert(0, f"... 已省略 {len(lines) - max_lines} 行")
    return rendered
