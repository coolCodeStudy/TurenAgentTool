from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.analysis_provider import generate_stock_analysis_with_openai
from investment_knowledge_mcp.futu_provider import FutuProviderError, get_futu_positions
from scripts.build_analysis_context import render_stock_context


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str


def handle_command(
    command: str,
    output_dir: Path | None = None,
    include_artifact_path: bool = True,
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
        )

    ambiguous_match = re.fullmatch(r"__AMBIGUOUS_STOCK__\s+(.+)", cleaned)
    if ambiguous_match:
        return CommandResult(ok=False, message=f"匹配到多个股票，请说得更具体一点：{ambiguous_match.group(1)}")

    stock_match = re.fullmatch(r"(?:分析|analyze)\s+(\S+)\s+(\S+)", cleaned, flags=re.IGNORECASE)
    if stock_match:
        symbol, market = stock_match.groups()
        return _handle_analyze_stock(
            symbol=symbol,
            market=market,
            output_dir=output_dir,
            include_artifact_path=include_artifact_path,
        )

    if cleaned in {"查看候选心得", "候选心得", "list candidates", "candidates"}:
        return _handle_list_candidates()

    if cleaned in {"我的持仓", "我的仓位", "当前持仓", "当前仓位", "持仓", "仓位", "portfolio", "positions"}:
        return _handle_portfolio_positions()

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


def is_query_command(command: str) -> bool:
    cleaned = command.strip()
    normalized = _normalize_natural_command(cleaned)
    return bool(
        re.fullmatch(r"(?:分析|analyze)\s+\S+\s+\S+", normalized, flags=re.IGNORECASE)
        or normalized
        in {
            "查看候选心得",
            "候选心得",
            "list candidates",
            "candidates",
            "帮助",
            "help",
            "?",
            "我的持仓",
            "我的仓位",
            "当前持仓",
            "当前仓位",
            "持仓",
            "仓位",
            "portfolio",
            "positions",
        }
        or _extract_stock_query(normalized) is not None
        or normalized.startswith("__AMBIGUOUS_STOCK__")
    )


def _handle_analyze_stock(
    symbol: str,
    market: str,
    output_dir: Path,
    include_artifact_path: bool,
) -> CommandResult:
    context = repository.get_stock_context(symbol=symbol, market=market)
    if not context.get("stock"):
        return CommandResult(ok=False, message=f"未找到股票：{symbol} {market}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{symbol.upper()}_{market.upper()}_analysis_context.md"
    output_path.write_text(render_stock_context(context) + "\n", encoding="utf-8")

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
        lines.append(
            f"- [{candidate['id']}] {candidate['target_type']}:{candidate['target_id']} "
            f"{candidate['insight']}"
        )
    return CommandResult(ok=True, message="\n".join(lines))


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


def _normalize_natural_command(command: str) -> str:
    cleaned = command.strip()
    compact = _strip_trailing_punctuation(cleaned)

    if compact in {"候选", "候选心得", "有什么候选心得", "有哪些候选心得", "待确认心得"}:
        return "查看候选心得"
    if compact in {"帮助", "怎么用", "能做什么", "help", "?"}:
        return "帮助"

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


def _strip_trailing_punctuation(value: str) -> str:
    return value.strip().strip("？?。.!！,， ")


def _render_portfolio_positions(snapshot: Any) -> str:
    positions = snapshot.positions
    fetched_at = snapshot.fetched_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    if not positions:
        return f"当前富途持仓为空。\n数据时间：{fetched_at}"

    total_market_value = sum(_number(item.get("market_val")) for item in positions)
    total_pl = sum(_number(item.get("pl_val")) for item in positions)
    sorted_positions = sorted(
        positions,
        key=lambda item: _number(item.get("market_val")),
        reverse=True,
    )

    lines = [
        "富途实时持仓：",
        f"- 持仓数量：{len(positions)}",
        f"- 总市值：{_fmt_money(total_market_value)}",
        f"- 浮动盈亏：{_fmt_money(total_pl)}",
        f"- 数据时间：{fetched_at}" + ("（短缓存）" if snapshot.cached else ""),
        "",
        "主要持仓：",
    ]
    for item in sorted_positions[:10]:
        name = item.get("stock_name") or item.get("code") or "unknown"
        code = item.get("code") or ""
        market_val = _number(item.get("market_val"))
        weight = market_val / total_market_value * 100 if total_market_value else 0
        pl_ratio = _number(item.get("pl_ratio"))
        lines.append(
            f"- {name} {code}: 市值 {_fmt_money(market_val)}, "
            f"占比 {weight:.1f}%, 盈亏 {_fmt_percent(pl_ratio)}"
        )
    if len(sorted_positions) > 10:
        lines.append(f"- 其余 {len(sorted_positions) - 10} 个持仓已省略。")
    lines.append("")
    lines.append("注：当前只读持仓，不会下单或修改账户。")
    return "\n".join(lines)


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}"


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
- 分析 000660 KR
- 怎么看海力士
- 分析一下腾讯
- 查看候选心得
- 确认候选心得 6
- 拒绝候选心得 5
- 记录心得 000660 KR 这里写你的正式心得
- 提出个股候选心得 000660 KR 这里写系统推断出的候选心得
"""
