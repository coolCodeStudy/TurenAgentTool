from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.analysis_provider import (
    generate_portfolio_analysis_with_openai,
    generate_stock_analysis_with_openai,
    route_command_intent_with_openai,
)
from investment_knowledge_mcp.display import build_stock_decision_card, render_stock_decision_card
from investment_knowledge_mcp.futu_provider import (
    FutuProviderError,
    get_futu_cash_flows,
    get_futu_positions,
    get_futu_trade_history,
    get_hk_ipo_list,
)
from investment_knowledge_mcp.futu_opend_control import (
    FutuOpenDControlError,
    ping_opend_telnet,
    relogin_opend,
    request_phone_verify_code,
    submit_phone_verify_code,
)
from investment_knowledge_mcp.kline_agent import DisabledHistoricalBarProvider, investigate_kline_behavior, parse_kline_command
from investment_knowledge_mcp.ops_client import (
    render_cloud_service_control,
    render_cloud_coding_status,
    render_cloud_system_status,
    render_recent_errors,
    render_service_logs,
)
from investment_knowledge_mcp.portfolio_analysis import (
    DEFAULT_CURRENCY_BY_MARKET,
    build_portfolio_analysis_context,
    render_portfolio_analysis_fallback,
)
from investment_knowledge_mcp.portfolio_graph import (
    build_portfolio_graph_queue,
    render_portfolio_graph_queue,
)
from investment_knowledge_mcp.research.audit import audit_research_draft, build_audit_markdown
from investment_knowledge_mcp.research.jobs import (
    ACTIVE_STATUSES,
    cancel_research_job,
    count_research_jobs,
    create_research_job,
    get_research_job,
    list_research_jobs_for_stock,
    list_research_jobs,
    requeue_research_jobs,
    update_research_job,
)
from investment_knowledge_mcp.research.pipeline import ResearchPipelineOptions, ResearchPipelineResult, run_single_stock_research
from investment_knowledge_mcp.research.source_facts import extract_source_facts
from investment_knowledge_mcp.research.validation import validate_research_draft
from investment_knowledge_mcp.system_status import render_ipo_reminder_status, render_system_status
from investment_knowledge_mcp.system_overview import render_system_overview
from investment_knowledge_mcp.stock_valuation import (
    build_valuation_artifact,
    load_latest_valuation_artifact,
    render_valuation_card,
    render_valuation_methods,
)
from investment_knowledge_mcp.weekly_review import build_weekly_review
from scripts.build_analysis_context import render_stock_context
from scripts.review_research_draft import build_review_markdown


DEFAULT_FX_TO_USD = {
    "USD": 1.0,
    "HKD": 1.0 / 7.8,
}
DEFAULT_PORTFOLIO_RESEARCH_BATCH_LIMIT = 1
DEFAULT_RESEARCH_JOB_REQUEUE_LIMIT = 1
MAX_RESEARCH_JOB_REQUEUE_LIMIT = 3
DEFAULT_MAX_ACTIVE_CODEX_RESEARCH_JOBS = 1
CHINESE_MONTHS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}
_MONTH_TEXT = r"(?:\d{1,2}|十[一二]?|[一二三四五六七八九])"
_MONTH_TOKEN_RE = re.compile(rf"(?<!\d){_MONTH_TEXT}\s*月份?")
_DATE_TOKEN_RE = re.compile(
    rf"(?:\d{{4}}\s*年\s*)?{_MONTH_TEXT}\s*月\s*\d{{1,2}}\s*[日号]?|"
    r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"
)


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str


PORTFOLIO_POSITION_COMMANDS = {
    "我的持仓",
    "我的仓位",
    "当前持仓",
    "当前仓位",
    "持仓",
    "仓位",
    "portfolio",
    "positions",
}

PORTFOLIO_ANALYSIS_COMMANDS = {
    "持仓分析",
    "仓位分析",
    "组合分析",
    "组合体检",
    "持仓复盘",
    "仓位复盘",
    "今天仓位怎么看",
    "今天持仓怎么看",
    "今天组合怎么看",
    "仓位怎么看",
    "持仓怎么看",
    "怎么看持仓",
    "怎么看我的持仓",
    "分析持仓",
    "分析我的持仓",
    "分析一下持仓",
    "分析一下我的持仓",
    "我的组合怎么看",
    "帮我分析持仓",
    "portfolio analysis",
}

PORTFOLIO_GRAPH_COMMANDS = {
    "持仓图谱",
    "持仓图谱队列",
    "组合图谱",
    "组合图谱队列",
    "图谱队列",
    "持仓知识图谱",
    "portfolio graph",
}

PORTFOLIO_RESEARCH_DRAFT_COMMANDS = {
    "全持仓研究草稿",
    "全持仓图谱草稿",
    "portfolio research drafts",
}

PORTFOLIO_GRAPH_BACKFILL_COMMANDS = {
    "持仓图谱补全",
    "补全持仓图谱",
    "全持仓图谱入库",
    "portfolio graph backfill",
}

RESEARCH_JOB_CREATE_COMMANDS = {
    "创建持仓研究任务",
    "创建全持仓研究任务",
    "全持仓研究任务",
    "portfolio research jobs",
    "create portfolio research jobs",
}

RESEARCH_JOB_LIST_COMMANDS = {
    "查看研究任务",
    "列出研究任务",
    "研究任务",
    "研究任务状态",
    "research jobs",
    "list research jobs",
}

RESEARCH_JOB_REQUEUE_COMMANDS = {
    "重排失败研究任务",
    "重试失败研究任务",
    "requeue failed research jobs",
}

SYSTEM_STATUS_COMMANDS = {
    "系统状态",
    "自检",
    "检查系统",
    "检查部署",
    "检查OpenD",
    "检查openD",
    "检查OpenAI",
    "检查openai",
    "status",
    "health",
}

SYSTEM_OVERVIEW_COMMANDS = {
    "系统总览",
    "总览",
    "控制台",
    "控制平面",
    "overview",
    "system overview",
}

FUTU_MAINTENANCE_QUERY_COMMANDS = {
    "富途状态",
    "OpenD状态",
    "opend状态",
    "富途控制状态",
}

IPO_REMINDER_STATUS_COMMANDS = {
    "IPO提醒状态",
    "ipo提醒状态",
    "新股提醒状态",
    "检查IPO提醒",
    "检查新股提醒",
    "ipo status",
}

TRADE_REVIEW_COMMANDS = {
    "交易记录",
    "交易复盘",
}

PERFORMANCE_ESTIMATE_COMMANDS = {
    "估算收益",
    "估算本月收益",
    "收益复盘",
    "月度收益",
    "本月收益",
}

WEEKLY_REVIEW_COMMANDS = {
    "本周复盘",
    "这周复盘",
    "本星期复盘",
    "这个星期复盘",
    "周复盘",
    "weekly review",
}

NEXT_WEEK_COMMANDS = {
    "查看下周节奏",
    "下周节奏",
    "next week",
}

TRADE_BACKFILL_COMMANDS = {
    "补全交易记录",
    "同步交易记录",
    "回补交易记录",
}

CODING_TASK_LIST_COMMANDS = {
    "开发任务",
    "查看开发任务",
    "编程任务",
    "查看编程任务",
    "coding tasks",
    "dev tasks",
}

WORKER_STATUS_COMMANDS = {
    "worker状态",
    "work状态",
    "worker status",
    "work status",
    "codex状态",
    "Codex状态",
    "开发worker状态",
    "开发任务状态",
    "开发状态",
    "云端开发状态",
}

CLOUD_SYSTEM_STATUS_COMMANDS = {
    "云端状态",
    "ECS状态",
    "ecs状态",
    "服务器状态",
    "云端系统状态",
    "线上状态",
    "生产状态",
    "cloud status",
}

RECENT_ERRORS_COMMANDS = {
    "最近错误",
    "最近报错",
    "云端错误",
    "线上错误",
    "查看错误",
    "查看最近错误",
    "recent errors",
}

RESEARCH_WORKER_STOP_COMMANDS = {
    "停止研究worker",
    "暂停研究worker",
    "停止研究任务worker",
    "stop research worker",
    "pause research worker",
}

RESEARCH_WORKER_START_COMMANDS = {
    "启动研究worker",
    "恢复研究worker",
    "启动研究任务worker",
    "start research worker",
    "resume research worker",
}

RESEARCH_WORKER_RESTART_COMMANDS = {
    "重启研究worker",
    "restart research worker",
}

SERVICE_LOG_COMMANDS = {
    "worker日志": "codex-worker",
    "codex日志": "codex-worker",
    "codex worker日志": "codex-worker",
    "research日志": "research-agent-worker",
    "研究worker日志": "research-agent-worker",
    "research worker日志": "research-agent-worker",
    "mcp日志": "mcp",
    "钉钉日志": "dingtalk-stream-bot",
    "dingtalk日志": "dingtalk-stream-bot",
    "IPO提醒日志": "ipo-reminder-scheduler",
    "ipo提醒日志": "ipo-reminder-scheduler",
    "ipo scheduler日志": "ipo-reminder-scheduler",
    "定时任务日志": "ipo-reminder-scheduler",
    "快照日志": "account-snapshot-scheduler",
    "账户快照日志": "account-snapshot-scheduler",
    "futu日志": "futu-opend",
    "opend日志": "futu-opend",
    "postgres日志": "postgres",
    "数据库日志": "postgres",
}


