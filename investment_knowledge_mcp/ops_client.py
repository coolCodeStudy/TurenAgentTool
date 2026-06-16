from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from investment_knowledge_mcp.config import AppConfig, get_config


class OpsClientError(RuntimeError):
    pass


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
            body = exc.read().decode("utf-8", errors="replace")
            raise OpsClientError(f"Ops API returned HTTP {exc.code}: {body}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OpsClientError(f"Ops API request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise OpsClientError("Ops API returned a non-object JSON payload")
        if not payload.get("ok"):
            raise OpsClientError(str(payload.get("error") or "Ops API request failed"))
        data = payload.get("data")
        return data if isinstance(data, dict) else {"value": data}

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
            error_body = exc.read().decode("utf-8", errors="replace")
            raise OpsClientError(f"Ops API returned HTTP {exc.code}: {error_body}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OpsClientError(f"Ops API request failed: {exc}") from exc

        if not isinstance(response_payload, dict):
            raise OpsClientError("Ops API returned a non-object JSON payload")
        if not response_payload.get("ok"):
            raise OpsClientError(str(response_payload.get("error") or "Ops API request failed"))
        data = response_payload.get("data")
        return data if isinstance(data, dict) else {"value": data}


def get_ops_client(config: AppConfig | None = None) -> OpsClient:
    config = config or get_config()
    if not config.ops_api_url:
        raise OpsClientError("OPS_API_URL is not configured")
    if not config.ops_api_token:
        raise OpsClientError("OPS_API_TOKEN or COMMAND_API_TOKEN is not configured")
    return OpsClient(
        base_url=config.ops_api_url,
        token=config.ops_api_token,
        timeout=config.ops_api_timeout_seconds,
    )


def get_ops_deploy_client(config: AppConfig | None = None) -> OpsClient:
    config = config or get_config()
    if not config.ops_api_url:
        raise OpsClientError("OPS_API_URL is not configured")
    if not config.ops_api_token:
        raise OpsClientError("OPS_API_TOKEN or COMMAND_API_TOKEN is not configured")
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


def deploy_cloud_ref(ref: str, mode: str = "quick", source: str = "codex_app", requested_by: str = "codex") -> dict[str, Any]:
    return get_ops_deploy_client().post(
        "/ops/deploy",
        {
            "ref": ref,
            "mode": mode,
            "source": source,
            "requested_by": requested_by,
        },
    )


def fetch_cloud_deploy_status(deploy_event_id: int) -> dict[str, Any]:
    return get_ops_client().get("/ops/deploy-status", {"id": deploy_event_id})


def render_cloud_deploy(ref: str, mode: str = "quick") -> str:
    try:
        data = deploy_cloud_ref(ref=ref, mode=mode)
    except OpsClientError as exc:
        return f"云端部署失败：{exc}"

    lines = [
        "云端部署已启动：",
        f"- deploy_event：#{data.get('deploy_event_id') or '-'}",
        f"- ref：{data.get('ref') or ref}",
        f"- commit：{data.get('commit_sha') or '-'}",
        f"- mode：{data.get('mode') or mode}",
        f"- 状态：{data.get('status') or '-'}",
    ]
    summary = str(data.get("summary") or "").strip()
    if summary:
        lines.append(f"- 摘要：{summary}")
    lines.append("")
    lines.append("可继续问：`cloud_deploy_status` 或 `系统总览`。")
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
