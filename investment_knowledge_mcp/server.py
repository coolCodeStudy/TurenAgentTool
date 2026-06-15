from __future__ import annotations

import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.command_router import (
    handle_command,
    is_candidate_write_command,
    is_coding_task_command,
    is_maintenance_command,
    is_query_command,
    is_research_write_command,
)
from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.display import build_stock_decision_card
from investment_knowledge_mcp.futu_provider import get_futu_positions
from investment_knowledge_mcp.ops_client import (
    deploy_cloud_ref,
    fetch_cloud_system_status,
    fetch_coding_status,
    fetch_recent_errors,
    fetch_service_logs,
    render_cloud_deploy,
    render_cloud_system_status,
    render_recent_errors,
    render_service_logs,
)
from investment_knowledge_mcp.research.jobs import create_research_job as create_research_job_record
from investment_knowledge_mcp.research.jobs import list_research_jobs as list_research_job_records
from investment_knowledge_mcp.research.jobs import list_research_jobs_for_stock
from investment_knowledge_mcp.system_overview import build_system_overview, render_system_overview


config = get_config()
mcp = FastMCP(
    "InvestmentKnowledge",
    host=config.mcp_host,
    port=config.mcp_port,
    streamable_http_path=config.mcp_path,
)


@mcp.tool()
def search_stock(symbol: str, market: str) -> dict[str, Any]:
    """Search a stock profile with linked sectors, knowledge, and user insights."""
    return repository.search_stock(symbol=symbol, market=market)


@mcp.tool()
def inspect_stock_decision_card(symbol: str, market: str) -> dict[str, Any]:
    """Build the default Level 1 decision card for a stock without expanding evidence."""
    context = repository.get_stock_context(symbol=symbol, market=market)
    jobs = list_research_jobs_for_stock(symbol=symbol, market=market, limit=1)
    latest_job = jobs[0] if jobs else None
    return build_stock_decision_card(context, latest_research_job=latest_job)


@mcp.tool()
def get_stock_context(symbol: str, market: str) -> dict[str, Any]:
    """Build analysis context for a stock, including sectors and relevant user memory."""
    return repository.get_stock_context(symbol=symbol, market=market)


@mcp.tool()
def get_sector_context(
    path: list[str] | None = None,
    sector_id: int | None = None,
) -> dict[str, Any]:
    """Build analysis context for a sector path or sector id."""
    return repository.get_sector_context(path=path, sector_id=sector_id)


@mcp.tool()
def upsert_stock_profile(
    symbol: str,
    market: str,
    name: str | None = None,
    core_business: str | None = None,
    equity_structure: str | None = None,
    stock_character: str | None = None,
    notable_history: str | None = None,
) -> dict[str, Any]:
    """Create or update a stock profile."""
    return repository.upsert_stock_profile(
        symbol=symbol,
        market=market,
        name=name,
        core_business=core_business,
        equity_structure=equity_structure,
        stock_character=stock_character,
        notable_history=notable_history,
    )


@mcp.tool()
def upsert_sector_tree(
    path: list[str],
    description: str | None = None,
    recent_status: str | None = None,
) -> dict[str, Any]:
    """Create or update a sector path and return the leaf sector."""
    return repository.upsert_sector_tree(
        path=path,
        description=description,
        recent_status=recent_status,
    )