def handle_command(
    command: str,
    output_dir: Path | None = None,
    include_artifact_path: bool = True,
    disable_kline_live_provider: bool = False,
) -> CommandResult:
    cleaned = command.strip()
    if not cleaned:
        return CommandResult(ok=False, message=_help_text())

    output_dir = output_dir or Path("drafts")

    normalized = _normalize_natural_command(cleaned)
    if normalized != cleaned:
        return handle_command(
            normalized,
            output_dir=output_dir,
            include_artifact_path=include_artifact_path,
            disable_kline_live_provider=disable_kline_live_provider,
        )

    ambiguous_match = re.fullmatch(r"__AMBIGUOUS_STOCK__\s+(.+)", cleaned)
    if ambiguous_match:
        return CommandResult(ok=False, message=f"匹配到多个股票，请说得更具体一点：{ambiguous_match.group(1)}")

    kline_request = parse_kline_command(cleaned)
    if kline_request is not None:
        provider = DisabledHistoricalBarProvider() if disable_kline_live_provider else None
        return CommandResult(ok=True, message=investigate_kline_behavior(kline_request, provider=provider))

    stock_detail_match = re.fullmatch(
        r"(?:分析详情|查看详情|股票详情|inspect detail|analyze detail)\s+(\S+)\s+(\S+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if stock_detail_match:
        symbol, market = stock_detail_match.groups()
        return _handle_analyze_stock(
            symbol=symbol,
            market=market,
            output_dir=output_dir,
            include_artifact_path=include_artifact_path,
            detail=True,
        )

    stock_inspect_match = re.fullmatch(
        r"(?:查看股票|inspect|stock inspect)\s+(\S+)\s+(\S+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if stock_inspect_match:
        symbol, market = stock_inspect_match.groups()
        return _handle_stock_decision_card(symbol=symbol, market=market)

    stock_bootstrap_match = re.fullmatch(
        r"(?:创建股票档案|初始化股票|initialize stock profile)\s+(\S+)\s+(\S+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if stock_bootstrap_match:
        symbol, market = stock_bootstrap_match.groups()
        return _handle_bootstrap_stock_profile(symbol=symbol, market=market)

    decision_match = re.fullmatch(r"(?:决策|decision)\s+(.+)", cleaned, flags=re.IGNORECASE)
    if decision_match:
        target = _parse_stock_target(decision_match.group(1))
        if target is None:
            return CommandResult(ok=False, message="决策指令需要股票标的，例如：决策 US.INTC 或 决策 000660 KR")
        symbol, market = target
        return _handle_stock_decision_card(symbol=symbol, market=market)

    if cleaned.lower() in {"valuation methods", "value methods", "估值方法", "估值框架"}:
        return CommandResult(ok=True, message=render_valuation_methods())

    valuation_latest_match = re.fullmatch(
        r"(?:latest valuation|valuation latest|value latest|查看估值|最新估值)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if valuation_latest_match:
        target = _parse_stock_target(valuation_latest_match.group(1))
        if target is None:
            return CommandResult(ok=False, message="估值指令需要股票标的，例如：valuation US.INTC 或 估值 000660 KR")
        symbol, market = target
        return _handle_stock_valuation_latest(
            symbol=symbol,
            market=market,
            output_dir=output_dir,
            include_artifact_path=include_artifact_path,
        )

    valuation_match = re.fullmatch(r"(?:估值|valuation|value)\s+(.+)", cleaned, flags=re.IGNORECASE)
    if valuation_match:
        target = _parse_stock_target(valuation_match.group(1))
        if target is None:
            return CommandResult(ok=False, message="估值指令需要股票标的，例如：valuation US.INTC 或 估值 000660 KR")
        symbol, market = target
        return _handle_stock_valuation(
            symbol=symbol,
            market=market,
            output_dir=output_dir,
            command=cleaned,
            include_artifact_path=include_artifact_path,
        )

    stock_match = re.fullmatch(r"(?:分析|analyze)\s+(\S+)\s+(\S+)", cleaned, flags=re.IGNORECASE)
    if stock_match:
        symbol, market = stock_match.groups()
        return _handle_analyze_stock(
            symbol=symbol,
            market=market,
            output_dir=output_dir,
            include_artifact_path=include_artifact_path,
        )

    research_draft_match = re.fullmatch(r"(?:研究草稿|图谱草稿|research draft)\s+(\S+)\s+(\S+)", cleaned, flags=re.IGNORECASE)
    if research_draft_match:
        symbol, market = research_draft_match.groups()
        return _handle_research_draft(
            symbol=symbol,
            market=market,
            output_dir=output_dir,
            include_artifact_path=include_artifact_path,
        )

    research_job_match = re.fullmatch(r"(?:创建研究任务|create research job)\s+(\S+)\s+(\S+)", cleaned, flags=re.IGNORECASE)
    if research_job_match:
        symbol, market = research_job_match.groups()
        budget_error = _research_budget_error(provider="codex", requested=1)
        if budget_error:
            return CommandResult(ok=False, message=budget_error)
        try:
            job = _create_codex_research_job(symbol=symbol, market=market, source="command")
        except RuntimeError as exc:
            return CommandResult(ok=False, message=str(exc))
        return CommandResult(ok=True, message=_render_research_job_create_result([job], [], []))

    cancel_job_match = re.fullmatch(
        r"(?:取消研究任务|停止研究任务|cancel research job)\s+#?(\d+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if cancel_job_match:
        return _handle_cancel_research_job(int(cancel_job_match.group(1)))

    reaudit_job_match = re.fullmatch(
        r"(?:重新审核研究任务|重审研究任务|reaudit research job)\s+#?(\d+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if reaudit_job_match:
        return _handle_reaudit_research_job(int(reaudit_job_match.group(1)))

    if cleaned in {"查看候选心得", "候选心得", "list candidates", "candidates"}:
        return _handle_list_candidates()

    if cleaned in CODING_TASK_LIST_COMMANDS:
        return _handle_list_coding_tasks()

    if cleaned in WORKER_STATUS_COMMANDS:
        return _handle_worker_status()

    if cleaned in SYSTEM_OVERVIEW_COMMANDS:
        return CommandResult(ok=True, message=render_system_overview())

    if cleaned in CLOUD_SYSTEM_STATUS_COMMANDS:
        return CommandResult(ok=True, message=render_cloud_system_status())

    if cleaned in RECENT_ERRORS_COMMANDS:
        return CommandResult(ok=True, message=render_recent_errors())

    if cleaned in SERVICE_LOG_COMMANDS:
        return CommandResult(ok=True, message=render_service_logs(SERVICE_LOG_COMMANDS[cleaned]))

    task_events_match = re.fullmatch(
        r"(?:任务状态|任务事件|task events?)\s+(research|coding|deploy|snapshot|ipo|command)\s+#?(\d+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if task_events_match:
        task_type, task_id = task_events_match.groups()
        return _handle_task_events(task_type=task_type, task_id=int(task_id))

    if cleaned in RESEARCH_WORKER_STOP_COMMANDS:
        return CommandResult(ok=True, message=render_cloud_service_control("research-agent-worker", "stop"))

    if cleaned in RESEARCH_WORKER_START_COMMANDS:
        return CommandResult(ok=True, message=render_cloud_service_control("research-agent-worker", "start"))

    if cleaned in RESEARCH_WORKER_RESTART_COMMANDS:
        return CommandResult(ok=True, message=render_cloud_service_control("research-agent-worker", "restart"))

    service_log_match = re.fullmatch(
        r"(?:服务日志|查看服务日志|service logs?)\s+([a-zA-Z0-9_-]+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if service_log_match:
        return CommandResult(ok=True, message=render_service_logs(service_log_match.group(1)))

    coding_task_detail_match = re.fullmatch(
        r"(?:查看开发任务|开发任务详情|查看编程任务|编程任务详情|coding task|dev task)\s+#?(\d+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if coding_task_detail_match:
        return _handle_coding_task_detail(int(coding_task_detail_match.group(1)))

    retry_coding_task_match = re.fullmatch(
        r"(?:重试开发任务|重新运行开发任务|重跑开发任务|retry coding task|retry dev task)\s+#?(\d+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if retry_coding_task_match:
        return _handle_retry_coding_task(int(retry_coding_task_match.group(1)))

    if cleaned in SYSTEM_STATUS_COMMANDS:
        return CommandResult(ok=True, message=render_system_status())

    if cleaned in FUTU_MAINTENANCE_QUERY_COMMANDS:
        return _handle_futu_control_status()

    futu_verify_match = re.fullmatch(r"(?:富途验证码|OpenD验证码|opend验证码)\s+(\d{4,8})", cleaned, flags=re.IGNORECASE)
    if futu_verify_match:
        return _handle_futu_verify_code(futu_verify_match.group(1))

    if cleaned in {"请求富途验证码", "富途请求验证码", "OpenD请求验证码", "opend请求验证码"}:
        return _handle_futu_request_verify_code()

    if cleaned in {"富途登录", "修复富途", "富途登录修复", "OpenD登录", "opend登录"}:
        return _handle_futu_login_flow()

    if cleaned in {"富途重登录", "重登录富途", "OpenD重登录", "opend重登录"}:
        return _handle_futu_relogin()

    if cleaned in IPO_REMINDER_STATUS_COMMANDS:
        return CommandResult(ok=True, message=render_ipo_reminder_status())

    if cleaned in PORTFOLIO_ANALYSIS_COMMANDS:
        return _handle_portfolio_analysis()

    if cleaned in PORTFOLIO_RESEARCH_DRAFT_COMMANDS:
        return _handle_portfolio_research(output_dir=output_dir, auto_import=False)

    if cleaned in RESEARCH_JOB_CREATE_COMMANDS:
        return _handle_create_portfolio_research_jobs()

    if cleaned in RESEARCH_JOB_LIST_COMMANDS:
        jobs = list_research_jobs(status="all", limit=20)
        return CommandResult(ok=True, message=_render_research_jobs(jobs))

    requeue_limit = _match_research_job_requeue_limit(cleaned)
    if requeue_limit is not None:
        budget_error = _research_budget_error(provider="codex", requested=requeue_limit)
        if budget_error:
            return CommandResult(ok=False, message=budget_error)
        jobs = requeue_research_jobs(status="failed", limit=requeue_limit)
        return CommandResult(ok=True, message=f"已重排失败研究任务 {len(jobs)} 个，limit={requeue_limit}。")

    if cleaned in PORTFOLIO_GRAPH_BACKFILL_COMMANDS:
        return _handle_portfolio_research(output_dir=output_dir, auto_import=True)

    if cleaned in PORTFOLIO_GRAPH_COMMANDS:
        return _handle_portfolio_graph_queue()

    if cleaned in PORTFOLIO_POSITION_COMMANDS:
        return _handle_portfolio_positions()

    if cleaned in {"港股新股", "港股IPO", "港股ipo", "新股", "ipo", "IPO"}:
        return _handle_hk_ipos()

    weekly_review_match = _match_weekly_review_command(cleaned)
    if weekly_review_match is not None:
        return _handle_weekly_review(time_range_text=weekly_review_match)

    next_week_match = _match_next_week_command(cleaned)
    if next_week_match is not None:
        return _handle_weekly_review(time_range_text=next_week_match, next_week_only=True)

    trade_backfill_match = _match_trade_backfill_command(cleaned)
    if trade_backfill_match is not None:
        return _handle_trade_backfill(time_range_text=trade_backfill_match)

    performance_match = _match_performance_estimate_command(cleaned)
    if performance_match is not None:
        return _handle_performance_estimate(time_range_text=performance_match)

    trade_review_match = _match_trade_review_command(cleaned)
    if trade_review_match is not None:
        return _handle_trade_review(time_range_text=trade_review_match)

    confirm_match = re.fullmatch(r"(?:确认候选心得|confirm candidate)\s+(\d+)", cleaned, flags=re.IGNORECASE)
    if confirm_match:
        return _handle_confirm_candidate(int(confirm_match.group(1)))

    reject_match = re.fullmatch(r"(?:拒绝候选心得|reject candidate)\s+(\d+)", cleaned, flags=re.IGNORECASE)
    if reject_match:
        return _handle_reject_candidate(int(reject_match.group(1)))

    stock_insight_match = re.fullmatch(
        r"(?:记录个股心得|记录心得)\s+(\S+)\s+(\S+)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if stock_insight_match:
        symbol, market, insight = stock_insight_match.groups()
        return _handle_record_stock_insight(symbol=symbol, market=market, insight=insight)

    global_insight_match = re.fullmatch(
        r"(?:记录组合心得|记录策略心得)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if global_insight_match:
        target_type = "strategy" if cleaned.startswith("记录策略心得") else "portfolio"
        return _handle_record_global_insight(target_type=target_type, insight=global_insight_match.group(1))

    candidate_stock_match = re.fullmatch(
        r"(?:提出个股候选心得|候选个股心得)\s+(\S+)\s+(\S+)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if candidate_stock_match:
        symbol, market, insight = candidate_stock_match.groups()
        return _handle_propose_stock_candidate(symbol=symbol, market=market, insight=insight)

    global_candidate_match = re.fullmatch(
        r"(?:提出组合候选心得|候选组合心得|提出策略候选心得|候选策略心得)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if global_candidate_match:
        target_type = "strategy" if "策略" in cleaned[:10] else "portfolio"
        return _handle_propose_global_candidate(target_type=target_type, insight=global_candidate_match.group(1))

    coding_task_match = re.fullmatch(
        r"(?:创建开发任务|提出开发任务|创建编程任务|新建开发任务|开发任务|coding task|dev task)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if coding_task_match:
        return _handle_create_coding_task(coding_task_match.group(1))

    if cleaned in {"帮助", "help", "?"}:
        return CommandResult(ok=True, message=_help_text())

    routed_result = _handle_intent_routed_command(cleaned)
    if routed_result is not None:
        return routed_result

    return CommandResult(
        ok=False,
        message="无法识别这条指令。\n\n" + _help_text(),
    )


def is_query_command(command: str) -> bool:
    cleaned = command.strip()
    normalized = _normalize_natural_command(cleaned)
    heuristic_intent = _heuristic_route_intent(normalized)
    return bool(
        re.fullmatch(r"(?:分析|analyze)\s+\S+\s+\S+", normalized, flags=re.IGNORECASE)
        or parse_kline_command(normalized) is not None
        or re.fullmatch(r"(?:决策|decision)\s+(?:[A-Za-z]{1,5}\.[A-Za-z0-9._-]+|\S+\s+\S+)", normalized, flags=re.IGNORECASE)
        or re.fullmatch(
            r"(?:估值|valuation|value)\s+(?:[A-Za-z]{1,5}\.[A-Za-z0-9._-]+|\S+\s+\S+)",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:latest valuation|valuation latest|value latest|查看估值|最新估值)\s+(?:[A-Za-z]{1,5}\.[A-Za-z0-9._-]+|\S+\s+\S+)",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:查看股票|inspect|stock inspect)\s+\S+\s+\S+",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:分析详情|查看详情|股票详情|inspect detail|analyze detail)\s+\S+\s+\S+",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(r"(?:研究草稿|图谱草稿|research draft)\s+\S+\s+\S+", normalized, flags=re.IGNORECASE)
        or normalized
        in {
            "查看候选心得",
            "候选心得",
            "list candidates",
            "candidates",
            "帮助",
            "help",
            "?",
            "valuation methods",
            "value methods",
            "估值方法",
            "估值框架",
            *SYSTEM_STATUS_COMMANDS,
            *FUTU_MAINTENANCE_QUERY_COMMANDS,
            *IPO_REMINDER_STATUS_COMMANDS,
            *WORKER_STATUS_COMMANDS,
            *SYSTEM_OVERVIEW_COMMANDS,
            *CLOUD_SYSTEM_STATUS_COMMANDS,
            *RECENT_ERRORS_COMMANDS,
            *SERVICE_LOG_COMMANDS,
            *PORTFOLIO_POSITION_COMMANDS,
            *PORTFOLIO_ANALYSIS_COMMANDS,
            *PORTFOLIO_GRAPH_COMMANDS,
            *PORTFOLIO_RESEARCH_DRAFT_COMMANDS,
            *RESEARCH_JOB_LIST_COMMANDS,
            *TRADE_REVIEW_COMMANDS,
            *PERFORMANCE_ESTIMATE_COMMANDS,
            *WEEKLY_REVIEW_COMMANDS,
            *NEXT_WEEK_COMMANDS,
            *TRADE_BACKFILL_COMMANDS,
            "港股新股",
            "港股IPO",
            "港股ipo",
            "新股",
            "ipo",
            "IPO",
        }
        or heuristic_intent.get("intent")
        in {"portfolio_analysis", "portfolio_positions", "portfolio_graph", "system_status", "ipo_status", "trade_review"}
        or re.fullmatch(r"(?:服务日志|查看服务日志|service logs?)\s+[a-zA-Z0-9_-]+", normalized, flags=re.IGNORECASE)
        or re.fullmatch(
            r"(?:任务状态|任务事件|task events?)\s+(research|coding|deploy|snapshot|ipo|command)\s+#?\d+",
            normalized,
            flags=re.IGNORECASE,
        )
        or _match_weekly_review_command(normalized) is not None
        or _match_next_week_command(normalized) is not None
        or _extract_stock_query(normalized) is not None
        or normalized.startswith("__AMBIGUOUS_STOCK__")
    )


def is_maintenance_command(command: str) -> bool:
    cleaned = command.strip()
    normalized = _normalize_natural_command(cleaned)
    return bool(
        re.fullmatch(r"(?:富途验证码|OpenD验证码|opend验证码)\s+\d{4,8}", cleaned, flags=re.IGNORECASE)
        or cleaned in {"请求富途验证码", "富途请求验证码", "OpenD请求验证码", "opend请求验证码"}
        or cleaned in {"富途登录", "修复富途", "富途登录修复", "OpenD登录", "opend登录"}
        or cleaned in {"富途重登录", "重登录富途", "OpenD重登录", "opend重登录"}
        or normalized in RESEARCH_WORKER_STOP_COMMANDS
        or normalized in RESEARCH_WORKER_START_COMMANDS
        or normalized in RESEARCH_WORKER_RESTART_COMMANDS
    )


def is_research_write_command(command: str) -> bool:
    cleaned = command.strip()
    normalized = _normalize_natural_command(cleaned)
    return bool(
        normalized in PORTFOLIO_GRAPH_BACKFILL_COMMANDS
        or normalized in RESEARCH_JOB_CREATE_COMMANDS
        or re.fullmatch(
            r"(?:创建股票档案|初始化股票|initialize stock profile)\s+\S+\s+\S+",
            normalized,
            flags=re.IGNORECASE,
        )
        or _match_research_job_requeue_limit(normalized) is not None
        or re.fullmatch(r"(?:创建研究任务|create research job)\s+\S+\s+\S+", normalized, flags=re.IGNORECASE)
        or re.fullmatch(r"(?:取消研究任务|停止研究任务|cancel research job)\s+#?\d+", normalized, flags=re.IGNORECASE)
        or re.fullmatch(r"(?:重新审核研究任务|重审研究任务|reaudit research job)\s+#?\d+", normalized, flags=re.IGNORECASE)
    )


def is_candidate_write_command(command: str) -> bool:
    cleaned = command.strip()
    normalized = _normalize_natural_command(cleaned)
    return bool(
        re.fullmatch(
            r"(?:提出个股候选心得|候选个股心得)\s+\S+\s+\S+\s+.+",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:提出组合候选心得|候选组合心得|提出策略候选心得|候选策略心得)\s+.+",
            normalized,
            flags=re.IGNORECASE,
        )
        or _heuristic_route_intent(normalized).get("intent") == "memory_candidate"
    )


def is_coding_task_command(command: str) -> bool:
    cleaned = command.strip()
    normalized = _normalize_natural_command(cleaned)
    return bool(
        normalized in CODING_TASK_LIST_COMMANDS
        or re.fullmatch(
            r"(?:重试开发任务|重新运行开发任务|重跑开发任务|retry coding task|retry dev task)\s+#?\d+",
            normalized,
            flags=re.IGNORECASE,
        )
        or re.fullmatch(
            r"(?:创建开发任务|提出开发任务|创建编程任务|新建开发任务|开发任务|coding task|dev task)\s+.+",
            normalized,
            flags=re.IGNORECASE,
        )
        or _heuristic_route_intent(normalized).get("intent") == "coding_task"
    )


def _handle_analyze_stock(
    symbol: str,
    market: str,
    output_dir: Path,
    include_artifact_path: bool,
    detail: bool = False,
) -> CommandResult:
    context = repository.get_stock_context(symbol=symbol, market=market)
    if not context.get("stock"):
        return CommandResult(ok=False, message=f"未找到股票：{symbol} {market}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol.upper()}_{market.upper()}_analysis_context.md"
    output_path.write_text(render_stock_context(context) + "\n", encoding="utf-8")

    if not detail:
        card = build_stock_decision_card(context, latest_research_job=_latest_research_job(symbol, market))
        footer = _analysis_footer(
            context=context,
            output_path=output_path,
            include_artifact_path=include_artifact_path,
        )
        return CommandResult(
            ok=True,
            message=render_stock_decision_card(card) + "\n\n" + footer,
        )

    fallback_analysis = _render_stock_brief_analysis(context)
    analysis = _generate_stock_analysis(context=context, fallback=fallback_analysis)
    footer = _analysis_footer(
        context=context,
        output_path=output_path,
        include_artifact_path=include_artifact_path,
    )
    return CommandResult(
        ok=True,
        message=analysis + "\n\n" + footer,
    )


def _handle_stock_decision_card(symbol: str, market: str) -> CommandResult:
    context = repository.get_stock_context(symbol=symbol, market=market)
    if not context.get("stock"):
        return CommandResult(ok=False, message=f"未找到股票：{symbol} {market}")
    if _stock_context_needs_research(context):
        normalized_symbol = symbol.strip().upper()
        normalized_market = market.strip().upper()
        return CommandResult(
            ok=False,
            message=(
                f"{normalized_market}.{normalized_symbol} 目前只有最小股票档案，信息量不足，不能生成有价值的决策卡。\n"
                f"请先运行：创建研究任务 {normalized_symbol} {normalized_market}\n"
                "研究任务导入事实后，再运行决策命令。"
            ),
        )
    card = build_stock_decision_card(context, latest_research_job=_latest_research_job(symbol, market))
    return CommandResult(ok=True, message=render_stock_decision_card(card))


def _handle_stock_valuation(
    symbol: str,
    market: str,
    output_dir: Path,
    command: str,
    include_artifact_path: bool,
) -> CommandResult:
    context = repository.get_stock_context(symbol=symbol, market=market)
    if not context.get("stock"):
        return CommandResult(ok=False, message=f"未找到股票：{symbol} {market}")
    packet, _ = build_valuation_artifact(
        context,
        symbol=symbol,
        market=market,
        output_dir=output_dir,
        command=command,
    )
    return CommandResult(ok=True, message=render_valuation_card(packet, include_artifact_path=include_artifact_path))


def _handle_stock_valuation_latest(
    symbol: str,
    market: str,
    output_dir: Path,
    include_artifact_path: bool,
) -> CommandResult:
    result = load_latest_valuation_artifact(symbol=symbol, market=market, output_dir=output_dir)
    if result is None:
        return CommandResult(
            ok=False,
            message=f"未找到已保存的估值 artifact：{market.strip().upper()}.{symbol.strip().upper()}。请先运行：valuation {market.strip().upper()}.{symbol.strip().upper()}",
        )
    packet, path = result
    packet["artifact_path"] = packet.get("artifact_path") or str(path)
    return CommandResult(ok=True, message=render_valuation_card(packet, include_artifact_path=include_artifact_path))


def _handle_bootstrap_stock_profile(symbol: str, market: str) -> CommandResult:
    normalized_symbol = symbol.strip().upper()
    normalized_market = market.strip().upper()
    if not normalized_symbol or not normalized_market:
        return CommandResult(ok=False, message="创建股票档案需要股票代码和市场，例如：创建股票档案 MSTR US")

    stock = repository.upsert_stock_profile(
        symbol=normalized_symbol,
        market=normalized_market,
        name=f"{normalized_market}.{normalized_symbol}",
        core_business=(
            "Minimal profile initialized from Command Workbench. "
            "Run a research job or add facts before treating analysis as complete."
        ),
        stock_character="Needs research.",
        notable_history="Initialized by Command Workbench missing-stock recovery.",
    )
    return CommandResult(
        ok=True,
        message=(
            f"已创建最小股票档案：{stock['market']}.{stock['symbol']}。\n"
            f"下一步可以重新预览并运行：决策 {stock['market']}.{stock['symbol']}。\n"
            "这个档案只解决可操作入口，不代表已经完成公司基本面研究。"
        ),
    )


def _latest_research_job(symbol: str, market: str) -> dict[str, Any] | None:
    jobs = list_research_jobs_for_stock(symbol=symbol, market=market, limit=1)
    return jobs[0] if jobs else None


def _stock_context_needs_research(context: dict[str, Any]) -> bool:
    stock = context.get("stock") or {}
    if not stock:
        return False
    knowledge_count = len(context.get("stock_knowledge") or context.get("knowledge_items") or [])
    source_count = len(context.get("sources") or [])
    marker_text = " ".join(
        str(stock.get(field) or "")
        for field in ("core_business", "stock_character", "notable_history")
    ).lower()
    minimal_marker = (
        "minimal profile initialized from command workbench" in marker_text
        or "needs research" in marker_text
        or "missing-stock recovery" in marker_text
    )
    return minimal_marker and knowledge_count == 0 and source_count == 0


def _handle_research_draft(
    symbol: str,
    market: str,
    output_dir: Path,
    include_artifact_path: bool,
) -> CommandResult:
    result = run_single_stock_research(
        symbol=symbol,
        market=market,
        company_name=None,
        options=ResearchPipelineOptions(
            output_dir=output_dir,
            provider="none",
            auto_confirm_facts=False,
            auto_import=False,
            refresh=True,
        ),
    )
    return CommandResult(ok=result.status not in {"failed"}, message=_render_research_result(result, include_artifact_path))


def _handle_reaudit_research_job(job_id: int) -> CommandResult:
    job = get_research_job(job_id)
    if job is None:
        return CommandResult(ok=False, message=f"研究任务不存在：#{job_id}")

    symbol = str(job.get("symbol") or "").upper()
    market = str(job.get("market") or "").upper()
    artifact_dir_text = str(job.get("artifact_dir") or "")
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), dict) else {}
    draft_path_text = str(artifacts.get("draft_path") or "")
    if not draft_path_text and artifact_dir_text:
        draft_path_text = str(Path(artifact_dir_text) / f"{symbol}_{market}_research_draft.json")
    artifact_draft = artifacts.get("draft_json") if isinstance(artifacts.get("draft_json"), dict) else None
    if not draft_path_text and artifact_draft is None:
        return CommandResult(ok=False, message=f"研究任务 #{job_id} 没有 draft_path，无法重新审核。")

    draft_path = Path(draft_path_text) if draft_path_text else None
    fallback_job_id = None
    if draft_path is None or not draft_path.exists():
        fallback = _find_existing_reaudit_artifact(job_id=job_id, symbol=symbol, market=market)
        if fallback is None and artifact_draft is None:
            return CommandResult(ok=False, message=f"研究任务 #{job_id} 草稿文件不存在：{draft_path}")
        if fallback is not None:
            fallback_job, draft_path = fallback
            fallback_job_id = int(fallback_job["id"])
            fallback_artifacts = fallback_job.get("artifacts") if isinstance(fallback_job.get("artifacts"), dict) else {}
            artifact_dir_text = str(fallback_job.get("artifact_dir") or draft_path.parent)
            artifacts = {**artifacts, **fallback_artifacts, "draft_path": str(draft_path)}
            artifact_draft = artifacts.get("draft_json") if isinstance(artifacts.get("draft_json"), dict) else artifact_draft

    if draft_path is not None and draft_path.exists():
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
    elif artifact_draft is not None:
        draft = json.loads(json.dumps(artifact_draft, ensure_ascii=False))
    else:
        return CommandResult(ok=False, message=f"研究任务 #{job_id} 没有可用草稿内容，无法重新审核。")
    if not isinstance(draft, dict):
        return CommandResult(ok=False, message=f"研究任务 #{job_id} 草稿不是 JSON object。")
    draft["user_insights"] = []
    if draft_path is None and artifact_dir_text:
        draft_path = Path(artifact_dir_text) / f"{symbol}_{market}_research_draft.json"
    if draft_path is not None:
        draft_path.parent.mkdir(parents=True, exist_ok=True)
        draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stock = draft.get("stock") if isinstance(draft.get("stock"), dict) else {}
    symbol = str(job.get("symbol") or stock.get("symbol") or "").upper()
    market = str(job.get("market") or stock.get("market") or "").upper()
    artifact_dir = Path(artifact_dir_text) if artifact_dir_text else (draft_path.parent if draft_path is not None else Path("drafts") / "research_jobs" / f"job_{job_id}_{symbol}_{market}")
    source_facts_path = Path(str(artifacts.get("source_facts_path") or artifact_dir / f"{symbol}_{market}_source_facts.json"))
    audit_path = Path(str(artifacts.get("audit_path") or artifact_dir / f"{symbol}_{market}_audit_report.md"))
    review_path = Path(str(artifacts.get("review_path") or artifact_dir / f"{symbol}_{market}_graph_review.md"))

    source_facts = extract_source_facts(draft)
    validation = validate_research_draft(draft)
    audit = audit_research_draft(draft, source_facts=source_facts)
    audit_markdown = build_audit_markdown(draft, source_facts, audit)
    review_markdown = build_review_markdown(draft, draft_path or Path(f"{symbol}_{market}_research_draft.json"))
    source_facts_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    source_facts_path.write_text(json.dumps(source_facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit_path.write_text(audit_markdown, encoding="utf-8")
    review_path.write_text(review_markdown, encoding="utf-8")

    errors = list(validation.errors) + list(audit.errors)
    imported_stock_id = None
    if errors:
        status = "failed"
        summary = "draft failed validation/audit after re-audit"
    elif bool(job.get("auto_import")) and audit.status == "pass":
        imported = repository.import_stock_research_draft(draft=draft, confirmed_by_user=True)
        imported_stock_id = int(imported["stock"]["id"])
        status = "imported"
        summary = "draft re-audited and imported"
    elif bool(job.get("auto_import")) and audit.status == "needs_review" and bool(job.get("import_needs_review")):
        imported = repository.import_stock_research_draft(draft=draft, confirmed_by_user=True)
        imported_stock_id = int(imported["stock"]["id"])
        status = "imported"
        summary = "needs_review draft imported by job setting after re-audit"
    elif audit.status == "needs_review":
        status = "needs_review"
        summary = "draft re-audited but still needs review"
    else:
        status = "drafted"
        summary = f"draft re-audited with audit_status={audit.status}"

    new_artifacts = {
        **artifacts,
        "draft_path": str(draft_path) if draft_path is not None else None,
        "source_facts_path": str(source_facts_path),
        "audit_path": str(audit_path),
        "review_path": str(review_path),
        "imported_stock_id": imported_stock_id,
        "audit_status": audit.status,
        "draft_json": draft,
        "source_facts_json": source_facts,
        "audit_json": audit.to_dict(),
        "audit_markdown": audit_markdown,
        "review_markdown": review_markdown,
        "errors": errors,
        "warnings": list(validation.warnings) + list(audit.warnings),
    }
    updated = update_research_job(
        job_id=job_id,
        status=status,
        result_summary=summary,
        error="; ".join(errors) if errors else None,
        artifact_dir=str(artifact_dir),
        artifacts=new_artifacts,
        source_discovery=job.get("source_discovery") if isinstance(job.get("source_discovery"), dict) else None,
        worker_log=f"command re-audited research job status={status} audit={audit.status}",
    )

    lines = [
        f"研究任务 #{job_id} 已重新审核：{updated['symbol']} {updated['market']}",
        f"- 状态：{status}",
        f"- 审核：{audit.status}",
        f"- errors：{len(errors)}",
        f"- warnings：{len(new_artifacts['warnings'])}",
    ]
    if imported_stock_id is not None:
        lines.append(f"- 已导入 stock_id：{imported_stock_id}")
    if fallback_job_id is not None:
        lines.append(f"- 使用可用草稿：job #{fallback_job_id}")
    return CommandResult(ok=status != "failed", message="\n".join(lines))


def _find_existing_reaudit_artifact(
    *,
    job_id: int,
    symbol: str,
    market: str,
) -> tuple[dict[str, Any], Path] | None:
    for candidate in list_research_jobs_for_stock(symbol=symbol, market=market, limit=20):
        if int(candidate["id"]) == job_id:
            continue
        artifacts = candidate.get("artifacts") if isinstance(candidate.get("artifacts"), dict) else {}
        draft_path_text = str(artifacts.get("draft_path") or "")
        if not draft_path_text and candidate.get("artifact_dir"):
            draft_path_text = str(Path(str(candidate["artifact_dir"])) / f"{symbol}_{market}_research_draft.json")
        if draft_path_text:
            draft_path = Path(draft_path_text)
            if draft_path.exists():
                return candidate, draft_path
    return None


def _handle_cancel_research_job(job_id: int) -> CommandResult:
    cancelled = cancel_research_job(job_id, reason="cancelled by command")
    if cancelled is None:
        job = get_research_job(job_id)
        if job is None:
            return CommandResult(ok=False, message=f"研究任务不存在：#{job_id}")
        return CommandResult(ok=False, message=f"研究任务 #{job_id} 当前状态是 {job.get('status')}，不能取消。")
    return CommandResult(
        ok=True,
        message=f"已取消研究任务 #{cancelled['id']}：{cancelled['symbol']} {cancelled['market']}。",
    )


def _handle_portfolio_research(output_dir: Path, auto_import: bool) -> CommandResult:
    try:
        payload = get_futu_positions()
    except FutuProviderError as exc:
        return CommandResult(ok=False, message=f"读取富途持仓失败，无法生成研究草稿：{exc}")

    positions = []
    for position in _positions_from_snapshot(payload):
        try:
            qty = float(position.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty > 0:
            positions.append(position)

    results: list[ResearchPipelineResult] = []
    batch_limit = _portfolio_research_batch_limit()
    processed_new = 0
    for position in positions:
        code = str(position.get("code") or "")
        if "." in code:
            market, symbol = code.split(".", 1)
        else:
            market, symbol = "", code
        market = market.upper()
        symbol = symbol.upper()
        if _stock_exists(symbol=symbol, market=market):
            results.append(
                ResearchPipelineResult(
                    symbol=symbol,
                    market=market,
                    status="skipped_existing",
                    message=f"{symbol} {market} already exists in knowledge base.",
                )
            )
            continue
        if batch_limit > 0 and processed_new >= batch_limit:
            results.append(
                ResearchPipelineResult(
                    symbol=symbol,
                    market=market,
                    status="queued",
                    message="not processed in this batch",
                )
            )
            continue
        result = run_single_stock_research(
            symbol=symbol,
            market=market,
            company_name=position.get("stock_name"),
            options=ResearchPipelineOptions(
                output_dir=output_dir,
                provider="none",
                auto_confirm_facts=auto_import,
                auto_import=auto_import,
                import_needs_review=False,
                refresh=False,
            ),
        )
        results.append(result)
        processed_new += 1

    return CommandResult(ok=True, message=_render_portfolio_research_results(results, auto_import=auto_import))


def _handle_create_portfolio_research_jobs() -> CommandResult:
    try:
        payload = get_futu_positions()
    except FutuProviderError as exc:
        return CommandResult(ok=False, message=f"读取富途持仓失败，无法创建研究任务：{exc}")

    created: list[dict[str, Any]] = []
    skipped_existing: list[dict[str, Any]] = []
    skipped_invalid: list[dict[str, Any]] = []
    for position in _positions_from_snapshot(payload):
        try:
            qty = float(position.get("qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0:
            continue
        code = str(position.get("code") or "")
        if "." not in code:
            skipped_invalid.append({"code": code, "reason": "missing market prefix"})
            continue
        market, symbol = code.split(".", 1)
        market = market.upper()
        symbol = symbol.upper()
        if _stock_exists(symbol=symbol, market=market):
            skipped_existing.append({"symbol": symbol, "market": market, "name": position.get("stock_name")})
            continue
        budget_error = _research_budget_error(provider="codex", requested=len(created) + 1)
        if budget_error:
            skipped_invalid.append({"code": code, "reason": budget_error})
            continue
        try:
            created.append(
                _create_codex_research_job(
                    symbol=symbol,
                    market=market,
                    name=position.get("stock_name"),
                    source="command",
                    refresh=False,
                )
            )
        except RuntimeError as exc:
            skipped_invalid.append({"code": code, "reason": str(exc)})
            continue

    return CommandResult(ok=True, message=_render_research_job_create_result(created, skipped_existing, skipped_invalid))


def _create_codex_research_job(
    *,
    symbol: str,
    market: str,
    name: str | None = None,
    source: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    return create_research_job(
        symbol=symbol,
        market=market,
        name=name,
        provider="codex",
        source_policy="broad_search",
        auto_import=True,
        import_needs_review=False,
        refresh=refresh,
        source=source,
        execution_location="cloud_worker",
        created_from="command_router",
    )


def _research_budget_error(provider: str, requested: int = 1) -> str | None:
    if provider != "codex":
        return None
    max_active = _max_active_codex_research_jobs()
    if max_active < 0:
        return None
    active = count_research_jobs(statuses=ACTIVE_STATUSES, provider="codex")
    if active + max(0, requested) > max_active:
        return (
            "Codex research budget gate 已阻止创建/重排任务："
            f"当前 active={active}，requested={requested}，max_active={max_active}。"
            "请先查看研究任务、取消/完成现有任务，或临时调整 RESEARCH_CODEX_MAX_ACTIVE_JOBS。"
        )
    return None


def _max_active_codex_research_jobs() -> int:
    value = os.environ.get("RESEARCH_CODEX_MAX_ACTIVE_JOBS", "").strip()
    if not value:
        return DEFAULT_MAX_ACTIVE_CODEX_RESEARCH_JOBS
    try:
        return int(value)
    except ValueError:
        return DEFAULT_MAX_ACTIVE_CODEX_RESEARCH_JOBS


def _portfolio_research_batch_limit() -> int:
    value = os.environ.get("PORTFOLIO_RESEARCH_BATCH_LIMIT", "").strip()
    if not value:
        return DEFAULT_PORTFOLIO_RESEARCH_BATCH_LIMIT
    try:
        return max(0, int(value))
    except ValueError:
        return DEFAULT_PORTFOLIO_RESEARCH_BATCH_LIMIT


def _match_research_job_requeue_limit(command: str) -> int | None:
    if command in RESEARCH_JOB_REQUEUE_COMMANDS:
        return DEFAULT_RESEARCH_JOB_REQUEUE_LIMIT

    match = re.fullmatch(
        r"(?:重排失败研究任务|重试失败研究任务|requeue failed research jobs)\s+(\d{1,3})",
        command,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    return max(1, min(int(match.group(1)), MAX_RESEARCH_JOB_REQUEUE_LIMIT))


def _stock_exists(symbol: str, market: str) -> bool:
    try:
        return bool(repository.search_stock(symbol=symbol, market=market).get("stock"))
    except Exception:
        return False


def _positions_from_snapshot(payload: Any) -> list[dict[str, Any]]:
    if hasattr(payload, "positions"):
        positions = getattr(payload, "positions")
        return list(positions) if isinstance(positions, list) else []
    if isinstance(payload, dict):
        positions = payload.get("positions") or []
        return list(positions) if isinstance(positions, list) else []
    return []


def _render_research_result(result: ResearchPipelineResult, include_artifact_path: bool) -> str:
    lines = [
        f"研究草稿：{result.symbol} {result.market}",
        f"- 状态：{result.status}",
        f"- 审核：{result.audit_status or 'n/a'}",
    ]
    if result.message:
        lines.append(f"- 说明：{result.message}")
    if include_artifact_path:
        if result.draft_path:
            lines.append(f"- 草稿：{result.draft_path}")
        if result.review_path:
            lines.append(f"- 审阅：{result.review_path}")
        if result.audit_path:
            lines.append(f"- 审核：{result.audit_path}")
    if result.errors:
        lines.append("- 错误：" + "；".join(result.errors[:3]))
    if result.warnings:
        lines.append("- 提醒：" + "；".join(result.warnings[:3]))
    return "\n".join(lines)


def _render_portfolio_research_results(results: list[ResearchPipelineResult], auto_import: bool) -> str:
    imported = [item for item in results if item.status == "imported"]
    skipped = [item for item in results if item.status == "skipped_existing"]
    drafted = [item for item in results if item.status == "drafted"]
    needs_review = [item for item in results if item.status == "needs_review"]
    failed = [item for item in results if item.status in {"failed", "failed_audit"}]
    queued = [item for item in results if item.status == "queued"]
    title = "持仓图谱补全" if auto_import else "全持仓研究草稿"
    lines = [
        f"{title}结果：",
        f"- 总数：{len(results)}",
        f"- 已导入：{len(imported)}",
        f"- 已跳过：{len(skipped)}",
        f"- 已生成草稿：{len(drafted)}",
        f"- 需人工复核：{len(needs_review)}",
        f"- 失败：{len(failed)}",
        f"- 待下轮：{len(queued)}",
    ]
    if imported:
        lines.append("- 导入：" + "、".join(f"{item.symbol} {item.market}" for item in imported[:8]))
    if needs_review:
        lines.append("- 需复核：" + "、".join(f"{item.symbol} {item.market}" for item in needs_review[:8]))
    if failed:
        lines.append("- 失败：" + "、".join(f"{item.symbol} {item.market}: {item.message}" for item in failed[:5]))
    if queued:
        lines.append("- 待下轮：" + "、".join(f"{item.symbol} {item.market}" for item in queued[:8]))
    return "\n".join(lines)


def _render_research_job_create_result(
    created: list[dict[str, Any]],
    skipped_existing: list[dict[str, Any]],
    skipped_invalid: list[dict[str, Any]],
) -> str:
    lines = [
        "Codex 研究任务已创建（默认由 cloud_worker 执行）：",
        f"- 新建/复用队列任务：{len(created)}",
        f"- 已入库跳过：{len(skipped_existing)}",
        f"- 无效持仓跳过：{len(skipped_invalid)}",
    ]
    if created:
        lines.append(
            "- 任务："
            + "、".join(
                f"#{item['id']} {item['symbol']} {item['market']} {item['status']} "
                f"{item.get('execution_location') or 'cloud_worker'}"
                for item in created[:10]
            )
        )
    if skipped_existing:
        lines.append("- 已跳过：" + "、".join(f"{item['symbol']} {item['market']}" for item in skipped_existing[:10]))
    return "\n".join(lines)


def _render_research_jobs(jobs: list[dict[str, Any]]) -> str:
    if not jobs:
        return "当前没有研究任务。"
    counts: dict[str, int] = {}
    for job in jobs:
        status = str(job.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    lines = [
        "研究任务状态：",
        "- 汇总：" + "，".join(f"{status} {count}" for status, count in sorted(counts.items())),
    ]
    for job in jobs[:20]:
        execution_location = job.get("execution_location") or "unknown"
        worker = job.get("worker_name") or "-"
        artifact_flags = job.get("artifacts") if isinstance(job.get("artifacts"), dict) else {}
        artifact_text = "/".join(key for key, exists in artifact_flags.items() if exists) or "none"
        import_status = job.get("import_status") or "-"
        token_usage = _format_token_usage(job.get("token_usage"))
        warnings_count = job.get("warnings_count", 0)
        title = (
            f"#{job['id']} {job['symbol']} {job['market']} {job.get('status')} "
            f"loc={execution_location} worker={worker}"
        )
        summary = job.get("result_summary") or job.get("error") or ""
        details = (
            f"provider={job.get('provider')} source_policy={job.get('source_policy')} "
            f"audit={job.get('audit_status') or 'unknown'} warnings={warnings_count} "
            f"token_usage={token_usage} artifacts={artifact_text} import={import_status}"
        )
        lines.append(f"- {title}；{details}" + (f"：{summary[:80]}" if summary else ""))
    return "\n".join(lines)


def _format_token_usage(token_usage: Any) -> str:
    if not isinstance(token_usage, dict) or not token_usage:
        return "unknown"
    for key in ("total_tokens", "total", "input_tokens", "output_tokens"):
        if token_usage.get(key) is not None:
            return str(token_usage[key])
    return "present"


def _analysis_footer(context: dict[str, Any], output_path: Path, include_artifact_path: bool) -> str:
    lines = []
    if include_artifact_path:
        lines.append(f"分析上下文已更新：{output_path}")
    else:
        lines.append("分析上下文已更新。")
    lines.append(
        f"数据覆盖：个股知识 {len(context.get('stock_knowledge') or [])} 条，"
        f"个股心得 {len(context.get('stock_insights') or [])} 条，"
        f"待确认候选 {_candidate_count(context)} 条。"
    )
    return "\n".join(lines)


def _generate_stock_analysis(context: dict[str, Any], fallback: str) -> str:
    try:
        analysis = generate_stock_analysis_with_openai(context)
    except Exception as exc:
        return fallback + f"\n\nOpenAI 分析暂时不可用，已使用本地模板分析。错误：{exc}"
    if not analysis:
        return fallback
    return analysis


def _handle_list_candidates() -> CommandResult:
    candidates = repository.list_candidate_insights(status="pending")
    if not candidates:
        return CommandResult(ok=True, message="暂无待确认候选心得。")

    lines = ["待确认候选心得："]
    for candidate in candidates:
        repeat_count = int(candidate.get("repeat_count") or 1)
        repeat_suffix = f" x{repeat_count}" if repeat_count > 1 else ""
        lines.append(
            f"- [{candidate['id']}{repeat_suffix}] {candidate['target_type']}:{candidate['target_id']} "
            f"{candidate['insight']}"
        )
    return CommandResult(ok=True, message="\n".join(lines))


def _handle_create_coding_task(title: str) -> CommandResult:
    cleaned_title = _clean_coding_task_title(title)
    row = repository.create_coding_task(
        title=cleaned_title,
        description=cleaned_title,
        labels=["coding", "from-dingtalk"],
        source="dingtalk",
    )
    return CommandResult(
        ok=True,
        message=(
            f"已创建开发任务 #{row['id']}，等待云端 Codex worker 处理。\n\n"
            f"任务：{row['title']}\n\n"
            "worker 会在 ECS 上拉取任务、改代码、推送分支，并在完成后触发部署。"
        ),
    )


def _handle_list_coding_tasks() -> CommandResult:
    tasks = repository.list_coding_tasks(status="all", limit=10)
    if not tasks:
        return CommandResult(ok=True, message="暂无开发任务。")

    lines = ["最近开发任务："]
    for task in tasks:
        suffix = ""
        if task.get("branch_name"):
            suffix = f" -> {task['branch_name']}"
        lines.append(f"- #{task['id']} [{task['status']}/{task['priority']}] {task['title']}{suffix}")
    return CommandResult(ok=True, message="\n".join(lines))


def _handle_task_events(task_type: str, task_id: int) -> CommandResult:
    events = repository.list_task_events(task_type=task_type.lower(), task_id=task_id, limit=30)
    if not events:
        return CommandResult(ok=True, message=f"{task_type} #{task_id} 暂无任务事件。")

    lines = [f"{task_type} #{task_id} 任务事件："]
    for event in reversed(events):
        status = f" [{event.get('status')}]" if event.get("status") else ""
        message = f"：{_truncate_text(str(event.get('message')), 160)}" if event.get("message") else ""
        lines.append(f"- {event.get('created_at')} {event.get('event_type')}{status}{message}")
    return CommandResult(ok=True, message="\n".join(lines))


def _handle_coding_task_detail(task_id: int) -> CommandResult:
    task = repository.get_coding_task(task_id)
    if not task:
        return CommandResult(ok=False, message=f"没有找到开发任务 #{task_id}。")

    lines = [
        f"开发任务 #{task['id']}",
        f"- 状态：{task['status']}",
        f"- 优先级：{task['priority']}",
        f"- 标题：{task['title']}",
    ]
    if task.get("branch_name"):
        lines.append(f"- 分支：{task['branch_name']}")
    if task.get("commit_sha"):
        lines.append(f"- commit：{task['commit_sha']}")
    if task.get("worker_started_at"):
        lines.append(f"- 开始：{task['worker_started_at']}")
    if task.get("worker_finished_at"):
        lines.append(f"- 结束：{task['worker_finished_at']}")
    if task.get("result"):
        lines.extend(["", "结果：", _truncate_text(str(task["result"]), 2500)])
    elif task.get("worker_log"):
        lines.extend(["", "worker 日志：", _truncate_text(str(task["worker_log"]), 2500)])
    else:
        lines.append("")
        lines.append("还没有 worker 结果。")
    return CommandResult(ok=True, message="\n".join(lines))


def _handle_retry_coding_task(task_id: int) -> CommandResult:
    try:
        task = repository.retry_coding_task(
            task_id,
            worker_log="Requeued by DingTalk command.",
        )
    except ValueError:
        return CommandResult(ok=False, message=f"没有找到开发任务 #{task_id}。")
    return CommandResult(
        ok=True,
        message=(
            f"已重新排队开发任务 #{task['id']}。\n\n"
            f"任务：{task['title']}\n\n"
            "worker 会在下一轮轮询时重新处理。"
        ),
    )


def _handle_worker_status() -> CommandResult:
    workers = repository.list_worker_status()
    tasks = repository.list_coding_tasks(status="all", limit=5)

    lines = ["Codex worker 状态："]
    cloud_status = render_cloud_coding_status()
    if not cloud_status.startswith("云端开发状态暂不可用"):
        lines.append(cloud_status)
        lines.append("")

    if not workers:
        lines.append("- 暂无 worker 心跳记录。")
        lines.append("- 这通常表示 worker 没启动，或还没连上数据库。")
    else:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        for worker in workers:
            last_seen = str(worker.get("last_seen_at") or "")
            stale_hint = ""
            try:
                last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                age_seconds = (now - last_seen_dt.astimezone(ZoneInfo("Asia/Shanghai"))).total_seconds()
                if age_seconds > 120:
                    stale_hint = "，可能已卡住"
            except ValueError:
                pass
            lines.append(f"- {worker['name']}: {worker['status']}，最后心跳 {last_seen}{stale_hint}")
            if worker.get("last_error"):
                lines.append(f"  最近错误：{_truncate_text(str(worker['last_error']), 800)}")

    lines.append("")
    lines.append("最近开发任务：")
    if not tasks:
        lines.append("- 暂无开发任务。")
    else:
        for task in tasks:
            lines.append(f"- #{task['id']} [{task['status']}] {task['title']}")
    return CommandResult(ok=True, message="\n".join(lines))


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n...内容过长，已截断。"


def _handle_portfolio_positions() -> CommandResult:
    try:
        snapshot = get_futu_positions()
    except FutuProviderError as exc:
        return CommandResult(
            ok=False,
            message=(
                "暂时读取不到富途持仓。\n"
                f"原因：{exc}\n\n"
                "需要确认云端 OpenD 已启动、已登录富途账号，且只在 ECS 本机开放端口。"
            ),
        )
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取富途持仓失败：{exc}")

    return CommandResult(ok=True, message=_render_portfolio_positions(snapshot))


def _handle_hk_ipos() -> CommandResult:
    try:
        snapshot = get_hk_ipo_list(include_orders=False)
    except FutuProviderError as exc:
        return CommandResult(
            ok=False,
            message=(
                "暂时读取不到港股新股。\n"
                f"原因：{exc}\n\n"
                "需要确认云端 OpenD 已启动，且容器可以访问 OpenD。"
            ),
        )
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取港股新股失败：{exc}")

    return CommandResult(ok=True, message=_render_hk_ipos(snapshot))


def _handle_confirm_candidate(candidate_id: int) -> CommandResult:
    result = repository.confirm_candidate_insight(candidate_id)
    return CommandResult(
        ok=True,
        message=(
            f"已确认候选心得 {result['candidate']['id']}，"
            f"正式心得 id={result['user_insight']['id']}。"
        ),
    )


def _handle_reject_candidate(candidate_id: int) -> CommandResult:
    candidate = repository.reject_candidate_insight(candidate_id)
    return CommandResult(ok=True, message=f"已拒绝候选心得 {candidate['id']}。")


def _handle_futu_control_status() -> CommandResult:
    try:
        response = ping_opend_telnet()
    except FutuOpenDControlError as exc:
        return CommandResult(
            ok=False,
            message=(
                "OpenD Telnet 控制口暂不可用。\n"
                f"原因：{exc}\n\n"
                "如果要用钉钉提交验证码，需要让 OpenD 启动参数包含 "
                "`-telnet_ip=127.0.0.1 -telnet_port=22222`，并把该端口代理给容器。"
            ),
        )
    return CommandResult(ok=True, message="OpenD Telnet 控制口可用。\n\n" + _trim_opend_response(response))


def _handle_futu_request_verify_code() -> CommandResult:
    try:
        response = request_phone_verify_code()
    except FutuOpenDControlError as exc:
        return CommandResult(ok=False, message=f"请求富途验证码失败：{exc}")
    return CommandResult(
        ok=True,
        message=(
            "已向 OpenD 发送请求手机验证码命令。\n\n"
            + _trim_opend_response(response)
            + "\n\n如果手机收到验证码，请回复：富途验证码 123456"
        ),
    )


def _handle_futu_verify_code(code: str) -> CommandResult:
    try:
        response = submit_phone_verify_code(code)
    except FutuOpenDControlError as exc:
        return CommandResult(ok=False, message=f"提交富途验证码失败：{exc}")
    return CommandResult(
        ok=True,
        message=(
            "已向 OpenD 提交手机验证码。\n\n"
            + _trim_opend_response(response)
            + "\n\n请等 5-10 秒后再试：我的持仓"
        ),
    )


def _handle_futu_relogin() -> CommandResult:
    try:
        response = relogin_opend()
    except FutuOpenDControlError as exc:
        return CommandResult(ok=False, message=f"触发富途重登录失败：{exc}")
    return CommandResult(
        ok=True,
        message="已向 OpenD 发送重登录命令。\n\n" + _trim_opend_response(response),
    )


def _handle_futu_login_flow() -> CommandResult:
    try:
        relogin_response = relogin_opend()
        verify_response = request_phone_verify_code()
    except FutuOpenDControlError as exc:
        return CommandResult(ok=False, message=f"启动富途登录修复失败：{exc}")
    return CommandResult(
        ok=True,
        message=(
            "已尝试触发 OpenD 重登录并请求手机验证码。\n\n"
            "重登录返回：\n"
            + _trim_opend_response(relogin_response)
            + "\n\n验证码请求返回：\n"
            + _trim_opend_response(verify_response)
            + "\n\n如果手机收到验证码，请回复：富途验证码 123456"
        ),
    )


def _trim_opend_response(response: str) -> str:
    lines = [line.rstrip() for line in response.strip().splitlines() if line.strip()]
    if not lines:
        return "OpenD 没有返回详细文本。"
    return "\n".join(lines[:20])


def _handle_record_stock_insight(symbol: str, market: str, insight: str) -> CommandResult:
    row = repository.record_user_insight(
        target_type="stock",
        symbol=symbol,
        market=market,
        insight=insight,
    )
    return CommandResult(ok=True, message=f"已记录个股心得 id={row['id']}。")


def _handle_record_global_insight(target_type: str, insight: str) -> CommandResult:
    row = repository.record_user_insight(
        target_type=target_type,
        insight=insight,
    )
    label = "策略" if target_type == "strategy" else "组合"
    return CommandResult(ok=True, message=f"已记录{label}心得 id={row['id']}。")


def _handle_propose_stock_candidate(symbol: str, market: str, insight: str) -> CommandResult:
    row = repository.propose_candidate_insight(
        target_type="stock",
        symbol=symbol,
        market=market,
        insight=insight,
        reason="来自统一指令入口的候选心得，需要用户确认。",
    )
    suffix = _candidate_repeat_suffix(row)
    return CommandResult(ok=True, message=f"已提出候选心得 id={row['id']}{suffix}，等待确认。")


def _handle_propose_global_candidate(target_type: str, insight: str) -> CommandResult:
    row = repository.propose_candidate_insight(
        target_type=target_type,
        insight=insight,
        reason="来自统一指令入口的组合/策略候选心得，需要用户确认。",
    )
    label = "策略" if target_type == "strategy" else "组合"
    suffix = _candidate_repeat_suffix(row)
    return CommandResult(ok=True, message=f"已提出{label}候选心得 id={row['id']}{suffix}，等待确认。")


def _candidate_repeat_suffix(row: dict[str, Any]) -> str:
    repeat_count = int(row.get("repeat_count") or 1)
    if repeat_count <= 1:
        return ""
    return f"（重复 {repeat_count} 次，已合并）"


def _handle_intent_routed_command(command: str) -> CommandResult | None:
    intent = _route_intent(command)
    intent_name = str(intent.get("intent") or "unknown")
    confidence = _number(intent.get("confidence"))
    if intent_name == "unknown" or confidence < 0.45:
        return None

    if intent_name == "portfolio_analysis":
        return _handle_portfolio_analysis()
    if intent_name == "portfolio_graph":
        return _handle_portfolio_graph_queue()
    if intent_name == "portfolio_positions":
        return _handle_portfolio_positions()
    if intent_name == "system_status":
        return CommandResult(ok=True, message=render_system_status())
    if intent_name == "ipo_status":
        if any(keyword in command for keyword in ("提醒", "推送", "状态", "没发", "没提醒")):
            return CommandResult(ok=True, message=render_ipo_reminder_status())
        return _handle_hk_ipos()
    if intent_name == "trade_review":
        if any(keyword in command for keyword in ("收益", "赚在哪", "亏在哪")):
            return _handle_performance_estimate(time_range_text=str(intent.get("time_range") or "").strip() or None)
        return _handle_trade_review(time_range_text=str(intent.get("time_range") or "").strip() or None)
    if intent_name == "coding_task":
        title = str(intent.get("coding_task") or command).strip()
        return _handle_create_coding_task(title or command)
    if intent_name == "memory_candidate":
        candidate = str(intent.get("memory_candidate") or command).strip()
        if not candidate:
            return None
        target_type = str(intent.get("target_type") or "strategy").strip().lower()
        if target_type not in {"portfolio", "strategy"}:
            target_type = "strategy"
        result = _handle_propose_global_candidate(target_type=target_type, insight=candidate)
        return CommandResult(
            ok=True,
            message=(
                result.message
                + "\n\n"
                + "我先把它作为候选心得保存，等你确认后才会变成正式长期记忆。"
            ),
        )
    return None


def _route_intent(command: str) -> dict[str, Any]:
    heuristic = _heuristic_route_intent(command)
    if heuristic.get("confidence", 0) >= 0.8 or heuristic.get("intent") == "memory_candidate":
        return heuristic
    try:
        routed = route_command_intent_with_openai(command)
    except Exception:
        routed = None
    if routed and routed.get("intent"):
        return routed
    return heuristic


def _heuristic_route_intent(command: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", "", command.lower())
    if _looks_like_coding_task(command):
        return {
            "intent": "coding_task",
            "confidence": 0.82,
            "target_type": None,
            "coding_task": _clean_coding_task_title(command),
        }
    if any(
        keyword in compact
        for keyword in ("系统状态", "自检", "检查系统", "检查部署", "有没有问题", "opend", "openai", "机器人没", "没回复")
    ):
        return {"intent": "system_status", "confidence": 0.9, "target_type": None}
    if any(keyword in compact for keyword in ("ipo提醒", "新股提醒", "没提醒", "提醒状态")):
        return {"intent": "ipo_status", "confidence": 0.9, "target_type": None}
    if any(keyword in compact for keyword in ("港股新股", "新股", "ipo")):
        return {"intent": "ipo_status", "confidence": 0.85, "target_type": None}
    if any(keyword in compact for keyword in ("交易记录", "收益", "赚在哪", "亏在哪", "月度", "本月")):
        return {
            "intent": "trade_review",
            "confidence": 0.85,
            "target_type": None,
            "time_range": _extract_time_range_text(command),
        }
    if any(keyword in compact for keyword in ("持仓图谱", "组合图谱", "图谱队列", "知识图谱覆盖")):
        return {"intent": "portfolio_graph", "confidence": 0.9, "target_type": None}
    if any(keyword in compact for keyword in ("持仓分析", "仓位分析", "组合分析", "持仓怎么看", "仓位怎么看", "组合风险")):
        return {"intent": "portfolio_analysis", "confidence": 0.85, "target_type": None}
    if any(keyword in compact for keyword in ("我的持仓", "当前持仓", "持仓列表", "仓位列表")):
        return {"intent": "portfolio_positions", "confidence": 0.85, "target_type": None}
    if _looks_like_memory_candidate(command):
        target_type = "strategy" if any(keyword in command for keyword in ("系统", "长期", "目标", "策略", "进步", "复盘", "伴侣")) else "portfolio"
        return {
            "intent": "memory_candidate",
            "confidence": 0.78,
            "target_type": target_type,
            "memory_candidate": command,
        }
    return {"intent": "unknown", "confidence": 0.0, "target_type": None}


def _looks_like_coding_task(command: str) -> bool:
    text = command.strip()
    if len(text) < 8:
        return False
    explicit_markers = (
        "创建开发任务",
        "提出开发任务",
        "创建编程任务",
        "新建开发任务",
        "开发任务",
        "coding task",
        "dev task",
    )
    if any(marker in text.lower() for marker in explicit_markers):
        return True

    action_markers = ("帮我修", "帮我改", "帮我实现", "帮我加", "帮我做", "修一下", "改一下", "优化一下", "排查一下")
    tech_markers = (
        "代码",
        "脚本",
        "workflow",
        "github",
        "deploy",
        "部署",
        "报错",
        "bug",
        "接口",
        "命令",
        "codex",
        "mcp",
        "钉钉",
        "opend",
        "openai",
    )
    return any(marker in text for marker in action_markers) and any(marker.lower() in text.lower() for marker in tech_markers)


def _clean_coding_task_title(command: str) -> str:
    title = _strip_trailing_punctuation(command)
    title = re.sub(
        r"^(?:创建开发任务|提出开发任务|创建编程任务|新建开发任务|开发任务|coding task|dev task)\s*[:：]?\s*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip() or command.strip()


def _looks_like_memory_candidate(command: str) -> bool:
    if len(command.strip()) < 12:
        return False
    markers = (
        "我觉得",
        "我认为",
        "我希望",
        "我想",
        "对我而言",
        "我的策略",
        "我的系统",
        "需要复盘",
        "消耗",
        "管理成本",
        "长期",
        "伴侣",
        "持续赚钱",
        "继续进步",
    )
    return any(marker in command for marker in markers)


def _extract_time_range_text(command: str) -> str | None:
    range_match = re.search(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}.*\d{4}[-/]\d{1,2}[-/]\d{1,2}", command)
    if range_match:
        return range_match.group(0)
    if re.search(r"(?:今年以来|今年|本年|本月|这个月|上月|上个月|近\s*\d+\s*[天日]|最近\s*\d+\s*[天日])", command):
        return command
    if _DATE_TOKEN_RE.search(command) and re.search(r"(?:到|至|~|—|-)", command):
        return command
    if _MONTH_TOKEN_RE.search(command) and re.search(r"(?:到|至|~|—|-)", command):
        return command
    month_match = re.search(r"\d{4}[-/年]\d{1,2}", command)
    if month_match:
        return month_match.group(0)
    bare_month_match = _MONTH_TOKEN_RE.search(command)
    if bare_month_match:
        return bare_month_match.group(0)
    return None


def _candidate_count(context: dict) -> int:
    return (
        len(context.get("stock_candidate_insights") or [])
        + len(context.get("sector_candidate_insights") or [])
        + len(context.get("global_candidate_insights") or [])
    )


def _normalize_natural_command(command: str) -> str:
    cleaned = command.strip()
    compact = _strip_trailing_punctuation(cleaned)

    if compact in {"候选", "候选心得", "有什么候选心得", "有哪些候选心得", "待确认心得"}:
        return "查看候选心得"
    if compact in {"帮助", "怎么用", "能做什么", "help", "?"}:
        return "帮助"
    if compact in {"港股新股", "港股IPO", "港股ipo", "新股", "ipo", "IPO"}:
        return "港股新股"
    if compact in PORTFOLIO_ANALYSIS_COMMANDS:
        return "持仓分析"
    if compact in PORTFOLIO_GRAPH_COMMANDS:
        return "持仓图谱"
    if compact in PORTFOLIO_POSITION_COMMANDS:
        return "我的持仓"

    stock_query = _extract_stock_query(compact)
    if not stock_query:
        return cleaned

    symbol_market_match = re.fullmatch(r"(\S+)\s+(\S+)", stock_query)
    if symbol_market_match:
        symbol, market = symbol_market_match.groups()
        return f"分析 {symbol} {market}"

    matches = repository.resolve_stock_reference(stock_query)
    if len(matches) == 1:
        stock = matches[0]
        return f"分析 {stock['symbol']} {stock['market']}"
    if len(matches) > 1:
        choices = "、".join(
            f"{item.get('name') or item['symbol']}({item['symbol']} {item['market']})"
            for item in matches
        )
        return f"__AMBIGUOUS_STOCK__ {choices}"
    return cleaned


def _extract_stock_query(command: str) -> str | None:
    patterns = [
        r"^(?:怎么看|如何看|怎样看|看一下|分析一下|分析|聊聊|说说)(.+)$",
        r"^(.+?)(?:怎么看|如何看|怎样看|怎么样|咋样)$",
        r"^(.+?)值得看吗$",
    ]
    for pattern in patterns:
        match = re.fullmatch(pattern, command, flags=re.IGNORECASE)
        if match:
            return _clean_stock_query(match.group(1))
    return None


def _clean_stock_query(value: str) -> str:
    cleaned = _strip_trailing_punctuation(value)
    cleaned = re.sub(r"^(?:一下|下|这个|这只|这家公司|股票)\s*", "", cleaned)
    cleaned = re.sub(r"\s*(?:这个|这只|这家公司|股票)$", "", cleaned)
    return cleaned.strip()


def _parse_stock_target(value: str) -> tuple[str, str] | None:
    cleaned = value.strip()
    market_symbol_match = re.fullmatch(r"([A-Za-z]{1,5})\.([A-Za-z0-9._-]+)", cleaned)
    if market_symbol_match:
        market, symbol = market_symbol_match.groups()
        return symbol.upper(), market.upper()
    symbol_market_match = re.fullmatch(r"(\S+)\s+(\S+)", cleaned)
    if symbol_market_match:
        symbol, market = symbol_market_match.groups()
        return symbol.upper(), market.upper()
    if re.fullmatch(r"[A-Z]{1,5}", cleaned):
        return cleaned.upper(), "US"
    return None


def _strip_trailing_punctuation(value: str) -> str:
    return value.strip().strip("？?。.!！,， ")


def _render_portfolio_positions(snapshot: Any) -> str:
    positions = snapshot.positions
    fetched_at = snapshot.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    if not positions:
        return f"当前富途持仓为空。\n数据时间：{fetched_at}"

    sorted_positions = sorted(
        positions,
        key=lambda item: _number(item.get("market_val")),
        reverse=True,
    )
    currency_totals: dict[str, dict[str, float]] = {}
    for item in sorted_positions:
        currency = _position_currency(item)
        bucket = currency_totals.setdefault(currency, {"market_val": 0.0, "pl_val": 0.0, "count": 0.0})
        bucket["market_val"] += _number(item.get("market_val"))
        bucket["pl_val"] += _number(item.get("pl_val"))
        bucket["count"] += 1
    has_mixed_currency = len([currency for currency in currency_totals if currency != "UNKNOWN"]) > 1

    lines = [
        "富途实时持仓：",
        f"- 持仓数量：{len(positions)}",
        f"- 数据时间：{fetched_at}" + ("（短缓存）" if snapshot.cached else ""),
        "",
        "按币种汇总：",
    ]
    if has_mixed_currency:
        lines.append("- 检测到多币种持仓，未配置汇率换算；这里不展示单一总市值。")
    else:
        only_currency = next(iter(currency_totals), "")
        totals = currency_totals.get(only_currency, {"market_val": 0.0, "pl_val": 0.0})
        lines.insert(2, f"- 总市值：{_fmt_money(totals['market_val'])} {only_currency}".rstrip())
        lines.insert(3, f"- 浮动盈亏：{_fmt_money(totals['pl_val'])} {only_currency}".rstrip())

    for currency, totals in sorted(currency_totals.items(), key=lambda pair: pair[1]["market_val"], reverse=True):
        lines.append(
            f"- {currency}: 市值 {_fmt_money(totals['market_val'])}, "
            f"浮动盈亏 {_fmt_money(totals['pl_val'])}, 持仓 {int(totals['count'])} 个"
        )

    lines.extend(
        [
            "",
            "持仓明细：",
        ]
    )
    for item in sorted_positions:
        name = item.get("stock_name") or item.get("code") or "unknown"
        code = item.get("code") or ""
        currency = _position_currency(item)
        market_val = _number(item.get("market_val"))
        currency_total = currency_totals.get(currency, {}).get("market_val") or 0
        currency_weight = market_val / currency_total * 100 if currency_total else 0
        pl_ratio = _number(item.get("pl_ratio"))
        lines.append(
            f"- {name} {code}: 市值 {_fmt_money(market_val)} {currency}, "
            f"{currency} 内占比 {currency_weight:.1f}%, 盈亏 {_fmt_percent(pl_ratio)}"
        )
    lines.append("")
    lines.append("注：当前只读持仓，不会下单或修改账户。")
    return "\n".join(lines)


def _handle_portfolio_analysis() -> CommandResult:
    try:
        snapshot = get_futu_positions()
    except FutuProviderError as exc:
        return CommandResult(
            ok=False,
            message=(
                "暂时读取不到富途持仓，无法生成持仓分析。\n"
                f"原因：{exc}\n\n"
                "需要确认云端 OpenD 已启动、已登录富途账号，且只在 ECS 本机开放端口。"
            ),
        )
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取富途持仓失败，无法生成持仓分析：{exc}")

    context = build_portfolio_analysis_context(snapshot)
    fallback = render_portfolio_analysis_fallback(context)
    analysis = _generate_portfolio_analysis(context=context, fallback=fallback)
    return CommandResult(
        ok=True,
        message=analysis + "\n\n" + _portfolio_analysis_footer(context),
    )


def _handle_portfolio_graph_queue() -> CommandResult:
    try:
        snapshot = get_futu_positions()
    except FutuProviderError as exc:
        return CommandResult(
            ok=False,
            message=(
                "暂时读取不到富途持仓，无法生成持仓图谱队列。\n"
                f"原因：{exc}\n\n"
                "需要确认云端 OpenD 已启动、已登录富途账号，且只在 ECS 本机开放端口。"
            ),
        )
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取富途持仓失败，无法生成持仓图谱队列：{exc}")

    context = build_portfolio_graph_queue(snapshot)
    return CommandResult(ok=True, message=render_portfolio_graph_queue(context))


def _generate_portfolio_analysis(context: dict[str, Any], fallback: str) -> str:
    try:
        analysis = generate_portfolio_analysis_with_openai(context)
    except Exception as exc:
        return fallback + f"\n\nOpenAI 组合分析暂时不可用，已使用本地模板分析。错误：{exc}"
    if not analysis:
        return fallback
    return analysis


def _portfolio_analysis_footer(context: dict[str, Any]) -> str:
    summary = context.get("summary") or {}
    footer = (
        "注：这版只读分析不会下单；只基于富途实时持仓、已入库知识和你的已确认心得，"
        "不包含未提供的实时新闻或公告。\n"
        f"数据覆盖：持仓 {summary.get('position_count', 0)} 个，"
        f"匹配知识库个股 {len(context.get('knowledge_matches') or [])} 个，"
        f"组合/策略心得 {len(context.get('global_insights') or [])} 条，"
        f"待确认候选 {len(context.get('global_candidate_insights') or [])} 条。"
    )
    warnings = context.get("context_warnings") or []
    if warnings:
        footer += "\n提醒：" + "；".join(str(item) for item in warnings[:2])
    return footer


def _render_hk_ipos(snapshot: Any) -> str:
    ipos = snapshot.ipos
    fetched_at = snapshot.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    if not ipos:
        return f"当前富途没有返回港股新股列表。\n数据时间：{fetched_at}"

    active_count = sum(1 for item in ipos if _is_subscribable(item.get("is_subscribe_status")))
    lines = [
        "港股新股：",
        f"- 新股数量：{len(ipos)}",
        f"- 可申购数量：{active_count}",
        f"- 数据时间：{fetched_at}" + ("（短缓存）" if snapshot.cached else ""),
        "",
    ]
    for title, items in _group_ipos(ipos):
        if not items:
            continue
        lines.append(f"{title}：")
        for item in sorted(items, key=_ipo_sort_key):
            lines.append(_render_ipo_line(item))
        lines.append("")

    if lines[-1] == "":
        lines.pop()
    lines.append("注：这里展示富途 IPO 列表状态；个人 IPO 申购/中签记录暂未接入，当前只读查询，不会提交申购。")
    return "\n".join(lines)


def _match_trade_review_command(command: str) -> str | None:
    compact = command.strip()
    if compact in TRADE_REVIEW_COMMANDS:
        return ""
    for prefix in TRADE_REVIEW_COMMANDS:
        if compact.startswith(prefix + " "):
            return compact[len(prefix) :].strip()
    if re.fullmatch(r"交易记录\s+\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{4}[-/]\d{1,2}[-/]\d{1,2}", compact):
        return compact.replace("交易记录", "", 1).strip()
    return None


def _match_weekly_review_command(command: str) -> str | None:
    compact = command.strip()
    if compact in {"上周复盘", "上星期复盘", "上个星期复盘"}:
        return "上周"
    if compact in {"复盘上周", "复盘上星期", "复盘上个星期"}:
        return "上周"
    if compact in WEEKLY_REVIEW_COMMANDS:
        return ""
    for prefix in WEEKLY_REVIEW_COMMANDS | {"复盘"}:
        if compact.startswith(prefix + " "):
            return compact[len(prefix) :].strip()
    if re.fullmatch(r"复盘\s+\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{4}[-/]\d{1,2}[-/]\d{1,2}", compact):
        return compact.replace("复盘", "", 1).strip()
    return None


def _match_next_week_command(command: str) -> str | None:
    compact = command.strip()
    if compact in NEXT_WEEK_COMMANDS:
        return ""
    for prefix in NEXT_WEEK_COMMANDS:
        if compact.startswith(prefix + " "):
            return compact[len(prefix) :].strip()
    return None


def _match_performance_estimate_command(command: str) -> str | None:
    compact = command.strip()
    if compact in PERFORMANCE_ESTIMATE_COMMANDS:
        return ""
    for prefix in PERFORMANCE_ESTIMATE_COMMANDS:
        if compact.startswith(prefix + " "):
            return compact[len(prefix) :].strip()
    return None


def _match_trade_backfill_command(command: str) -> str | None:
    compact = command.strip()
    for prefix in TRADE_BACKFILL_COMMANDS:
        if compact == prefix:
            return ""
        if compact.startswith(prefix + " "):
            return compact[len(prefix) :].strip()
    return None


def _handle_weekly_review(time_range_text: str | None = None, next_week_only: bool = False) -> CommandResult:
    start, end, _ = _resolve_weekly_review_range(time_range_text)
    try:
        result = build_weekly_review(start=start, end=end, save=not next_week_only, next_week_only=next_week_only)
    except Exception as exc:
        return CommandResult(ok=False, message=f"生成本周复盘失败：{exc}")
    footer = ""
    if result.saved_report is not None:
        footer = f"\n\n已保存周复盘：review_reports #{result.saved_report.get('id')}"
    return CommandResult(ok=True, message=result.markdown + footer)


def _handle_trade_review(time_range_text: str | None = None) -> CommandResult:
    start, end, label = _resolve_trade_review_range(time_range_text)
    try:
        snapshot = get_futu_trade_history(start=start.isoformat(), end=end.isoformat())
    except FutuProviderError as exc:
        message = (
            f"交易复盘（{label}）接口已接上，但暂时读取不到富途交易记录。\n"
            f"原因：{exc}\n\n"
            "需要确认云端 OpenD 已启动、已完成验证码登录，并且容器可以访问 OpenD。"
        )
        return CommandResult(ok="futu-api 未安装" in str(exc), message=message)
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取富途交易记录失败：{exc}")

    return CommandResult(ok=True, message=_render_trade_review(snapshot=snapshot, label=label))


def _handle_trade_backfill(time_range_text: str | None = None) -> CommandResult:
    start, end, label = _resolve_trade_review_range(time_range_text)
    try:
        snapshot = get_futu_trade_history(start=start.isoformat(), end=end.isoformat())
    except FutuProviderError as exc:
        message = (
            f"补全交易记录（{label}）暂时读取不到富途交易记录。\n"
            f"原因：{exc}\n\n"
            "需要确认云端 OpenD 已启动、已完成验证码登录，并且容器可以访问 OpenD。"
        )
        return CommandResult(ok="futu-api 未安装" in str(exc), message=message)
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取富途交易记录失败，无法补全：{exc}")

    try:
        result = repository.upsert_trade_records(snapshot.deals)
        stored_count = repository.count_trade_records(start=start.isoformat(), end=end.isoformat())
    except Exception as exc:
        return CommandResult(ok=False, message=f"交易记录落库失败：{exc}")

    lines = [
        f"交易记录补全（{label}）",
        f"- 查询区间：{snapshot.start} 至 {snapshot.end}",
        f"- 富途返回成交：{len(snapshot.deals)} 笔",
        f"- 本次写入/更新：{result['synced_count']} 笔",
        f"- 当前库内该区间记录：{stored_count} 笔",
        "- 口径：按富途 deal_id 去重；缺少 deal_id 时使用订单、标的、方向、数量、价格、时间组合去重。",
    ]
    return CommandResult(ok=True, message="\n".join(lines))


def _resolve_weekly_review_range(value: str | None) -> tuple[date, date, str]:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    text = (value or "").strip()
    if not text or re.search(r"(?:本周|这周|本星期|这个星期)", text):
        start = today - timedelta(days=today.weekday())
        return start, today, f"{start.isoformat()} 至 {today.isoformat()}"

    if re.search(r"(?:上周|上星期)", text):
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    range_match = re.search(
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}).*?(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        text,
    )
    if range_match:
        start = _parse_command_date(range_match.group(1))
        end = _parse_command_date(range_match.group(2))
        if end < start:
            start, end = end, start
        return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    date_tokens = _extract_date_tokens(text, today=today)
    if len(date_tokens) >= 2:
        start, end = date_tokens[0], date_tokens[1]
        if end < start:
            start, end = end, start
        return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    start = today - timedelta(days=today.weekday())
    return start, today, f"{start.isoformat()} 至 {today.isoformat()}"


def _handle_performance_estimate(time_range_text: str | None = None) -> CommandResult:
    start, end, label = _resolve_trade_review_range(time_range_text)
    try:
        trade_snapshot = get_futu_trade_history(start=start.isoformat(), end=end.isoformat())
    except FutuProviderError as exc:
        message = (
            f"估算收益复盘（{label}）暂时读取不到富途交易记录。\n"
            f"原因：{exc}\n\n"
            "需要确认云端 OpenD 已启动、已完成验证码登录，并且容器可以访问 OpenD。"
        )
        return CommandResult(ok="futu-api 未安装" in str(exc), message=message)
    except Exception as exc:
        return CommandResult(ok=False, message=f"读取富途交易记录失败，无法估算收益：{exc}")

    try:
        position_snapshot = get_futu_positions()
        positions_error = None
    except Exception as exc:
        position_snapshot = None
        positions_error = str(exc)

    try:
        cash_flow_snapshot = get_futu_cash_flows(start=start.isoformat(), end=end.isoformat())
        cash_flow_error = None
    except Exception as exc:
        cash_flow_snapshot = None
        cash_flow_error = str(exc)

    snapshot_row, snapshot_error = _save_account_snapshot_for_performance(
        trade_snapshot=trade_snapshot,
        position_snapshot=position_snapshot,
        start=start,
        end=end,
    )
    account_snapshots, account_snapshots_error = _load_account_snapshots_for_range(start=start, end=end)

    return CommandResult(
        ok=True,
        message=_render_performance_estimate(
            trade_snapshot=trade_snapshot,
            position_snapshot=position_snapshot,
            cash_flow_snapshot=cash_flow_snapshot,
            positions_error=positions_error,
            cash_flow_error=cash_flow_error,
            account_snapshot=snapshot_row,
            account_snapshot_error=snapshot_error,
            account_snapshots=account_snapshots,
            account_snapshots_error=account_snapshots_error,
            label=label,
        ),
    )


def _resolve_trade_review_range(value: str | None) -> tuple[date, date, str]:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    text = (value or "").strip()
    if not text or re.search(r"(?:本月|这个月)", text):
        start = today.replace(day=1)
        return start, today, f"{start.isoformat()} 至 {today.isoformat()}"

    if re.search(r"(?:上月|上个月)", text):
        year = today.year
        month = today.month - 1
        if month == 0:
            year -= 1
            month = 12
        return _month_range(year=year, month=month, today=today)

    if re.search(r"(?:今年以来|今年|本年)", text):
        start = date(today.year, 1, 1)
        return start, today, f"{start.isoformat()} 至 {today.isoformat()}"

    recent_days_match = re.search(r"(?:近|最近)\s*(\d{1,4})\s*[天日]", text)
    if recent_days_match:
        days = max(1, int(recent_days_match.group(1)))
        start = today - _date_delta(days - 1)
        return start, today, f"{start.isoformat()} 至 {today.isoformat()}"

    range_match = re.search(
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2}).*?(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        text,
    )
    if range_match:
        start = _parse_command_date(range_match.group(1))
        end = _parse_command_date(range_match.group(2))
        if end < start:
            start, end = end, start
        return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    date_tokens = _extract_date_tokens(text, today=today)
    if len(date_tokens) >= 2:
        start, end = date_tokens[0], date_tokens[1]
        if end < start:
            start, end = end, start
        return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    month_match = re.search(r"(\d{4})[-/年](\d{1,2})", text)
    if month_match:
        year = int(month_match.group(1))
        month = int(month_match.group(2))
        return _month_range(year=year, month=month, today=today)

    month_tokens = _extract_month_tokens(text, today=today)
    if len(month_tokens) >= 2:
        first_year, first_month = month_tokens[0]
        last_year, last_month = month_tokens[1]
        start, _, _ = _month_range(year=first_year, month=first_month, today=today)
        _, end, _ = _month_range(year=last_year, month=last_month, today=today)
        if end < start:
            start, end = end, start
        return start, end, f"{start.isoformat()} 至 {end.isoformat()}"

    bare_month = _parse_bare_month(text)
    if bare_month is not None:
        return _month_range(year=_infer_year_for_month(bare_month, today=today), month=bare_month, today=today)

    start = today.replace(day=1)
    return start, today, f"{start.isoformat()} 至 {today.isoformat()}"


def _parse_command_date(value: str) -> date:
    normalized = value.replace("/", "-")
    return datetime.strptime(normalized, "%Y-%m-%d").date()


def _date_delta(days: int) -> timedelta:
    return timedelta(days=days)


def _month_range(year: int, month: int, today: date) -> tuple[date, date, str]:
    last_day = calendar.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last_day)
    if start <= today <= end:
        end = today
    return start, end, f"{year:04d}-{month:02d}"


def _parse_bare_month(value: str) -> int | None:
    match = _MONTH_TOKEN_RE.search(value)
    if not match:
        return None
    month = _parse_month_text(match.group(0))
    if month is None or month < 1 or month > 12:
        return None
    return month


def _extract_month_tokens(value: str, today: date) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for match in re.finditer(rf"(?:(\d{{4}})\s*年\s*)?({_MONTH_TEXT})\s*月份?", value):
        month = _parse_month_text(match.group(2))
        if month is None or month < 1 or month > 12:
            continue
        year = int(match.group(1)) if match.group(1) else _infer_year_for_month(month, today=today)
        result.append((year, month))
    return result


def _extract_date_tokens(value: str, today: date) -> list[date]:
    result: list[date] = []
    for match in re.finditer(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value):
        result.append(_parse_command_date(match.group(0)))
    for match in re.finditer(rf"(?:(\d{{4}})\s*年\s*)?({_MONTH_TEXT})\s*月\s*(\d{{1,2}})\s*[日号]?", value):
        month = _parse_month_text(match.group(2))
        day = int(match.group(3))
        if month is None or month < 1 or month > 12:
            continue
        year = int(match.group(1)) if match.group(1) else _infer_year_for_date(month=month, day=day, today=today)
        try:
            result.append(date(year, month, day))
        except ValueError:
            continue
    return sorted(set(result))


def _parse_month_text(value: str) -> int | None:
    text = re.sub(r"\s+", "", value)
    text = text.replace("月份", "").replace("月", "")
    if text.isdigit():
        return int(text)
    return CHINESE_MONTHS.get(text)


def _infer_year_for_month(month: int, today: date) -> int:
    return today.year - 1 if month > today.month else today.year


def _infer_year_for_date(month: int, day: int, today: date) -> int:
    year = today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return year
    return year - 1 if candidate > today else year


def _save_account_snapshot_for_performance(
    trade_snapshot: Any,
    position_snapshot: Any,
    start: date,
    end: date,
) -> tuple[dict[str, Any] | None, str | None]:
    account_info = trade_snapshot.account_info or {}
    positions = position_snapshot.positions if position_snapshot is not None else []
    if not account_info and not positions:
        return None, None

    fetched_at = trade_snapshot.fetched_at.astimezone(ZoneInfo("Asia/Shanghai"))
    try:
        row = repository.upsert_account_snapshot(
            snapshot_date=fetched_at.date().isoformat(),
            account_info=account_info,
            positions=positions,
            fx_rates=_current_fx_rates_for_snapshot(),
            fetched_at=fetched_at.isoformat(),
            metadata={
                "command": "performance_estimate",
                "range_start": start.isoformat(),
                "range_end": end.isoformat(),
            },
        )
    except Exception as exc:
        return None, str(exc)
    return row, None


def _load_account_snapshots_for_range(start: date, end: date) -> tuple[list[dict[str, Any]], str | None]:
    try:
        rows = repository.list_account_snapshots(start=start.isoformat(), end=end.isoformat())
    except Exception as exc:
        return [], str(exc)
    return rows, None


def _render_trade_review(snapshot: Any, label: str) -> str:
    deals = snapshot.deals
    fetched_at = snapshot.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        f"交易复盘（{label}）",
        f"- 成交笔数：{len(deals)}",
        f"- 查询区间：{snapshot.start} 至 {snapshot.end}",
        f"- 数据时间：{fetched_at}",
        "",
        "口径说明：",
        "- 这是第一版“成交复盘”，读取的是富途历史成交；严格区间收益还需要期初/期末净资产、出入金和汇率快照，不能只靠成交记录硬算。",
        "- 当前只读查询，不会下单或修改账户。",
    ]
    if snapshot.account_info:
        lines.extend(["", "当前账户快照："])
        account = snapshot.account_info
        for key, label_text in (
            ("total_assets", "总资产"),
            ("market_val", "证券市值"),
            ("cash", "现金"),
            ("power", "购买力"),
        ):
            value = account.get(key)
            if value is not None:
                lines.append(f"- {label_text}: {value}")
    elif snapshot.account_error:
        lines.extend(["", f"账户快照暂不可用：{snapshot.account_error}"])

    if not deals:
        lines.extend(["", "这个区间没有读取到成交记录。"])
        return "\n".join(lines)

    currency_summary = _summarize_deals_by_currency(deals)
    lines.extend(["", "按币种成交汇总："])
    for currency, summary in sorted(currency_summary.items()):
        buy_usd = _fmt_usd_equivalent(summary["buy_amount"], currency)
        sell_usd = _fmt_usd_equivalent(summary["sell_amount"], currency)
        net_cash_flow = summary["sell_amount"] - summary["buy_amount"]
        net_usd = _fmt_usd_equivalent(net_cash_flow, currency)
        lines.append(
            f"- {currency}: 买入 {_fmt_money(summary['buy_amount'])}{buy_usd}, "
            f"卖出 {_fmt_money(summary['sell_amount'])}{sell_usd}, "
            f"净现金流 {_fmt_money(net_cash_flow)}{net_usd}, "
            f"成交 {int(summary['count'])} 笔"
        )
    usd_summary = _deal_summary_to_usd(currency_summary)
    if usd_summary:
        lines.extend(
            [
                "",
                "美元折算汇总（展示用）：",
                f"- 买入约 {_fmt_money(usd_summary['buy_amount'])} USD，"
                f"卖出约 {_fmt_money(usd_summary['sell_amount'])} USD，"
                f"净交易现金流约 {_fmt_money(usd_summary['net_cash_flow'])} USD。",
                f"- 汇率口径：{_fx_disclaimer()}",
            ]
        )

    lines.extend(["", "主要交易标的："])
    for item in _top_traded_symbols(deals)[:8]:
        lines.append(
            f"- {item['name']} {item['code']}: 成交额 {_fmt_money(item['amount'])} {item['currency']}, "
            f"买入 {int(item['buy_count'])} 笔，卖出 {int(item['sell_count'])} 笔"
        )

    lines.extend(["", "最近成交："])
    for deal in sorted(deals, key=lambda item: str(item.get("create_time") or ""), reverse=True)[:10]:
        side = _fmt_trade_side(deal.get("trd_side"))
        lines.append(
            f"- {_display_value(deal.get('create_time'))} {side} "
            f"{_display_value(deal.get('stock_name'))} {_display_value(deal.get('code'))} "
            f"{_display_value(deal.get('qty'))} 股 @ {_display_value(deal.get('price'))}"
        )

    lines.extend(
        [
            "",
            "下一步建议：如果你认可这个成交口径，我会再加“每日账户快照 + 出入金记录 + 汇率换算”，那时才能做更准确的月度收益归因。",
        ]
    )
    return "\n".join(lines)


def _render_performance_estimate(
    trade_snapshot: Any,
    position_snapshot: Any,
    cash_flow_snapshot: Any,
    positions_error: str | None,
    cash_flow_error: str | None,
    account_snapshot: dict[str, Any] | None,
    account_snapshot_error: str | None,
    account_snapshots: list[dict[str, Any]],
    account_snapshots_error: str | None,
    label: str,
) -> str:
    fetched_at = trade_snapshot.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    range_end = _parse_snapshot_date(str(trade_snapshot.end))
    is_historical_range = range_end is not None and range_end < today
    account = trade_snapshot.account_info or {}
    deals = trade_snapshot.deals
    account_heading = "当前账户快照："
    position_heading = "当前持仓浮盈亏（按原币种）："
    usd_heading = "美元折算总览（展示用）："
    if is_historical_range:
        account_heading = "实时账户快照（截至数据时间，非查询区间）："
        position_heading = "实时持仓浮盈亏（截至数据时间，非查询区间）："
        usd_heading = "美元折算总览（含实时持仓参考）："
    lines = [
        f"估算收益复盘（{label}）",
        f"- 查询区间：{trade_snapshot.start} 至 {trade_snapshot.end}",
        f"- 数据时间：{fetched_at}",
        "- 展示基准：USD；各币种原始数据会保留，并额外给出美元折算汇总。",
        "- 结论口径：当前还没有完整的期初/期末净资产快照、出入金和汇率快照，所以不能严格给出区间收益率；这里先做估算所需数据拼图和低置信度归因。",
        f"- 汇率口径：{_fx_disclaimer()}",
        "",
        account_heading,
    ]
    if account:
        for key, label_text in (
            ("total_assets", "总资产"),
            ("market_val", "证券市值"),
            ("cash", "现金"),
            ("power", "购买力"),
        ):
            value = account.get(key)
            if value is not None:
                lines.append(f"- {label_text}: {value}")
    else:
        lines.append("- 暂未读取到账户快照。")

    lines.extend(["", "查询区间账户快照记录："])
    if account_snapshot is not None:
        saved_date = account_snapshot.get("snapshot_date")
        if is_historical_range:
            lines.append(f"- 今日实时账户快照已保存/更新 {saved_date}，用于后续复盘，不作为本区间期末快照。")
        else:
            lines.append(f"- 已保存/更新 {saved_date} 的账户快照。")
    elif account_snapshot_error:
        lines.append(f"- 本次快照未保存：{account_snapshot_error}")
    else:
        lines.append("- 本次没有足够的账户/持仓数据可保存。")

    if account_snapshots:
        lines.extend(_render_account_snapshot_history(account_snapshots))
    elif account_snapshots_error:
        lines.append(f"- 查询区间历史快照暂不可用：{account_snapshots_error}")
    else:
        lines.append("- 查询区间暂未读取到已保存的历史账户快照。")

    position_summary: dict[str, dict[str, float]] = {}
    if position_snapshot is not None:
        position_summary = _summarize_positions_by_currency(position_snapshot.positions)
        lines.extend(["", position_heading])
        for currency, summary in sorted(position_summary.items()):
            market_usd = _fmt_usd_equivalent(summary["market_val"], currency)
            pl_usd = _fmt_usd_equivalent(summary["pl_val"], currency)
            lines.append(
                f"- {currency}: 市值 {_fmt_money(summary['market_val'])}{market_usd}, "
                f"浮动盈亏 {_fmt_money(summary['pl_val'])}{pl_usd}, 持仓 {int(summary['count'])} 个"
            )
    elif positions_error:
        lines.extend(["", f"当前持仓暂不可用：{positions_error}"])

    deal_summary = _summarize_deals_by_currency(deals)
    lines.extend(["", "区间成交现金流（按原币种）："])
    if deal_summary:
        for currency, summary in sorted(deal_summary.items()):
            buy_usd = _fmt_usd_equivalent(summary["buy_amount"], currency)
            sell_usd = _fmt_usd_equivalent(summary["sell_amount"], currency)
            net_cash_flow = summary["sell_amount"] - summary["buy_amount"]
            net_usd = _fmt_usd_equivalent(net_cash_flow, currency)
            lines.append(
                f"- {currency}: 买入 {_fmt_money(summary['buy_amount'])}{buy_usd}, "
                f"卖出 {_fmt_money(summary['sell_amount'])}{sell_usd}, "
                f"净交易现金流 {_fmt_money(net_cash_flow)}{net_usd}, "
                f"成交 {int(summary['count'])} 笔"
            )
    else:
        lines.append("- 区间没有读取到成交。")

    cash_flow_summary: dict[str, dict[str, float]] = {}
    lines.extend(["", "区间资金流水："])
    if cash_flow_snapshot is None:
        lines.append(f"- 暂不可用：{cash_flow_error}")
    else:
        if cash_flow_snapshot.cash_flows:
            cash_flow_summary = _summarize_cash_flows(cash_flow_snapshot.cash_flows)
            for currency, summary in sorted(cash_flow_summary.items()):
                total_usd = _fmt_usd_equivalent(summary["total"], currency)
                external_usd = _fmt_usd_equivalent(summary["external"], currency)
                lines.append(
                    f"- {currency}: 总流水 {_fmt_money(summary['total'])}{total_usd}, "
                    f"外部/非交易流水估算 {_fmt_money(summary['external'])}{external_usd}, "
                    f"记录 {int(summary['count'])} 条"
                )
            top_types = _top_cash_flow_types(cash_flow_snapshot.cash_flows)
            if top_types:
                lines.append("")
                lines.append("主要资金流水类型：")
                for item in top_types[:8]:
                    lines.append(
                        f"- {item['currency']} {item['type']}: {_fmt_money(item['amount'])}, {int(item['count'])} 条"
                    )
        else:
            lines.append("- 没有读取到资金流水记录。")
        for error in cash_flow_snapshot.errors[:3]:
            lines.append(f"- 提醒：{error}")

    usd_rollup = _performance_rollup_to_usd(
        position_summary=position_summary,
        deal_summary=deal_summary,
        cash_flow_summary=cash_flow_summary,
    )
    if usd_rollup:
        lines.extend(["", usd_heading])
        if "market_val" in usd_rollup:
            holding_label = "实时持仓" if is_historical_range else "当前持仓"
            lines.append(
                f"- {holding_label}市值约 {_fmt_money(usd_rollup['market_val'])} USD，"
                f"{holding_label}浮盈亏约 {_fmt_money(usd_rollup.get('pl_val', 0.0))} USD。"
            )
        if "net_trade_cash_flow" in usd_rollup:
            lines.append(f"- 区间净交易现金流约 {_fmt_money(usd_rollup['net_trade_cash_flow'])} USD。")
        if "external_cash_flow" in usd_rollup:
            lines.append(f"- 区间外部/非交易资金流水估算约 {_fmt_money(usd_rollup['external_cash_flow'])} USD。")
        lines.append("- 注意：这是为了阅读方便做的展示折算，不代表严格收益率。")

    lines.extend(
        [
            "",
            "估算判断：",
            "- 当前可以判断交易活跃度、现金流方向和大致美元口径规模，但还不能严谨计算区间净收益率。",
            "- 实时账户和实时持仓只作为参考；历史月份要准确复盘，需要查询区间内的账户快照、出入金、换汇和历史价格回放。",
            "",
            "下一步：我建议把 `本月收益` 固定为这个收益口径，把纯成交列表留给 `交易复盘`。",
        ]
    )
    return "\n".join(lines)


def _parse_snapshot_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _summarize_deals_by_currency(deals: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for deal in deals:
        currency = str(deal.get("currency") or "UNKNOWN").upper()
        bucket = result.setdefault(currency, {"buy_amount": 0.0, "sell_amount": 0.0, "count": 0.0})
        amount = _number(deal.get("amount"))
        side = str(deal.get("trd_side") or "").lower()
        if "sell" in side or "卖" in side:
            bucket["sell_amount"] += amount
        elif "buy" in side or "买" in side:
            bucket["buy_amount"] += amount
        bucket["count"] += 1
    return result


def _summarize_positions_by_currency(positions: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for item in positions:
        currency = _position_currency(item)
        bucket = result.setdefault(currency, {"market_val": 0.0, "pl_val": 0.0, "count": 0.0})
        bucket["market_val"] += _number(item.get("market_val"))
        bucket["pl_val"] += _number(item.get("pl_val"))
        bucket["count"] += 1
    return result


def _summarize_cash_flows(cash_flows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for item in cash_flows:
        currency = str(item.get("currency") or "UNKNOWN").upper()
        amount = _number(item.get("cashflow_amount"))
        bucket = result.setdefault(currency, {"total": 0.0, "external": 0.0, "count": 0.0})
        bucket["total"] += amount
        bucket["count"] += 1
        if _is_external_cash_flow(item):
            bucket["external"] += amount
    return result


def _deal_summary_to_usd(summary_by_currency: dict[str, dict[str, float]]) -> dict[str, float]:
    result = {"buy_amount": 0.0, "sell_amount": 0.0, "net_cash_flow": 0.0}
    has_value = False
    for currency, summary in summary_by_currency.items():
        rate = _fx_to_usd_rate(currency)
        if rate is None:
            continue
        has_value = True
        result["buy_amount"] += summary["buy_amount"] * rate
        result["sell_amount"] += summary["sell_amount"] * rate
        result["net_cash_flow"] += (summary["sell_amount"] - summary["buy_amount"]) * rate
    return result if has_value else {}


def _performance_rollup_to_usd(
    position_summary: dict[str, dict[str, float]],
    deal_summary: dict[str, dict[str, float]],
    cash_flow_summary: dict[str, dict[str, float]],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for currency, summary in position_summary.items():
        rate = _fx_to_usd_rate(currency)
        if rate is None:
            continue
        result["market_val"] = result.get("market_val", 0.0) + summary["market_val"] * rate
        result["pl_val"] = result.get("pl_val", 0.0) + summary["pl_val"] * rate
    for currency, summary in deal_summary.items():
        rate = _fx_to_usd_rate(currency)
        if rate is None:
            continue
        result["net_trade_cash_flow"] = (
            result.get("net_trade_cash_flow", 0.0)
            + (summary["sell_amount"] - summary["buy_amount"]) * rate
        )
    for currency, summary in cash_flow_summary.items():
        rate = _fx_to_usd_rate(currency)
        if rate is None:
            continue
        result["external_cash_flow"] = result.get("external_cash_flow", 0.0) + summary["external"] * rate
    return result


def _render_account_snapshot_history(snapshots: list[dict[str, Any]]) -> list[str]:
    lines = [f"- 本区间已保存账户快照 {len(snapshots)} 天。"]
    if len(snapshots) < 2:
        return lines

    first = snapshots[0]
    last = snapshots[-1]
    first_assets = _snapshot_total_assets(first)
    last_assets = _snapshot_total_assets(last)
    if first_assets is None or last_assets is None:
        lines.append("- 快照里缺少可比较的总资产字段，暂不展示资产变化。")
        return lines

    first_currency = _snapshot_account_currency(first)
    last_currency = _snapshot_account_currency(last)
    if first_currency and first_currency == last_currency:
        delta = last_assets - first_assets
        delta_usd = _fmt_usd_equivalent(delta, first_currency)
        lines.append(
            f"- 快照资产变化：{first.get('snapshot_date')} {_fmt_money(first_assets)} {first_currency} "
            f"-> {last.get('snapshot_date')} {_fmt_money(last_assets)} {last_currency}，"
            f"变化 {_fmt_money(delta)} {first_currency}{delta_usd}。"
        )
        lines.append("- 注意：这还没有扣除出入金/换汇影响，不能直接等同于收益。")
    else:
        first_label = first_currency or "UNKNOWN"
        last_label = last_currency or "UNKNOWN"
        lines.append(
            f"- 快照资产口径不一致或缺少币种：期初 {first_label}，期末 {last_label}；暂不做资产变化比较。"
        )
    return lines


def _snapshot_total_assets(snapshot: dict[str, Any]) -> float | None:
    account = snapshot.get("account_info") or {}
    if not isinstance(account, dict):
        return None
    value = account.get("total_assets")
    if value is None:
        return None
    return _number(value)


def _snapshot_account_currency(snapshot: dict[str, Any]) -> str | None:
    account = snapshot.get("account_info") or {}
    if not isinstance(account, dict):
        return None
    currency = str(account.get("currency") or "").strip().upper()
    return currency or None


def _current_fx_rates_for_snapshot() -> dict[str, Any]:
    return {
        currency: rate
        for currency in ("USD", "HKD", "CNY")
        if (rate := _fx_to_usd_rate(currency)) is not None
    }


def _top_cash_flow_types(cash_flows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in cash_flows:
        currency = str(item.get("currency") or "UNKNOWN").upper()
        flow_type = str(item.get("cashflow_type") or "UNKNOWN")
        key = (currency, flow_type)
        bucket = result.setdefault(key, {"currency": currency, "type": flow_type, "amount": 0.0, "count": 0.0})
        bucket["amount"] += _number(item.get("cashflow_amount"))
        bucket["count"] += 1
    return sorted(result.values(), key=lambda item: abs(item["amount"]), reverse=True)


def _is_external_cash_flow(item: dict[str, Any]) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("cashflow_type", "cashflow_remark", "cashflow_direction")
    ).lower()
    external_markers = (
        "deposit",
        "withdraw",
        "transfer",
        "fund",
        "入金",
        "出金",
        "存入",
        "提取",
        "转入",
        "转出",
        "换汇",
        "currency exchange",
        "interest",
        "dividend",
        "利息",
        "股息",
        "分红",
    )
    trade_markers = ("buy", "sell", "买入", "卖出", "交易", "成交")
    return any(marker in text for marker in external_markers) and not any(marker in text for marker in trade_markers)


def _top_traded_symbols(deals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for deal in deals:
        code = str(deal.get("code") or "")
        currency = str(deal.get("currency") or "UNKNOWN").upper()
        key = (code, currency)
        item = result.setdefault(
            key,
            {
                "code": code,
                "currency": currency,
                "name": str(deal.get("stock_name") or code or "unknown"),
                "amount": 0.0,
                "buy_count": 0.0,
                "sell_count": 0.0,
            },
        )
        item["amount"] += abs(_number(deal.get("amount")))
        side = str(deal.get("trd_side") or "").lower()
        if "sell" in side or "卖" in side:
            item["sell_count"] += 1
        elif "buy" in side or "买" in side:
            item["buy_count"] += 1
    return sorted(result.values(), key=lambda item: item["amount"], reverse=True)


def _fmt_trade_side(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if "buy" in lowered or "买" in text:
        return "买入"
    if "sell" in lowered or "卖" in text:
        return "卖出"
    return text or "-"


def _group_ipos(ipos: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    subscribable: list[dict[str, Any]] = []
    closed_pending_list: list[dict[str, Any]] = []
    listed_or_other: list[dict[str, Any]] = []

    for item in ipos:
        list_date = _parse_date(item.get("list_time"))
        if _is_subscribable(item.get("is_subscribe_status")):
            subscribable.append(item)
        elif list_date and list_date > today:
            closed_pending_list.append(item)
        else:
            listed_or_other.append(item)

    return [
        ("可申购", subscribable),
        ("已截止/待上市", closed_pending_list),
        ("已上市/其他", listed_or_other),
    ]


def _render_ipo_line(item: dict[str, Any]) -> str:
    name = _display_value(item.get("name"))
    code = _display_value(item.get("code"))
    return (
        f"- {name} {code}: 状态 {_fmt_ipo_status(item.get('is_subscribe_status'))}, "
        f"招股截止 {_display_value(item.get('apply_end_time'))}, "
        f"上市日 {_display_value(item.get('list_time'))}, "
        f"发行价 {_fmt_ipo_price(item)}, "
        f"每手 {_display_value(item.get('lot_size'))}, "
        f"入场费 {_display_value(item.get('entrance_price'))}, "
        "我的申购 暂未接入 IPO 申购/中签记录"
    )


def _ipo_sort_key(item: dict[str, Any]) -> tuple[int, str, str]:
    subscribable_rank = 0 if _is_subscribable(item.get("is_subscribe_status")) else 1
    return (
        subscribable_rank,
        str(item.get("apply_end_time") or "9999-99-99"),
        str(item.get("list_time") or "9999-99-99"),
    )


def _is_subscribable(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on", "认购中", "可申购"}
    return False


def _fmt_ipo_status(value: Any) -> str:
    if _is_subscribable(value):
        return "可申购"
    if value is None:
        return "不可申购/待更新"
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "不可申购"


def _fmt_ipo_price(item: dict[str, Any]) -> str:
    min_price = item.get("ipo_price_min")
    max_price = item.get("ipo_price_max")
    list_price = item.get("list_price")
    if min_price is not None and max_price is not None:
        if str(min_price) == str(max_price):
            return str(min_price)
        return f"{min_price}-{max_price}"
    if list_price is not None:
        return str(list_price)
    if min_price is not None:
        return str(min_price)
    if max_price is not None:
        return str(max_price)
    return "-"


def _display_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        value = value.strip()
        return value if value else "-"
    return str(value)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text[:10], text):
        for pattern in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
    return None


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_money(value: float) -> str:
    if abs(value) < 0.005:
        value = 0.0
    return f"{value:,.2f}"


def _fmt_usd_equivalent(value: float, currency: str) -> str:
    if str(currency or "").strip().upper() == "USD":
        return ""
    rate = _fx_to_usd_rate(currency)
    if rate is None:
        return ""
    return f"（≈ {_fmt_money(value * rate)} USD）"


def _fx_to_usd_rate(currency: str) -> float | None:
    normalized = str(currency or "").strip().upper()
    if not normalized or normalized == "UNKNOWN":
        return None
    env_key = f"FX_TO_USD_{normalized}"
    if os.getenv(env_key):
        return _positive_number(os.getenv(env_key))
    if normalized == "HKD" and os.getenv("FX_USD_HKD"):
        usd_hkd = _positive_number(os.getenv("FX_USD_HKD"))
        return 1.0 / usd_hkd if usd_hkd else None
    return DEFAULT_FX_TO_USD.get(normalized)


def _fx_disclaimer() -> str:
    usd_hkd = os.getenv("FX_USD_HKD")
    hkd_to_usd = os.getenv("FX_TO_USD_HKD")
    if usd_hkd:
        return f"1 USD = {usd_hkd} HKD（来自环境变量 FX_USD_HKD）；未配置实时汇率。"
    if hkd_to_usd:
        return f"1 HKD = {hkd_to_usd} USD（来自环境变量 FX_TO_USD_HKD）；未配置实时汇率。"
    return "默认 1 USD = 7.80 HKD，USD 原币不折算；未配置实时汇率。"


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    return number if number > 0 else None


def _position_currency(item: dict[str, Any]) -> str:
    currency = str(item.get("currency") or "").strip().upper()
    if currency:
        return currency
    code = str(item.get("code") or "")
    market = code.split(".", 1)[0].upper() if "." in code else ""
    return DEFAULT_CURRENCY_BY_MARKET.get(market, "UNKNOWN")


def _fmt_percent(value: float) -> str:
    if abs(value) <= 1:
        value *= 100
    return f"{value:.2f}%"


def _render_stock_brief_analysis(context: dict[str, Any]) -> str:
    stock = context["stock"]
    display_name = stock.get("name") or stock["symbol"]
    lines = [
        f"基于当前知识库，我对 {display_name} 的第一版看法如下：",
        "",
        "核心判断：",
        _stock_thesis(context),
        "",
        "主要看点：",
    ]
    lines.extend(_bullet_lines(_stock_watch_points(context), empty="当前知识库里的事实知识还不够，需要继续补资料。"))
    lines.extend(["", "主要风险："])
    lines.extend(_bullet_lines(_stock_risks(context), empty="当前知识库还没有沉淀明确风险项。"))
    lines.extend(["", "结合你的历史偏好："])
    lines.extend(_bullet_lines(_user_preference_points(context), empty="目前还没有足够的相关用户心得。"))

    candidates = _candidate_count(context)
    if candidates:
        lines.extend(["", f"还有 {candidates} 条待确认候选心得，建议之后处理一下，避免系统把未确认观点当成正式偏好。"])
    lines.extend(["", "注：这不是实时行情判断，只基于当前已入库资料和心得。"])
    return "\n".join(lines)


def _stock_thesis(context: dict[str, Any]) -> str:
    stock = context["stock"]
    business = stock.get("core_business")
    sectors = context.get("sectors") or []
    sector_paths = [sector.get("path") for sector in sectors if sector.get("path")]
    if business and sector_paths:
        business_text = str(business).rstrip("。；; ")
        return f"- 核心业务：{business_text}；当前主要归在{sector_paths[0]}这条线里。"
    if business:
        return f"- 核心业务：{business}"
    if sector_paths:
        return f"- 当前主要可以先按{sector_paths[0]}这条线理解。"
    return "- 当前画像还偏薄，适合作为待补资料标的，而不是直接下结论。"


def _stock_watch_points(context: dict[str, Any]) -> list[str]:
    points: list[str] = []
    stock = context["stock"]
    if stock.get("notable_history"):
        points.append(f"历史脉络：{stock['notable_history']}")
    if stock.get("stock_character"):
        points.append(f"股性/交易特征：{stock['stock_character']}")
    for item in (context.get("stock_knowledge") or [])[:3]:
        if item.get("content"):
            points.append(str(item["content"]))
    for item in (context.get("sector_knowledge") or [])[:2]:
        if item.get("content"):
            points.append(f"板块相关：{item['content']}")
    return points


def _stock_risks(context: dict[str, Any]) -> list[str]:
    risks: list[str] = []
    for item in [*(context.get("stock_insights") or []), *(context.get("sector_insights") or [])]:
        text = item.get("normalized_summary") or item.get("insight")
        if text and any(keyword in text for keyword in ["风险", "警惕", "拥挤", "追高", "周期", "反转"]):
            risks.append(str(text))
    if context.get("stock_candidate_insights") or context.get("sector_candidate_insights"):
        risks.append("还有待确认候选心得，相关观点暂时不能当成正式用户偏好。")
    return _dedupe(risks)[:4]


def _user_preference_points(context: dict[str, Any]) -> list[str]:
    points: list[str] = []
    insight_groups = [
        context.get("stock_insights") or [],
        context.get("sector_insights") or [],
        context.get("global_insights") or [],
    ]
    for group in insight_groups:
        for item in group[:3]:
            text = item.get("normalized_summary") or item.get("insight")
            if text:
                points.append(str(text))
    return _dedupe(points)[:5]


def _bullet_lines(items: list[str], empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _help_text() -> str:
    return """支持的指令：
- 我的持仓
- 持仓分析
- 持仓图谱
- 研究草稿 09988 HK
- 全持仓研究草稿
- 创建持仓研究任务
- 查看研究任务
- 持仓图谱补全
- 今天仓位怎么看
- 组合体检
- 港股新股
- 交易记录 2026-05
- 交易记录 2026-05-01 2026-05-29
- 补全交易记录 2026-05
- 本月收益
- 本周复盘
- 复盘 2026-06-08 2026-06-14
- 查看下周节奏
- 富途状态
- 富途登录
- 富途请求验证码
- 富途验证码 123456
- 富途重登录
- 系统状态
- 云端状态
- 最近错误
- worker日志
- mcp日志
- IPO提醒状态
- 估值方法
- valuation US.INTC
- 查看估值 US.INTC
- 决策 US.INTC
- 决策 000660 KR
- 分析 000660 KR
- 怎么看海力士
- 分析一下腾讯
- 查看候选心得
- 确认候选心得 6
- 拒绝候选心得 5
- 创建开发任务 帮我修一下本月收益的展示格式
- 查看开发任务
- 记录心得 000660 KR 这里写你的正式心得
- 提出个股候选心得 000660 KR 这里写系统推断出的候选心得
- 记录组合心得 这里写你的正式组合心得
- 提出策略候选心得 这里写系统推断出的候选策略心得
- 也可以自然说：我觉得港股亏损股太消耗精力了 / 帮我看看本月赚在哪亏在哪 / 帮我修一下部署脚本报错
"""
