from __future__ import annotations

from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.ops_client import OpsClientError, fetch_cloud_system_status


def build_system_overview() -> dict[str, Any]:
    run_schema()
    summary = repository.get_control_plane_summary()
    try:
        cloud_status = fetch_cloud_system_status()
        cloud_error = None
    except OpsClientError as exc:
        cloud_status = None
        cloud_error = str(exc)
    except Exception as exc:
        cloud_status = None
        cloud_error = str(exc)

    return {
        "cloud_status": cloud_status,
        "cloud_error": cloud_error,
        **summary,
    }


def render_system_overview() -> str:
    overview = build_system_overview()
    lines = ["系统总览："]

    cloud_status = overview.get("cloud_status")
    cloud_error = overview.get("cloud_error")
    if isinstance(cloud_status, dict):
        failed = [
            str(item.get("name") or "-")
            for item in cloud_status.get("checks") or []
            if isinstance(item, dict) and not item.get("ok")
        ]
        if failed:
            lines.append("- 云端服务：需要关注 " + "、".join(failed[:8]))
        else:
            lines.append("- 云端服务：核心检查 OK")
    else:
        lines.append(f"- 云端服务：Ops 暂不可用（{cloud_error or 'unknown'}）")

    research_counts = overview.get("research_jobs") or {}
    coding_counts = overview.get("coding_tasks") or {}
    lines.append("- 研究队列：" + _render_counts(research_counts))
    lines.append("- 开发队列：" + _render_counts(coding_counts))

    latest_deploy = _first(overview.get("recent_deploy_events"))
    if latest_deploy:
        duration = latest_deploy.get("duration_seconds")
        duration_text = f"，耗时 {float(duration):.0f}s" if duration is not None else ""
        commit = str(latest_deploy.get("commit_sha") or "-")[:12]
        lines.append(
            f"- 最近部署：#{latest_deploy.get('id')} {latest_deploy.get('status')} "
            f"{latest_deploy.get('deploy_mode')} commit={commit}{duration_text}"
        )
    else:
        lines.append("- 最近部署：暂无记录")

    commands_24h = overview.get("commands_24h") or {}
    lines.append(
        "- 24h 指令："
        f"total={commands_24h.get('total_24h') or 0} "
        f"ok={commands_24h.get('ok_24h') or 0} "
        f"failed={commands_24h.get('failed_24h') or 0}"
    )

    snapshot = overview.get("latest_account_snapshot")
    if snapshot:
        lines.append(
            f"- 最近账户快照：{snapshot.get('snapshot_date')} "
            f"source={snapshot.get('source')} fetched_at={snapshot.get('fetched_at')}"
        )
    else:
        lines.append("- 最近账户快照：暂无")

    workers = overview.get("worker_status") or []
    if workers:
        worker_text = "；".join(
            f"{item.get('name')}={item.get('status')}"
            + (f" err={str(item.get('last_error'))[:80]}" if item.get("last_error") else "")
            for item in workers[:8]
        )
        lines.append("- Worker： " + worker_text)
    else:
        lines.append("- Worker：暂无心跳记录")

    failed_commands = overview.get("recent_failed_commands") or []
    if failed_commands:
        lines.append("")
        lines.append("最近失败指令：")
        for item in failed_commands[:3]:
            lines.append(
                f"- {item.get('created_at')} {item.get('command')}："
                f"{str(item.get('message') or '')[:120]}"
            )

    recent_events = overview.get("recent_task_events") or []
    if recent_events:
        lines.append("")
        lines.append("最近任务事件：")
        for item in recent_events[:5]:
            task_id = f"#{item.get('task_id')}" if item.get("task_id") is not None else "-"
            lines.append(
                f"- {item.get('created_at')} {item.get('task_type')} {task_id} "
                f"{item.get('event_type')} {item.get('status') or ''}"
            )

    return "\n".join(lines)


def _render_counts(counts: dict[str, Any]) -> str:
    if not counts:
        return "empty"
    return "，".join(f"{key}={value}" for key, value in sorted(counts.items()))


def _first(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return None