@mcp.tool()
def link_stock_to_sector(
    stock_id: int,
    sector_id: int,
    relation_type: str = "related",
    confidence: float = 0.5,
    source_id: int | None = None,
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    """Link a stock to a sector."""
    return repository.link_stock_to_sector(
        stock_id=stock_id,
        sector_id=sector_id,
        relation_type=relation_type,
        confidence=confidence,
        source_id=source_id,
        confirmed_by_user=confirmed_by_user,
    )


@mcp.tool()
def add_source(
    source_type: str,
    title: str | None = None,
    url: str | None = None,
    publisher: str | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    """Add a source record for factual knowledge."""
    return repository.add_source(
        source_type=source_type,
        title=title,
        url=url,
        publisher=publisher,
        published_at=published_at,
    )


@mcp.tool()
def add_knowledge_item(
    target_type: str,
    target_id: int | None,
    knowledge_type: str,
    content: str,
    source_id: int | None = None,
    confidence: float = 0.5,
    confirmed_by_user: bool = False,
    stale_after: str | None = None,
) -> dict[str, Any]:
    """Add a factual knowledge item."""
    return repository.add_knowledge_item(
        target_type=target_type,
        target_id=target_id,
        knowledge_type=knowledge_type,
        content=content,
        source_id=source_id,
        confidence=confidence,
        confirmed_by_user=confirmed_by_user,
        stale_after=stale_after,
    )


@mcp.tool()
def add_user_insight(
    target_type: str,
    target_id: int | None,
    insight: str,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Add a user investment insight while preserving the original text."""
    return repository.add_user_insight(
        target_type=target_type,
        target_id=target_id,
        insight=insight,
        normalized_summary=normalized_summary,
        tags=tags,
    )


@mcp.tool()
def record_user_insight(
    target_type: str,
    insight: str,
    target_id: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    sector_path: list[str] | None = None,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Record user memory by resolving stock, sector, portfolio, or strategy targets."""
    return repository.record_user_insight(
        target_type=target_type,
        insight=insight,
        target_id=target_id,
        symbol=symbol,
        market=market,
        sector_path=sector_path,
        normalized_summary=normalized_summary,
        tags=tags,
    )


@mcp.tool()
def propose_candidate_insight(
    target_type: str,
    insight: str,
    target_id: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    sector_path: list[str] | None = None,
    normalized_summary: str | None = None,
    tags: list[str] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Propose an inferred user insight for later user confirmation."""
    return repository.propose_candidate_insight(
        target_type=target_type,
        insight=insight,
        target_id=target_id,
        symbol=symbol,
        market=market,
        sector_path=sector_path,
        normalized_summary=normalized_summary,
        tags=tags,
        reason=reason,
    )


@mcp.tool()
def list_candidate_insights(
    status: str | None = "pending",
    target_type: str | None = None,
) -> list[dict[str, Any]]:
    """List candidate insights waiting for confirmation or review."""
    return repository.list_candidate_insights(status=status, target_type=target_type)


@mcp.tool()
def confirm_candidate_insight(candidate_id: int) -> dict[str, Any]:
    """Confirm a candidate insight and promote it into user_insights."""
    return repository.confirm_candidate_insight(candidate_id=candidate_id)


@mcp.tool()
def reject_candidate_insight(candidate_id: int) -> dict[str, Any]:
    """Reject a candidate insight so it is not treated as user memory."""
    return repository.reject_candidate_insight(candidate_id=candidate_id)


@mcp.tool()
def get_realtime_portfolio_positions() -> dict[str, Any]:
    """Read current portfolio positions from Futu OpenD. This is read-only and never trades."""
    snapshot = get_futu_positions()
    return {
        "source": snapshot.source,
        "cached": snapshot.cached,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "positions": snapshot.positions,
    }


@mcp.tool()
def create_coding_task(
    title: str,
    description: str | None = None,
    priority: str = "normal",
    labels: list[str] | None = None,
    sender: str | None = None,
    source: str = "hermes",
) -> dict[str, Any]:
    """Create a coding task for later Codex/manual handling. This does not edit code."""
    return repository.create_coding_task(
        title=title,
        description=description,
        priority=priority,
        labels=labels,
        sender=sender,
        source=source,
    )


@mcp.tool()
def list_coding_tasks(status: str | None = "pending", limit: int = 10) -> list[dict[str, Any]]:
    """List coding tasks tracked by InvestmentKnowledge."""
    return repository.list_coding_tasks(status=status, limit=limit)


@mcp.tool()
def create_research_job(
    symbol: str,
    market: str,
    name: str | None = None,
    priority: str = "normal",
    source_policy: str = "broad_search",
    provider: str = "codex",
    auto_import: bool = True,
    import_needs_review: bool = False,
    refresh: bool = False,
    sender: str | None = None,
    source: str = "codex",
) -> dict[str, Any]:
    """Create an async Codex-first stock research job. This queues work; it does not trade."""
    return create_research_job_record(
        symbol=symbol,
        market=market,
        name=name,
        priority=priority,
        source_policy=source_policy,
        provider=provider,
        auto_import=auto_import,
        import_needs_review=import_needs_review,
        refresh=refresh,
        sender=sender,
        source=source,
        execution_location="cloud_worker",
        created_from="mcp_tool",
        requested_by=sender,
    )


@mcp.tool()
def create_portfolio_research_jobs(
    provider: str = "codex",
    source_policy: str = "broad_search",
    priority: str = "normal",
    include_existing: bool = False,
    refresh: bool = False,
    limit: int | None = None,
    sender: str | None = None,
    source: str = "codex",
) -> dict[str, Any]:
    """Create async Codex-first research jobs for current Futu holdings."""
    snapshot = get_futu_positions()
    positions = [item for item in snapshot.positions if _positive_qty(item)]
    if limit is not None:
        positions = positions[: max(0, int(limit))]

    created: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    skipped_invalid: list[dict[str, Any]] = []
    for position in positions:
        code = str(position.get("code") or "")
        if "." not in code:
            skipped_invalid.append({"code": code, "reason": "missing market prefix"})
            continue
        market, symbol = code.split(".", 1)
        market = market.upper()
        symbol = symbol.upper()
        if not include_existing and repository.search_stock(symbol=symbol, market=market).get("stock"):
            skipped_existing.append({"symbol": symbol, "market": market, "name": position.get("stock_name")})
            continue
        created.append(
            create_research_job_record(
                symbol=symbol,
                market=market,
                name=position.get("stock_name"),
                priority=priority,
                source_policy=source_policy,
                provider=provider,
                auto_import=True,
                import_needs_review=False,
                refresh=refresh,
                sender=sender,
                source=source,
                execution_location="cloud_worker",
                created_from="mcp_tool",
                requested_by=sender,
            )
        )
    return {
        "created_count": len(created),
        "skipped_existing_count": len(skipped_existing),
        "skipped_invalid_count": len(skipped_invalid),
        "created": created,
        "skipped_existing": skipped_existing,
        "skipped_invalid": skipped_invalid,
    }


@mcp.tool()
def list_research_jobs(status: str | None = "queued", limit: int = 20, verbose: bool = False) -> list[dict[str, Any]]:
    """List async stock research jobs."""
    return list_research_job_records(status=status, limit=limit, verbose=verbose)


@mcp.tool()
def claim_next_coding_task(worker_name: str = "codex-worker") -> dict[str, Any] | None:
    """Claim the next pending coding task for a trusted code worker."""
    return repository.claim_next_coding_task(worker_name=worker_name)


@mcp.tool()
def update_coding_task(
    task_id: int,
    status: str,
    result: str | None = None,
    branch_name: str | None = None,
    commit_sha: str | None = None,
    worker_log: str | None = None,
    linked_issue_url: str | None = None,
) -> dict[str, Any]:
    """Update a coding task after a trusted worker has processed it."""
    return repository.update_coding_task(
        task_id=task_id,
        status=status,
        result=result,
        branch_name=branch_name,
        commit_sha=commit_sha,
        worker_log=worker_log,
        linked_issue_url=linked_issue_url,
    )


@mcp.tool()
def run_investment_command(
    command: str,
    sender: str | None = None,
    source: str = "hermes",
) -> dict[str, Any]:
    """Run a safe natural-language InvestmentKnowledge command for an agent shell.

    This tool is intended for Hermes/OpenClaw style gateways. It permits
    query commands, Futu maintenance commands, candidate-memory proposals, and
    explicit candidate confirmation/rejection. Direct formal memory writes remain
    blocked.
    """
    cleaned = command.strip()
    if not cleaned:
        return {"ok": False, "message": "command is required"}

    if not _is_safe_agent_command(cleaned):
        message = (
            "Hermes MCP 当前只允许查询类、富途维护类、候选心得和候选确认/拒绝指令。"
            "正式心得写入必须先经过候选确认，避免污染长期记忆。"
        )
        _record_agent_command(command=cleaned, ok=False, message=message, sender=sender, source=source)
        return {"ok": False, "message": message}

    try:
        run_schema()
        result = handle_command(cleaned, include_artifact_path=False)
        _record_agent_command(
            command=cleaned,
            ok=result.ok,
            message=result.message,
            sender=sender,
            source=source,
        )
        return {"ok": result.ok, "message": result.message}
    except Exception as exc:
        message = f"执行 InvestmentKnowledge 指令失败：{exc}"
        _record_agent_command(command=cleaned, ok=False, message=message, sender=sender, source=source)
        return {"ok": False, "message": message}


def _is_safe_agent_command(command: str) -> bool:
    return bool(
        is_query_command(command)
        or is_maintenance_command(command)
        or is_candidate_write_command(command)
        or is_coding_task_command(command)
        or is_research_write_command(command)
        or re.fullmatch(r"(?:确认候选心得|confirm candidate)\s+\d+", command, flags=re.IGNORECASE)
        or re.fullmatch(r"(?:拒绝候选心得|reject candidate)\s+\d+", command, flags=re.IGNORECASE)
    )


def _record_agent_command(
    command: str,
    ok: bool,
    message: str,
    sender: str | None,
    source: str | None,
) -> None:
    try:
        repository.record_command_event(
            command=command,
            ok=ok,
            message=message,
            sender=sender,
            source=source,
        )
    except Exception:
        # Command execution should not fail just because audit logging is down.
        return


@mcp.tool()
def cloud_system_status(render: bool = True) -> dict[str, Any]:
    """Read ECS-level system status through the controlled Ops API."""
    if render:
        return {"ok": True, "message": render_cloud_system_status()}
    return {"ok": True, "data": fetch_cloud_system_status()}


@mcp.tool()
def cloud_recent_errors(lines: int = 160, render: bool = True) -> dict[str, Any]:
    """Read recent ECS/Hermes/Codex/Futu errors through the controlled Ops API."""
    if render:
        return {"ok": True, "message": render_recent_errors(lines=lines)}
    return {"ok": True, "data": fetch_recent_errors(lines=lines)}


@mcp.tool()
def cloud_service_logs(service: str, lines: int = 120, render: bool = True) -> dict[str, Any]:
    """Read recent logs for one whitelisted cloud service."""
    if render:
        return {"ok": True, "message": render_service_logs(service=service, lines=lines)}
    return {"ok": True, "data": fetch_service_logs(service=service, lines=lines)}


@mcp.tool()
def cloud_coding_status() -> dict[str, Any]:
    """Read cloud Codex worker status through the controlled Ops API."""
    return {"ok": True, "data": fetch_coding_status()}


@mcp.tool()
def cloud_deploy(ref: str, mode: str = "quick", render: bool = True) -> dict[str, Any]:
    """Deploy a pushed Git ref on ECS through the controlled Ops API."""
    if render:
        return {"ok": True, "message": render_cloud_deploy(ref=ref, mode=mode)}
    return {"ok": True, "data": deploy_cloud_ref(ref=ref, mode=mode)}


@mcp.tool()
def system_overview(render: bool = True) -> dict[str, Any]:
    """Read the Codex-first control-plane overview: services, queues, deployments, workers, and recent failures."""
    if render:
        return {"ok": True, "message": render_system_overview()}
    return {"ok": True, "data": build_system_overview()}


@mcp.tool()
def import_stock_research_draft(
    draft: dict[str, Any],
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    """Import a user-confirmed stock research draft into the knowledge base."""
    return repository.import_stock_research_draft(
        draft=draft,
        confirmed_by_user=confirmed_by_user,
    )


def _positive_qty(position: dict[str, Any]) -> bool:
    try:
        return float(position.get("qty") or 0) > 0
    except (TypeError, ValueError):
        return False


def main() -> None:
    mcp.run(transport=config.mcp_transport)


if __name__ == "__main__":
    main()
