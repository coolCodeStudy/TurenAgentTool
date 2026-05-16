from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.repository import (
    add_knowledge_item,
    add_source,
    add_user_insight,
    link_stock_to_sector,
    search_stock,
    upsert_sector_tree,
    upsert_stock_profile,
)

SMOKE_SYMBOL = "SMOKE001"
SMOKE_MARKET = "TEST"
SMOKE_SOURCE_URL = "https://example.invalid/investment-knowledge-smoke-test"
SMOKE_SECTOR_ROOT = "__smoke_test__"


def cleanup_smoke_data() -> None:
    with transaction() as conn:
        stock = conn.execute(
            """
            SELECT id
            FROM stocks
            WHERE symbol = %s AND market = %s
            """,
            (SMOKE_SYMBOL, SMOKE_MARKET),
        ).fetchone()
        if stock is not None:
            conn.execute(
                """
                DELETE FROM knowledge_items
                WHERE target_type = 'stock' AND target_id = %s
                """,
                (stock["id"],),
            )
            conn.execute(
                """
                DELETE FROM user_insights
                WHERE target_type = 'stock' AND target_id = %s
                """,
                (stock["id"],),
            )
            conn.execute("DELETE FROM stocks WHERE id = %s", (stock["id"],))

        conn.execute("DELETE FROM sources WHERE url = %s", (SMOKE_SOURCE_URL,))
        conn.execute(
            """
            DELETE FROM sectors
            WHERE parent_id IN (
              SELECT id FROM sectors WHERE name = %s AND parent_id IS NULL
            )
            """,
            (SMOKE_SECTOR_ROOT,),
        )
        conn.execute(
            """
            DELETE FROM sectors
            WHERE name = %s AND parent_id IS NULL
            """,
            (SMOKE_SECTOR_ROOT,),
        )


def main() -> None:
    run_schema()
    cleanup_smoke_data()

    try:
        stock = upsert_stock_profile(
            symbol=SMOKE_SYMBOL,
            market=SMOKE_MARKET,
            name="Smoke Test Stock",
            core_business="用于本地链路验证的测试股票。",
            stock_character="测试数据，运行结束后应被清理。",
            notable_history="用于验证数据库和 MCP repository 写入查询闭环。",
        )
        sector_tree = upsert_sector_tree(
            path=[SMOKE_SECTOR_ROOT, "链路验证"],
            description="测试专用板块。",
            recent_status="测试运行结束后应被清理。",
        )
        source = add_source(
            source_type="test",
            title="Smoke Test Source",
            url=SMOKE_SOURCE_URL,
            publisher="InvestmentKnowledge MCP",
        )
        repeated_source = add_source(
            source_type="test",
            title="Smoke Test Source",
            url=SMOKE_SOURCE_URL,
            publisher="InvestmentKnowledge MCP",
        )
        relation = link_stock_to_sector(
            stock_id=stock["id"],
            sector_id=sector_tree["leaf"]["id"],
            relation_type="main",
            confidence=0.9,
            source_id=source["id"],
            confirmed_by_user=True,
        )
        knowledge = add_knowledge_item(
            target_type="stock",
            target_id=stock["id"],
            knowledge_type="business",
            content="Smoke test verifies idempotent knowledge insertion.",
            source_id=source["id"],
            confidence=0.8,
            confirmed_by_user=True,
        )
        repeated_knowledge = add_knowledge_item(
            target_type="stock",
            target_id=stock["id"],
            knowledge_type="business",
            content="Smoke test verifies idempotent knowledge insertion.",
            source_id=source["id"],
            confidence=0.8,
            confirmed_by_user=True,
        )
        insight = add_user_insight(
            target_type="stock",
            target_id=stock["id"],
            insight="Smoke test verifies idempotent user insight insertion.",
            normalized_summary="Smoke test insight should not duplicate.",
            tags=["smoke-test"],
        )
        repeated_insight = add_user_insight(
            target_type="stock",
            target_id=stock["id"],
            insight="Smoke test verifies idempotent user insight insertion.",
            normalized_summary="Smoke test insight should not duplicate.",
            tags=["smoke-test"],
        )
        result = search_stock(symbol=SMOKE_SYMBOL, market=SMOKE_MARKET)

        assert repeated_source["id"] == source["id"]
        assert repeated_knowledge["id"] == knowledge["id"]
        assert repeated_insight["id"] == insight["id"]
        assert result["stock"]["id"] == stock["id"]
        assert result["sectors"][0]["relation_id"] == relation["id"]
        assert len(result["knowledge_items"]) == 1
        assert len(result["user_insights"]) == 1

        print("Smoke test passed.")
        print(
            {
                "stock": result["stock"]["symbol"],
                "sector_count": len(result["sectors"]),
                "knowledge_count": len(result["knowledge_items"]),
                "insight_count": len(result["user_insights"]),
            }
        )
    finally:
        cleanup_smoke_data()


if __name__ == "__main__":
    main()
