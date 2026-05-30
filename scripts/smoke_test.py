from pathlib import Path
import os
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["OPENAI_ANALYSIS_ENABLED"] = "false"

from investment_knowledge_mcp.command_router import (
    handle_command,
    is_candidate_write_command,
    is_maintenance_command,
    is_query_command,
)
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.repository import (
    add_knowledge_item,
    add_source,
    confirm_candidate_insight,
    add_user_insight,
    get_sector_context,
    get_stock_context,
    list_candidate_insights,
    link_stock_to_sector,
    propose_candidate_insight,
    record_user_insight,
    resolve_stock_reference,
    reject_candidate_insight,
    search_stock,
    upsert_sector_tree,
    upsert_stock_profile,
)

SMOKE_SYMBOL = "SMOKE001"
SMOKE_MARKET = "TEST"
SMOKE_SOURCE_URL = "https://example.invalid/investment-knowledge-smoke-test"
SMOKE_SECTOR_ROOT = "__smoke_test__"
SMOKE_STOCK_INSIGHT = "Smoke test verifies idempotent user insight insertion."
SMOKE_SECTOR_INSIGHT = "Smoke test verifies sector-level user memory retrieval."
SMOKE_PORTFOLIO_INSIGHT = "Smoke test verifies portfolio-level user memory retrieval."
SMOKE_REJECTED_CANDIDATE = "Smoke test verifies candidate insight rejection."
SMOKE_CONFIRMED_CANDIDATE = "Smoke test verifies candidate insight confirmation."
SMOKE_ROUTER_INSIGHT = "Smoke test verifies command router formal insight recording."
SMOKE_ROUTER_CANDIDATE = "Smoke test verifies command router candidate proposal."
SMOKE_ROUTER_PORTFOLIO_INSIGHT = "Smoke test verifies command router portfolio insight recording."
SMOKE_ROUTER_STRATEGY_CANDIDATE = "Smoke test verifies command router strategy candidate proposal."
SMOKE_ROUTER_NATURAL_MEMORY = "我觉得 Smoke Test 的组合管理成本需要被系统识别并沉淀。"


