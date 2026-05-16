from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.config import get_config


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
def import_stock_research_draft(
    draft: dict[str, Any],
    confirmed_by_user: bool = False,
) -> dict[str, Any]:
    """Import a user-confirmed stock research draft into the knowledge base."""
    return repository.import_stock_research_draft(
        draft=draft,
        confirmed_by_user=confirmed_by_user,
    )


def main() -> None:
    mcp.run(transport=config.mcp_transport)


if __name__ == "__main__":
    main()
