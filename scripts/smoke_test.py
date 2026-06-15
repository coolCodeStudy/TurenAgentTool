from pathlib import Path
from datetime import datetime, timedelta
import os
import sys
import tempfile
from types import SimpleNamespace
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ["OPENAI_ANALYSIS_ENABLED"] = "false"

from investment_knowledge_mcp.command_router import (
    _extract_time_range_text,
    _render_performance_estimate,
    _resolve_trade_review_range,
    _resolve_weekly_review_range,
    handle_command,
    is_candidate_write_command,
    is_maintenance_command,
    is_query_command,
    is_research_write_command,
)
from investment_knowledge_mcp.db import run_schema
from investment_knowledge_mcp.db import transaction
from investment_knowledge_mcp.portfolio_graph import build_portfolio_graph_queue, render_portfolio_graph_queue
from investment_knowledge_mcp.research.audit import audit_research_draft
from investment_knowledge_mcp.research.jobs import create_research_job, list_research_jobs, update_research_job
from investment_knowledge_mcp.research.official_sources import (
    _classify_hkex_title,
    _classify_issuer_ir_title,
    _dedupe_source_documents,
    _extract_sec_ixbrl_text,
    _extract_report_year,
    _extract_pdf_links,
    _extract_hkex_stock_ids,
    _fetch_hk_issuer_ir_candidates,
    _select_hk_issuer_ir_candidates,
    _select_sec_recent_filing_candidates,
    _issuer_ir_key,
    _hkex_title_search_urls,
)
from investment_knowledge_mcp.research.models import SourceDocument
from investment_knowledge_mcp.research.official_sources import FilingCandidate
from investment_knowledge_mcp.research.source_facts import extract_source_facts
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
    upsert_account_snapshot,
    upsert_sector_tree,
    upsert_stock_profile,
    upsert_trade_records,
)
from investment_knowledge_mcp.weekly_review import build_weekly_review, build_weekly_review_context, render_weekly_review_markdown
from investment_knowledge_mcp.weekly_review_web import _resolve_request_range, render_weekly_review_workbench_html

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
SMOKE_JOB_SYMBOL = "SMOKEJOB"
SMOKE_JOB_MARKET = "TEST"


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
            DELETE FROM research_jobs
            WHERE symbol = %s AND market = %s
            """,
            (SMOKE_JOB_SYMBOL, SMOKE_JOB_MARKET),
        )
        conn.execute(
            """
            DELETE FROM review_reports
            WHERE report_type = 'weekly'
              AND period_start = DATE '2020-01-06'
              AND period_end = DATE '2020-01-12'
            """
        )
        conn.execute(
            """
            DELETE FROM trade_records
            WHERE code IN (%s, %s)
            """,
            (f"{SMOKE_MARKET}.{SMOKE_SYMBOL}", "TEST.LOSS"),
        )
        conn.execute(
            """
            DELETE FROM account_snapshots
            WHERE metadata->>'task' = 'smoke_weekly_review'
            """
        )
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
            assert SMOKE_SYMBOL in analyze_result.message
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
        graph_context = build_portfolio_graph_queue(
            SimpleNamespace(
                positions=[
                    {
                        "code": f"{SMOKE_MARKET}.{SMOKE_SYMBOL}",
                        "stock_name": "Smoke Test Stock",
                        "qty": 10,
                        "market_val": 1000,
                        "pl_val": 12,
                        "currency": "USD",
                    },
                    {
                        "code": "HK.MISSING",
                        "stock_name": "Missing Graph Stock",
                        "qty": 20,
                        "market_val": 500,
                        "pl_val": -5,
                        "currency": "HKD",
                    },
                ],
                fetched_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                cached=False,
                source="smoke",
            )
        )
        graph_message = render_portfolio_graph_queue(graph_context)
        old_budget_gate = os.environ.get("RESEARCH_CODEX_MAX_ACTIVE_JOBS")
        os.environ["RESEARCH_CODEX_MAX_ACTIVE_JOBS"] = "-1"
        research_job = create_research_job(
            symbol=SMOKE_JOB_SYMBOL,
            market=SMOKE_JOB_MARKET,
            name="Smoke Research Job",
            source="smoke_test",
            sender="smoke",
        )
        updated_research_job = update_research_job(
            job_id=int(research_job["id"]),
            status="drafted",
            artifact_dir="/tmp/smoke-research-job",
            artifacts={
                "draft_path": "/tmp/smoke-research-job/draft.json",
                "source_facts_path": "/tmp/smoke-research-job/source_facts.json",
                "audit_path": "/tmp/smoke-research-job/audit.md",
                "review_path": "/tmp/smoke-research-job/review.md",
                "warnings": ["smoke warning"],
                "import_status": "not_imported",
                "token_usage": {"total_tokens": 12},
            },
        )
        research_job_summaries = list_research_jobs(status="all", limit=10)
        smoke_research_summary = next(item for item in research_job_summaries if item["id"] == research_job["id"])
        if old_budget_gate is None:
            os.environ.pop("RESEARCH_CODEX_MAX_ACTIVE_JOBS", None)
        else:
            os.environ["RESEARCH_CODEX_MAX_ACTIVE_JOBS"] = old_budget_gate

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
        assert graph_context["summary"]["position_count"] == 2
        assert graph_context["summary"]["stock_profile_count"] == 1
        assert graph_context["summary"]["sector_linked_count"] == 1
        assert "持仓图谱队列" in graph_message
        assert "Missing Graph Stock" in graph_message
        assert research_job["execution_location"] == "cloud_worker"
        assert research_job["created_from"] == "mcp_tool"
        assert updated_research_job["artifact_location"] == "/tmp/smoke-research-job"
        assert smoke_research_summary["execution_location"] == "cloud_worker"
        assert smoke_research_summary["artifacts"]["draft"]
        assert smoke_research_summary["artifacts"]["audit"]
        assert smoke_research_summary["warnings_count"] == 1
        assert smoke_research_summary["import_status"] == "not_imported"
        assert not is_query_command(SMOKE_ROUTER_NATURAL_MEMORY)
        assert is_query_command("持仓图谱")
        assert is_query_command(f"研究草稿 {SMOKE_SYMBOL} {SMOKE_MARKET}")
        assert is_query_command("全持仓研究草稿")
        assert is_query_command("列出研究任务")
        assert is_research_write_command("持仓图谱补全")
        assert is_research_write_command("重新审核研究任务 33")
        assert is_research_write_command("取消研究任务 33")
        assert not is_research_write_command("列出研究任务")
        assert is_maintenance_command("停止研究worker")
        assert is_maintenance_command("启动研究worker")
        assert is_query_command("交易复盘")
        assert is_query_command("本月收益")
        assert is_query_command("补全交易记录 2026-05")
        assert is_query_command("本周复盘")
        assert is_query_command("上周复盘")
        assert is_query_command("复盘 上周")
        assert is_query_command("复盘 2020-01-06 2020-01-12")
        assert is_query_command("查看下周节奏")
        assert _extract_time_range_text("5月收益") == "5月"
        assert _extract_time_range_text("五月份收益") == "五月份"
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        week_start, week_end, _ = _resolve_weekly_review_range("")
        assert week_start == today - timedelta(days=today.weekday())
        assert week_end == today
        prev_week_start, prev_week_end, _ = _resolve_weekly_review_range("上周")
        assert prev_week_start == today - timedelta(days=today.weekday() + 7)
        assert prev_week_end == today - timedelta(days=today.weekday() + 1)
        may_start, may_end, may_label = _resolve_trade_review_range("5月")
        expected_may_year = today.year if 5 <= today.month else today.year - 1
        assert may_start.isoformat() == f"{expected_may_year}-05-01"
        assert may_label == f"{expected_may_year}-05"
        may_zh_start, _, may_zh_label = _resolve_trade_review_range("五月份")
        assert may_zh_start.isoformat() == f"{expected_may_year}-05-01"
        assert may_zh_label == f"{expected_may_year}-05"
        future_month = today.month + 1 if today.month < 12 else 1
        future_start, _, future_label = _resolve_trade_review_range(f"{future_month}月")
        expected_future_year = today.year - 1 if future_month > today.month else today.year
        assert future_start.isoformat() == f"{expected_future_year}-{future_month:02d}-01"
        assert future_label == f"{expected_future_year}-{future_month:02d}"
        range_start, range_end, _ = _resolve_trade_review_range("5月1日到5月31日")
        assert range_start.isoformat() == f"{expected_may_year}-05-01"
        assert range_end.isoformat() == f"{expected_may_year}-05-31"
        month_range_start, month_range_end, _ = _resolve_trade_review_range("4月到5月")
        expected_april_year = today.year if 4 <= today.month else today.year - 1
        assert month_range_start.isoformat() == f"{expected_april_year}-04-01"
        assert month_range_end.isoformat() == f"{expected_may_year}-05-31"
        recent_start, recent_end, _ = _resolve_trade_review_range("最近30天")
        assert recent_end == today
        assert (recent_end - recent_start).days == 29
        weekly_start = datetime(2020, 1, 6, tzinfo=ZoneInfo("Asia/Shanghai")).date()
        weekly_end = datetime(2020, 1, 12, tzinfo=ZoneInfo("Asia/Shanghai")).date()
        upsert_account_snapshot(
            snapshot_date=weekly_start.isoformat(),
            account_info={"currency": "USD", "total_assets": 2000},
            positions=[
                {
                    "code": f"{SMOKE_MARKET}.{SMOKE_SYMBOL}",
                    "stock_name": "Smoke Test Stock",
                    "qty": 10,
                    "cost_price": 99,
                    "market_val": 1000,
                    "pl_val": 10,
                    "pl_ratio": 0.01,
                    "currency": "USD",
                },
                {
                    "code": "TEST.LOSS",
                    "stock_name": "Smoke Loss Stock",
                    "qty": 5,
                    "cost_price": 20,
                    "market_val": 100,
                    "pl_val": 40,
                    "pl_ratio": 0.4,
                    "currency": "USD",
                },
                {
                    "code": "TEST.CUT",
                    "stock_name": "Smoke Cut Loss Stock",
                    "qty": 3,
                    "cost_price": 20,
                    "market_val": 45,
                    "pl_val": -15,
                    "pl_ratio": -0.25,
                    "currency": "USD",
                },
                {
                    "code": "TEST.TAKE",
                    "stock_name": "Smoke Take Profit Stock",
                    "qty": 2,
                    "cost_price": 20,
                    "market_val": 55,
                    "pl_val": 15,
                    "pl_ratio": 0.38,
                    "currency": "USD",
                },
            ],
            fx_rates={"USD": 1.0},
            fetched_at=datetime(2020, 1, 6, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(),
            metadata={"task": "smoke_weekly_review"},
        )
        upsert_account_snapshot(
            snapshot_date=weekly_end.isoformat(),
            account_info={"currency": "USD", "total_assets": 2100},
            positions=[
                {
                    "code": f"{SMOKE_MARKET}.{SMOKE_SYMBOL}",
                    "stock_name": "Smoke Test Stock",
                    "qty": 10,
                    "cost_price": 99,
                    "market_val": 1100,
                    "pl_val": 80,
                    "pl_ratio": 0.08,
                    "currency": "USD",
                },
                {
                    "code": "TEST.LOSS",
                    "stock_name": "Smoke Loss Stock",
                    "qty": 7,
                    "cost_price": 18,
                    "market_val": 90,
                    "pl_val": -50,
                    "pl_ratio": -0.35,
                    "currency": "USD",
                },
            ],
            fx_rates={"USD": 1.0},
            fetched_at=datetime(2020, 1, 12, 23, 0, tzinfo=ZoneInfo("Asia/Shanghai")).isoformat(),
            metadata={"task": "smoke_weekly_review"},
        )
        upsert_trade_records(
            [
                {
                    "deal_id": "smoke-weekly-loss-buy",
                    "order_id": "smoke-weekly-loss-order",
                    "code": "TEST.LOSS",
                    "stock_name": "Smoke Loss Stock",
                    "trd_side": "BUY",
                    "qty": 2,
                    "price": 18,
                    "amount": 36,
                    "currency": "USD",
                    "create_time": "2020-01-08 10:00:00",
                }
            ]
        )
        weekly_context = build_weekly_review_context(start=weekly_start, end=weekly_end)
        weekly_markdown = render_weekly_review_markdown(weekly_context)
        assert weekly_context["source_status"]["account_snapshots"]["status"] == "ok"
        assert weekly_context["source_status"]["trades"]["count"] == 1
        assert weekly_context["highlights"][0]["code"] == f"{SMOKE_MARKET}.{SMOKE_SYMBOL}"
        assert any(item["code"] == "TEST.TAKE" and item["type"] == "止盈清仓" for item in weekly_context["highlights"])
        assert all(item["code"] != "TEST.CUT" for item in weekly_context["highlights"])
        assert weekly_context["blowups"][0]["code"] == "TEST.LOSS"
        assert weekly_context["blowups"][0]["movement"] == "加仓"
        assert any(item["code"] == "TEST.CUT" and item["type"] == "割肉清仓" for item in weekly_context["blowups"])
        assert "本周复盘 2020-01-06 至 2020-01-12" in weekly_markdown
        assert "指数数据源未接入" in weekly_markdown
        weekly_result = build_weekly_review(start=weekly_start, end=weekly_end, save=True)
        assert weekly_result.saved_report is not None
        assert weekly_result.saved_report["report_type"] == "weekly"
        assert str(weekly_result.saved_report["period_start"]) == "2020-01-06"
        assert str(weekly_result.saved_report["period_end"]) == "2020-01-12"
        weekly_command_result = handle_command("复盘 2020-01-06 2020-01-12")
        assert weekly_command_result.ok
        assert "本周复盘 2020-01-06 至 2020-01-12" in weekly_command_result.message
        assert "已保存周复盘" in weekly_command_result.message
        weekly_web_html = render_weekly_review_workbench_html()
        assert "InvestmentKnowledge" in weekly_web_html
        assert "本周复盘" in weekly_web_html
        assert "/api/weekly-review/save" in weekly_web_html
        assert "data-slot=\"holdings\"" in weekly_web_html
        web_start, web_end = _resolve_request_range({"start": "2020-01-12", "end": "2020-01-06"})
        assert web_start == weekly_start
        assert web_end == weekly_end
        draft_for_audit = {
            "stock": {
                "symbol": "AUDIT",
                "market": "TEST",
                "name": "Audit Test",
                "core_business": "Audit fixture business.",
                "equity_structure": "Audit fixture equity structure.",
                "stock_character": "Audit fixture stock character.",
                "notable_history": "Audit fixture notable history.",
            },
            "sources": [
                {
                    "key": "official",
                    "source_type": "annual_report",
                    "title": "Audit Test Annual Report",
                    "publisher": "SEC",
                    "content_excerpt": "Revenue was 123 million. Gross margin was 45%.",
                }
            ],
            "sectors": [
                {
                    "path": ["Audit", "Official"],
                    "relation_type": "main",
                    "confidence": 0.8,
                    "source_key": "official",
                }
            ],
            "knowledge_items": [
                {
                    "knowledge_type": "business",
                    "content": "Revenue was 123 million.",
                    "confidence": 0.8,
                    "source_key": "official",
                }
            ],
            "user_insights": [],
        }
        source_facts = extract_source_facts(draft_for_audit)
        audit = audit_research_draft(draft_for_audit, source_facts)
        assert audit.status == "pass"
        hsi_draft = {
            **draft_for_audit,
            "sources": [
                {
                    "key": "official",
                    "source_type": "index_review",
                    "title": "Hang Seng Index Review Results",
                    "publisher": "Hang Seng Indexes Company",
                    "content_excerpt": "The review included 123 eligible securities.",
                }
            ],
            "knowledge_items": [
                {
                    "knowledge_type": "research_source",
                    "content": "The review included 123 eligible securities.",
                    "confidence": 0.8,
                    "source_key": "official",
                }
            ],
        }
        hsi_audit = audit_research_draft(hsi_draft)
        assert hsi_audit.status == "pass"
        trusted_hk_supplement_draft = {
            **draft_for_audit,
            "sources": [
                {
                    "key": "hkex",
                    "source_type": "exchange_profile",
                    "title": "HKEX Securities Quote",
                    "publisher": "HKEX",
                    "content_excerpt": "Meituan is listed on The Stock Exchange of Hong Kong.",
                },
                {
                    "key": "hsi",
                    "source_type": "index_factsheet",
                    "title": "Hang Seng TECH Index Factsheet",
                    "publisher": "Hang Seng Indexes Company Limited",
                    "content_excerpt": "The factsheet included Meituan as a constituent.",
                },
                {
                    "key": "samr",
                    "source_type": "regulatory_action",
                    "title": "SAMR Antitrust Penalty",
                    "publisher": "河北省市场监督管理局（转载国家市场监督管理总局信息）",
                    "content_excerpt": "The regulator published an antitrust administrative penalty.",
                },
            ],
            "sectors": [
                {
                    "path": ["Audit", "Trusted HK"],
                    "relation_type": "main",
                    "confidence": 0.8,
                    "source_key": "hkex",
                }
            ],
            "knowledge_items": [
                {
                    "knowledge_type": "research_source",
                    "content": "Trusted HK exchange, index and regulator sources should not trigger non-official warnings.",
                    "confidence": 0.8,
                    "source_key": "hkex",
                }
            ],
        }
        trusted_hk_audit = audit_research_draft(trusted_hk_supplement_draft)
        assert trusted_hk_audit.status == "pass"
        issuer_ir_draft = {
            **draft_for_audit,
            "sources": [
                {
                    "key": "issuer_ir",
                    "source_type": "earnings_release",
                    "title": "Issuer Q1 Results",
                    "publisher": "Vertiv Investor Relations / PRNewswire",
                    "content_excerpt": "Revenue was 123 million. Gross margin was 45%.",
                }
            ],
            "sectors": [
                {
                    "path": ["Audit", "Issuer IR"],
                    "relation_type": "main",
                    "confidence": 0.8,
                    "source_key": "issuer_ir",
                }
            ],
            "knowledge_items": [
                {
                    "knowledge_type": "research_source",
                    "content": "Issuer investor relations sources should be treated as official company sources.",
                    "confidence": 0.8,
                    "source_key": "issuer_ir",
                }
            ],
        }
        issuer_ir_audit = audit_research_draft(issuer_ir_draft)
        assert issuer_ir_audit.status == "pass"
        issuer_host_draft = {
            **draft_for_audit,
            "sources": [
                {
                    "key": "issuer_home",
                    "source_type": "company_profile",
                    "title": "Issuer Company Profile",
                    "url": "https://www.vertiv.com/en-us/",
                    "publisher": "Vertiv Holdings Co",
                    "content_excerpt": "Revenue was 123 million. Gross margin was 45%.",
                }
            ],
            "sectors": [
                {
                    "path": ["Audit", "Issuer Host"],
                    "relation_type": "main",
                    "confidence": 0.8,
                    "source_key": "issuer_home",
                }
            ],
            "knowledge_items": [
                {
                    "knowledge_type": "research_source",
                    "content": "Issuer host-matched company sources should be treated as official.",
                    "confidence": 0.8,
                    "source_key": "issuer_home",
                }
            ],
        }
        issuer_host_audit = audit_research_draft(issuer_host_draft)
        assert issuer_host_audit.status == "pass"
        issuer_cdn_draft = {
            **issuer_host_draft,
            "sources": [
                {
                    "key": "issuer_cdn",
                    "source_type": "investor_presentation",
                    "title": "Issuer Investor Presentation",
                    "url": "https://s205.q4cdn.com/554782763/files/doc_presentations/2026/presentation.pdf",
                    "publisher": "Vertiv Holdings Co",
                    "content_excerpt": "Revenue was 123 million. Gross margin was 45%.",
                }
            ],
            "sectors": [{**issuer_host_draft["sectors"][0], "source_key": "issuer_cdn"}],
            "knowledge_items": [{**issuer_host_draft["knowledge_items"][0], "source_key": "issuer_cdn"}],
        }
        issuer_cdn_audit = audit_research_draft(issuer_cdn_draft)
        assert issuer_cdn_audit.status == "pass"
        issuer_unknown_type_draft = {
            **issuer_host_draft,
            "sources": [
                {
                    "key": "issuer_unknown",
                    "source_type": "webcast",
                    "title": "Issuer Webcast",
                    "url": "https://investors.vertiv.com/events/default.aspx",
                    "publisher": "Vertiv Holdings Co",
                    "content_excerpt": "Revenue was 123 million. Gross margin was 45%.",
                }
            ],
            "sectors": [{**issuer_host_draft["sectors"][0], "source_key": "issuer_unknown"}],
            "knowledge_items": [{**issuer_host_draft["knowledge_items"][0], "source_key": "issuer_unknown"}],
        }
        issuer_unknown_type_audit = audit_research_draft(issuer_unknown_type_draft)
        assert issuer_unknown_type_audit.status == "pass"
        media_source_draft = {
            **issuer_host_draft,
            "sources": [
                {
                    "key": "media",
                    "source_type": "news",
                    "title": "Media Story",
                    "url": "https://www.reuters.com/markets/",
                    "publisher": "Reuters",
                    "content_excerpt": "Revenue was 123 million. Gross margin was 45%.",
                }
            ],
            "sectors": [{**issuer_host_draft["sectors"][0], "source_key": "media"}],
            "knowledge_items": [{**issuer_host_draft["knowledge_items"][0], "source_key": "media"}],
        }
        media_source_audit = audit_research_draft(media_source_draft)
        assert media_source_audit.status == "needs_review"
        ytd_start, ytd_end, _ = _resolve_trade_review_range("今年以来")
        assert ytd_start.isoformat() == f"{today.year}-01-01"
        assert ytd_end == today
        historical_start = today - timedelta(days=40)
        historical_end = today - timedelta(days=30)
        historical_message = _render_performance_estimate(
            trade_snapshot=SimpleNamespace(
                start=historical_start.isoformat(),
                end=historical_end.isoformat(),
                fetched_at=datetime.now(ZoneInfo("Asia/Shanghai")),
                account_info={"total_assets": 1000, "market_val": 800, "cash": 200, "power": 100},
                deals=[],
            ),
            position_snapshot=SimpleNamespace(
                positions=[{"currency": "USD", "market_val": 800, "pl_val": 50}]
            ),
            cash_flow_snapshot=SimpleNamespace(cash_flows=[], errors=[]),
            positions_error=None,
            cash_flow_error=None,
            account_snapshot={"snapshot_date": today.isoformat()},
            account_snapshot_error=None,
            account_snapshots=[],
            account_snapshots_error=None,
            label=f"{historical_start.isoformat()} 至 {historical_end.isoformat()}",
        )
        assert "实时账户快照（截至数据时间，非查询区间）" in historical_message
        assert "今日实时账户快照已保存/更新" in historical_message
        assert "查询区间暂未读取到已保存的历史账户快照" in historical_message
        assert "实时持仓浮盈亏（截至数据时间，非查询区间）" in historical_message
        hkex_urls = _hkex_title_search_urls(symbol="01810", company_name="小米集团-W")
        assert "stockId=190371" in hkex_urls[0]
        meituan_hkex_urls = _hkex_title_search_urls(symbol="03690", company_name="美团-W")
        assert "stockId=198419" in meituan_hkex_urls[0]
        assert _extract_hkex_stock_ids('href="/search/titlesearch.xhtml?stockId=1131"') == ["1131"]
        assert _classify_hkex_title("Financial Statements/ESG Information - Annual Report") == ("annual_report", 0)
        assert _classify_hkex_title("Announcements and Notices - Quarterly Results") == ("quarterly_results", 2)
        assert _classify_hkex_title("公告及通告 - 年度業績公告") == ("annual_results", 1)
        assert _classify_hkex_title("公告及通告 - 盈利警告") == ("announcement", 4)
        assert _classify_hkex_title("Voluntary Announcement - HK$20 Billion On-Market Share Repurchase Program") == (
            "announcement",
            4,
        )
        assert _classify_issuer_ir_title("2025 年报") == ("annual_report", 0)
        assert _classify_issuer_ir_title("Profit Warning") == ("profit_warning", 4)
        assert _classify_issuer_ir_title("Discloseable Transaction - Acquisition of All Issued Shares") == (
            "transaction_announcement",
            5,
        )
        assert _classify_issuer_ir_title("Global Offering Prospectus") == ("prospectus", 7)
        assert _extract_report_year("二零二五年年报") == "2025"
        assert _issuer_ir_key(
            "annual_report",
            "二零二五年年报",
            "https://ir.xajuzi.com/resources/uploads/20260429/2049471183291846656.pdf",
            0,
        ) == "issuer_ir_annual_report_2025_2049471183291846656"
        assert _issuer_ir_key(
            "annual_report",
            "二零二二年年报",
            "https://ir.xajuzi.com/resources/uploads/20240912/1834168936008593408.pdf",
            0,
        ) == "issuer_ir_annual_report_2022_1834168936008593408"
        assert _issuer_ir_key(
            "quarterly_results",
            "Announcement of the Results for the Three Months ended March 31, 2026",
            "https://media-meituan.todayir.com/202606011753301715997254_en.pdf",
            0,
        ) == "issuer_ir_quarterly_results_2026_202606011753301715997254"
        duplicate_sources = _dedupe_source_documents(
            [
                SourceDocument(
                    key="a",
                    source_type="annual_report",
                    title="2025 Annual Report",
                    url="https://example.invalid/report.pdf",
                    publisher="Issuer",
                    published_at="2026-04-24T00:00:00+08:00",
                    content_excerpt="Revenue was 123.",
                ),
                SourceDocument(
                    key="b",
                    source_type="annual_report",
                    title="2025 Annual Report PDF",
                    url="https://example.invalid/report.pdf#page=1",
                    publisher="Issuer",
                    published_at="2026-04-24T00:00:00+08:00",
                    content_excerpt="Revenue was 123.",
                ),
            ]
        )
        assert len(duplicate_sources) == 1
        pdf_links = _extract_pdf_links(
            '<a href="/resources/uploads/20260429/report.pdf">2025 年报</a>'
            ' https://ir.xajuzi.com/resources/uploads/20250923/interim-report.pdf',
            "https://ir.xajuzi.com/list-l3s05l87/index.html/1/10",
        )
        assert pdf_links[0]["url"] == "https://ir.xajuzi.com/resources/uploads/20260429/report.pdf"
        assert pdf_links[0]["title"] == "2025 年报"
        assert pdf_links[1]["url"] == "https://ir.xajuzi.com/resources/uploads/20250923/interim-report.pdf"
        fake_ir_html = (
            '<a href="/resources/uploads/20260429/annual-report.pdf">2025 年报</a>'
            '<a href="/resources/uploads/20250923/interim-report.pdf">2025 中期报告</a>'
        )
        fake_ir_client = SimpleNamespace(
            get=lambda _url: SimpleNamespace(text=fake_ir_html, raise_for_status=lambda: None)
        )
        ir_candidates = _fetch_hk_issuer_ir_candidates(fake_ir_client, symbol="02367")
        assert ir_candidates[0].source_type == "annual_report"
        assert ir_candidates[0].key == "issuer_ir_annual_report_2025_annual_report"
        assert ir_candidates[0].publisher == "巨子生物"
        fake_todayir_html = (
            '<section><h3>2025 Annual Report</h3>'
            '<a href="https://media-meituan.todayir.com/20260424065602168712120049_en.pdf">PDF</a></section>'
            '<section><h3>Announcement of the Results for the Three Months ended March 31, 2026</h3>'
            '<a href="https://media-meituan.todayir.com/20260601013460123456789012_en.pdf">PDF</a></section>'
            '<section><h3>Profit Warning</h3>'
            '<a href="https://media-meituan.todayir.com/20260213200801422012025140_en.pdf">View</a></section>'
        )
        fake_todayir_client = SimpleNamespace(
            get=lambda _url: SimpleNamespace(text=fake_todayir_html, raise_for_status=lambda: None)
        )
        meituan_candidates = _fetch_hk_issuer_ir_candidates(fake_todayir_client, symbol="03690")
        assert meituan_candidates[0].source_type == "annual_report"
        assert meituan_candidates[0].title == "2025 Annual Report"
        assert meituan_candidates[1].source_type == "quarterly_results"
        assert meituan_candidates[1].publisher == "Meituan"
        crowded_candidates = [
            FilingCandidate(
                key=f"annual_{year}",
                source_type="annual_report",
                title=f"{year} Annual Report",
                url=f"https://example.invalid/{year}.pdf",
                publisher="Issuer",
                published_at=f"{year}-04-01T00:00:00+08:00",
            )
            for year in range(2026, 2020, -1)
        ] + [
            FilingCandidate(
                key="q1_2026",
                source_type="quarterly_results",
                title="Announcement of the Results for the Three Months ended March 31, 2026",
                url="https://example.invalid/q1-2026.pdf",
                publisher="Issuer",
                published_at="2026-06-01T00:00:00+08:00",
            )
        ]
        selected_crowded_candidates = _select_hk_issuer_ir_candidates(crowded_candidates, limit=3)
        assert [candidate.source_type for candidate in selected_crowded_candidates] == [
            "annual_report",
            "annual_report",
            "quarterly_results",
        ]
        sec_candidates = [
            (
                0,
                "2024-10-01",
                FilingCandidate(
                    key="sec_10k_2024",
                    source_type="annual_report",
                    title="Issuer 10-K filed 2024-10-01",
                    url="https://www.sec.gov/Archives/edgar/data/1/old/old.htm",
                    publisher="SEC",
                    published_at="2024-10-01T00:00:00-04:00",
                ),
            ),
            (
                0,
                "2025-10-01",
                FilingCandidate(
                    key="sec_10k_2025",
                    source_type="annual_report",
                    title="Issuer 10-K filed 2025-10-01",
                    url="https://www.sec.gov/Archives/edgar/data/1/new/new.htm",
                    publisher="SEC",
                    published_at="2025-10-01T00:00:00-04:00",
                ),
            ),
            (
                1,
                "2026-03-01",
                FilingCandidate(
                    key="sec_10q_2026_q1",
                    source_type="quarterly_results",
                    title="Issuer 10-Q filed 2026-03-01",
                    url="https://www.sec.gov/Archives/edgar/data/1/q1/q1.htm",
                    publisher="SEC",
                    published_at="2026-03-01T00:00:00-04:00",
                ),
            ),
        ]
        selected_sec_candidates = _select_sec_recent_filing_candidates(sec_candidates)
        assert [candidate.key for candidate in selected_sec_candidates[:2]] == ["sec_10k_2025", "sec_10q_2026_q1"]
        assert "sec_10k_2024" not in {candidate.key for candidate in selected_sec_candidates}
        ixbrl_text = _extract_sec_ixbrl_text(
            """
            <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL">
              <body>
                <ix:header><ix:hidden>hidden taxonomy noise 999</ix:hidden></ix:header>
                <script>bad()</script>
                <div>Item 1. Business</div>
                <ix:nonNumeric contextRef="c1">Data center revenue increased.</ix:nonNumeric>
                <ix:nonFraction contextRef="c1" unitRef="usd">1234</ix:nonFraction>
              </body>
            </html>
            """
        )
        assert "hidden taxonomy noise" not in ixbrl_text
        assert "Data center revenue increased." in ixbrl_text
        assert "1234" in ixbrl_text
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