def cleanup_smoke_data() -> None:
    with transaction() as conn:
        conn.execute(
            """
            DELETE FROM user_insights
            WHERE insight = ANY(%s)
            """,
            (
                [
                    SMOKE_STOCK_INSIGHT,
                    SMOKE_SECTOR_INSIGHT,
                    SMOKE_PORTFOLIO_INSIGHT,
                    SMOKE_REJECTED_CANDIDATE,
                    SMOKE_CONFIRMED_CANDIDATE,
                    SMOKE_ROUTER_INSIGHT,
                    SMOKE_ROUTER_CANDIDATE,
                    SMOKE_ROUTER_PORTFOLIO_INSIGHT,
                    SMOKE_ROUTER_STRATEGY_CANDIDATE,
                    SMOKE_ROUTER_NATURAL_MEMORY,
                ],
            ),
        )
        conn.execute(
            """
            DELETE FROM candidate_insights
            WHERE insight = ANY(%s)
            """,
            (
                [
                    SMOKE_REJECTED_CANDIDATE,
                    SMOKE_CONFIRMED_CANDIDATE,
                    SMOKE_ROUTER_CANDIDATE,
                    SMOKE_ROUTER_STRATEGY_CANDIDATE,
                    SMOKE_ROUTER_NATURAL_MEMORY,
                ],
            ),
        )
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
            insight=SMOKE_STOCK_INSIGHT,
            normalized_summary="Smoke test insight should not duplicate.",
            tags=["smoke-test"],
        )
        repeated_insight = add_user_insight(
            target_type="stock",
            target_id=stock["id"],
            insight=SMOKE_STOCK_INSIGHT,
            normalized_summary="Smoke test insight should not duplicate.",
            tags=["smoke-test"],
        )
        sector_insight = record_user_insight(
            target_type="sector",
            sector_path=[SMOKE_SECTOR_ROOT, "链路验证"],
            insight=SMOKE_SECTOR_INSIGHT,
            normalized_summary="Smoke test sector insight should appear in stock and sector context.",
            tags=["smoke-test", "sector"],
        )
        portfolio_insight = record_user_insight(
            target_type="portfolio",
            insight=SMOKE_PORTFOLIO_INSIGHT,
            normalized_summary="Smoke test portfolio insight should appear as global context.",
            tags=["smoke-test", "portfolio"],
        )
        rejected_candidate = propose_candidate_insight(
            target_type="sector",
            sector_path=[SMOKE_SECTOR_ROOT, "链路验证"],
            insight=SMOKE_REJECTED_CANDIDATE,
            normalized_summary="Smoke test candidate should be rejected.",
            tags=["smoke-test", "candidate"],
            reason="Smoke test exercises candidate rejection.",
        )
        confirmed_candidate = propose_candidate_insight(
            target_type="stock",
            symbol=SMOKE_SYMBOL,
            market=SMOKE_MARKET,
            insight=SMOKE_CONFIRMED_CANDIDATE,
            normalized_summary="Smoke test candidate should be promoted into user insights.",
            tags=["smoke-test", "candidate"],
            reason="Smoke test exercises candidate confirmation.",
        )
        pending_candidates = list_candidate_insights(status="pending")
        rejected_candidate = reject_candidate_insight(rejected_candidate["id"])
        confirmed_result = confirm_candidate_insight(confirmed_candidate["id"])
        result = search_stock(symbol=SMOKE_SYMBOL, market=SMOKE_MARKET)
        stock_context = get_stock_context(symbol=SMOKE_SYMBOL, market=SMOKE_MARKET)
        sector_context = get_sector_context(path=[SMOKE_SECTOR_ROOT, "链路验证"])
        with tempfile.TemporaryDirectory() as tmp_dir:
            analyze_result = handle_command(
                f"分析 {SMOKE_SYMBOL} {SMOKE_MARKET}",
                output_dir=Path(tmp_dir),
            )
            assert analyze_result.ok
            assert "核心判断" in analyze_result.message
            assert (Path(tmp_dir) / f"{SMOKE_SYMBOL}_{SMOKE_MARKET}_analysis_context.md").exists()

            natural_analyze_result = handle_command(
                "怎么看 Smoke Test Stock",
                output_dir=Path(tmp_dir),
            )
            assert natural_analyze_result.ok
            assert "Smoke Test Stock" in natural_analyze_result.message

        router_insight_result = handle_command(
            f"记录心得 {SMOKE_SYMBOL} {SMOKE_MARKET} {SMOKE_ROUTER_INSIGHT}"
        )
        router_candidate_result = handle_command(
            f"提出个股候选心得 {SMOKE_SYMBOL} {SMOKE_MARKET} {SMOKE_ROUTER_CANDIDATE}"
        )
        router_duplicate_candidate_result = handle_command(
            f"提出个股候选心得 {SMOKE_SYMBOL} {SMOKE_MARKET} {SMOKE_ROUTER_CANDIDATE}"
        )
        router_portfolio_insight_result = handle_command(f"记录组合心得 {SMOKE_ROUTER_PORTFOLIO_INSIGHT}")
        router_strategy_candidate_result = handle_command(f"提出策略候选心得 {SMOKE_ROUTER_STRATEGY_CANDIDATE}")
        router_natural_memory_result = handle_command(SMOKE_ROUTER_NATURAL_MEMORY)
        router_trade_review_result = handle_command("帮我看看这个月到底赚在哪亏在哪")
        router_candidates_result = handle_command("查看候选心得")

        assert repeated_source["id"] == source["id"]
        assert repeated_knowledge["id"] == knowledge["id"]
        assert repeated_insight["id"] == insight["id"]
        assert sector_insight["target_type"] == "sector"
        assert portfolio_insight["target_type"] == "portfolio"
        assert any(item["id"] == rejected_candidate["id"] for item in pending_candidates)
        assert rejected_candidate["status"] == "rejected"
        assert confirmed_result["candidate"]["status"] == "confirmed"
        assert confirmed_result["user_insight"]["insight"] == SMOKE_CONFIRMED_CANDIDATE
        assert result["stock"]["id"] == stock["id"]
        assert resolve_stock_reference("Smoke Test Stock")[0]["id"] == stock["id"]
        assert router_insight_result.ok
        assert router_candidate_result.ok
        assert router_duplicate_candidate_result.ok
        assert "已合并" in router_duplicate_candidate_result.message
        assert router_portfolio_insight_result.ok
        assert router_strategy_candidate_result.ok
        assert router_natural_memory_result.ok
        assert router_trade_review_result.ok
        assert router_candidates_result.ok
        assert not is_query_command(SMOKE_ROUTER_NATURAL_MEMORY)
        assert is_query_command("交易复盘")
        assert is_query_command("本月收益")
        assert is_candidate_write_command(SMOKE_ROUTER_NATURAL_MEMORY)
        assert is_candidate_write_command(f"提出策略候选心得 {SMOKE_ROUTER_STRATEGY_CANDIDATE}")
        assert is_maintenance_command("富途验证码 123456")
        assert is_maintenance_command("富途登录")
        assert SMOKE_ROUTER_CANDIDATE in router_candidates_result.message
        assert SMOKE_ROUTER_STRATEGY_CANDIDATE in router_candidates_result.message
        assert SMOKE_ROUTER_NATURAL_MEMORY in router_candidates_result.message
        assert "估算收益复盘" in router_trade_review_result.message
        assert result["sectors"][0]["relation_id"] == relation["id"]
        assert len(result["knowledge_items"]) == 1
        assert len(result["user_insights"]) == 2
        assert stock_context["stock"]["id"] == stock["id"]
        assert len(stock_context["sector_insights"]) == 1
        assert stock_context["sector_candidate_insights"] == []
        assert any(
            item["insight"] == SMOKE_PORTFOLIO_INSIGHT
            for item in stock_context["global_insights"]
        )
        assert sector_context["sector"]["sector_id"] == sector_tree["leaf"]["id"]
        assert len(sector_context["linked_stocks"]) == 1
        assert len(sector_context["sector_insights"]) == 1

        print("Smoke test passed.")
        print(
            {
                "stock": result["stock"]["symbol"],
                "sector_count": len(result["sectors"]),
                "knowledge_count": len(result["knowledge_items"]),
                "insight_count": len(result["user_insights"]),
                "context_sector_insight_count": len(stock_context["sector_insights"]),
                "context_global_insight_count": len(stock_context["global_insights"]),
                "confirmed_candidate_id": confirmed_result["candidate"]["id"],
            }
        )
    finally:
        cleanup_smoke_data()


if __name__ == "__main__":
    main()
