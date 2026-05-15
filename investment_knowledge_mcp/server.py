from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from investment_knowledge_mcp import repository


mcp = FastMCP("InvestmentKnowledge")


@mcp.tool()
def search_stock(symbol: str, market: str) -> dict[str, Any]:
    """Search a stock profile with linked sectors, knowledge, and user insights."""
    return repository.search_stock(symbol=symbol, market=market)


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


if __name__ == "__main__":
    mcp.run()
