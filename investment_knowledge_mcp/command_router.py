from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from investment_knowledge_mcp import repository
from scripts.build_analysis_context import render_stock_context


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str


def handle_command(command: str, output_dir: Path | None = None) -> CommandResult:
    cleaned = command.strip()
    if not cleaned:
        return CommandResult(ok=False, message=_help_text())

    output_dir = output_dir or Path("drafts")

    stock_match = re.fullmatch(r"(?:分析|analyze)\s+(\S+)\s+(\S+)", cleaned, flags=re.IGNORECASE)
    if stock_match:
        symbol, market = stock_match.groups()
        return _handle_analyze_stock(symbol=symbol, market=market, output_dir=output_dir)

    if cleaned in {"查看候选心得", "候选心得", "list candidates", "candidates"}:
        return _handle_list_candidates()

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

    candidate_stock_match = re.fullmatch(
        r"(?:提出个股候选心得|候选个股心得)\s+(\S+)\s+(\S+)\s+(.+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if candidate_stock_match:
        symbol, market, insight = candidate_stock_match.groups()
        return _handle_propose_stock_candidate(symbol=symbol, market=market, insight=insight)

    if cleaned in {"帮助", "help", "?"}:
        return CommandResult(ok=True, message=_help_text())

    return CommandResult(
        ok=False,
        message="无法识别这条指令。\n\n" + _help_text(),
    )


def _handle_analyze_stock(symbol: str, market: str, output_dir: Path) -> CommandResult:
    context = repository.get_stock_context(symbol=symbol, market=market)
    if not context.get("stock"):
        return CommandResult(ok=False, message=f"未找到股票：{symbol} {market}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol.upper()}_{market.upper()}_analysis_context.md"
    output_path.write_text(render_stock_context(context) + "\n", encoding="utf-8")

    stock = context["stock"]
    return CommandResult(
        ok=True,
        message=(
            f"已生成 {stock.get('name') or stock['symbol']} 分析上下文：{output_path}\n"
            f"- 个股知识：{len(context.get('stock_knowledge') or [])}\n"
            f"- 个股心得：{len(context.get('stock_insights') or [])}\n"
            f"- 待确认候选：{_candidate_count(context)}"
        ),
    )


def _handle_list_candidates() -> CommandResult:
    candidates = repository.list_candidate_insights(status="pending")
    if not candidates:
        return CommandResult(ok=True, message="暂无待确认候选心得。")

    lines = ["待确认候选心得："]
    for candidate in candidates:
        lines.append(
            f"- [{candidate['id']}] {candidate['target_type']}:{candidate['target_id']} "
            f"{candidate['insight']}"
        )
    return CommandResult(ok=True, message="\n".join(lines))


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


def _handle_record_stock_insight(symbol: str, market: str, insight: str) -> CommandResult:
    row = repository.record_user_insight(
        target_type="stock",
        symbol=symbol,
        market=market,
        insight=insight,
    )
    return CommandResult(ok=True, message=f"已记录个股心得 id={row['id']}。")


def _handle_propose_stock_candidate(symbol: str, market: str, insight: str) -> CommandResult:
    row = repository.propose_candidate_insight(
        target_type="stock",
        symbol=symbol,
        market=market,
        insight=insight,
        reason="来自统一指令入口的候选心得，需要用户确认。",
    )
    return CommandResult(ok=True, message=f"已提出候选心得 id={row['id']}，等待确认。")


def _candidate_count(context: dict) -> int:
    return (
        len(context.get("stock_candidate_insights") or [])
        + len(context.get("sector_candidate_insights") or [])
        + len(context.get("global_candidate_insights") or [])
    )


def _help_text() -> str:
    return """支持的指令：
- 分析 000660 KR
- 查看候选心得
- 确认候选心得 6
- 拒绝候选心得 5
- 记录心得 000660 KR 这里写你的正式心得
- 提出个股候选心得 000660 KR 这里写系统推断出的候选心得
"""
