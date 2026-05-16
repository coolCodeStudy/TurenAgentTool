from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from investment_knowledge_mcp.repository import get_stock_context


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a stock analysis context document.")
    parser.add_argument("symbol", help="Stock symbol, for example 000660.")
    parser.add_argument("market", help="Market code, for example KR.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional markdown output path. Defaults to stdout.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw context JSON instead of markdown.",
    )
    args = parser.parse_args()

    context = get_stock_context(symbol=args.symbol, market=args.market)
    if args.json:
        output = json.dumps(context, ensure_ascii=False, indent=2)
    else:
        output = render_stock_context(context)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"Analysis context written to {args.output}")
    else:
        print(output)


def render_stock_context(context: dict[str, Any]) -> str:
    stock = context.get("stock")
    if not stock:
        return "# 个股分析上下文\n\n未找到股票。"

    lines: list[str] = [
        f"# {stock.get('name') or stock['symbol']} 分析上下文",
        "",
        "## 股票画像",
        "",
        f"- 代码：{stock['symbol']}",
        f"- 市场：{stock['market']}",
        f"- 名称：{stock.get('name') or ''}",
        f"- 核心业务：{stock.get('core_business') or ''}",
        f"- 股权结构：{stock.get('equity_structure') or ''}",
        f"- 股性：{stock.get('stock_character') or ''}",
        f"- 突出历史：{stock.get('notable_history') or ''}",
        "",
        "## 板块归属",
        "",
    ]

    sectors = context.get("sectors") or []
    if sectors:
        for sector in sectors:
            confidence = _format_confidence(sector.get("confidence"))
            lines.append(
                f"- `{sector.get('relation_type')}` {sector.get('path')} "
                f"(confidence={confidence}, confirmed={sector.get('confirmed_by_user')})"
            )
            if sector.get("description"):
                lines.append(f"  - 描述：{sector['description']}")
            if sector.get("recent_status"):
                lines.append(f"  - 近况：{sector['recent_status']}")
    else:
        lines.append("- 暂无")

    lines.extend(["", "## 个股事实知识", ""])
    _append_knowledge(lines, context.get("stock_knowledge") or [])

    lines.extend(["", "## 个股用户心得", ""])
    _append_insights(lines, context.get("stock_insights") or [])

    lines.extend(["", "## 待确认个股候选心得", ""])
    _append_candidate_insights(lines, context.get("stock_candidate_insights") or [])

    lines.extend(["", "## 相关板块知识", ""])
    _append_knowledge(lines, context.get("sector_knowledge") or [])

    lines.extend(["", "## 相关板块心得", ""])
    _append_insights(lines, context.get("sector_insights") or [])

    lines.extend(["", "## 待确认板块候选心得", ""])
    _append_candidate_insights(lines, context.get("sector_candidate_insights") or [])

    lines.extend(["", "## 组合/策略级用户偏好", ""])
    _append_insights(lines, context.get("global_insights") or [])

    lines.extend(["", "## 待确认组合/策略候选心得", ""])
    _append_candidate_insights(lines, context.get("global_candidate_insights") or [])

    lines.extend(["", "## 来源", ""])
    sources = context.get("sources") or []
    if sources:
        for source in sources:
            title = source.get("title") or f"source-{source['id']}"
            publisher = source.get("publisher") or ""
            url = source.get("url")
            if url:
                lines.append(f"- [{source['id']}] [{title}]({url}) {publisher}".rstrip())
            else:
                lines.append(f"- [{source['id']}] {title} {publisher}".rstrip())
    else:
        lines.append("- 暂无")

    return "\n".join(lines)


def _append_knowledge(lines: list[str], items: list[dict[str, Any]]) -> None:
    if not items:
        lines.append("- 暂无")
        return
    for item in items:
        confidence = _format_confidence(item.get("confidence"))
        source = _format_source_suffix(item)
        lines.append(
            f"- `{item.get('knowledge_type')}` confidence={confidence}, "
            f"confirmed={item.get('confirmed_by_user')}{source}"
        )
        lines.append(f"  - {item.get('content')}")


def _append_insights(lines: list[str], items: list[dict[str, Any]]) -> None:
    if not items:
        lines.append("- 暂无")
        return
    for item in items:
        tags = item.get("tags") or []
        tag_suffix = f" tags={tags}" if tags else ""
        lines.append(f"- `{item.get('target_type')}`{tag_suffix}")
        lines.append(f"  - 原文：{item.get('insight')}")
        if item.get("normalized_summary"):
            lines.append(f"  - 摘要：{item['normalized_summary']}")


def _append_candidate_insights(lines: list[str], items: list[dict[str, Any]]) -> None:
    if not items:
        lines.append("- 暂无")
        return
    for item in items:
        tags = item.get("tags") or []
        tag_suffix = f" tags={tags}" if tags else ""
        lines.append(f"- [{item['id']}] `{item.get('target_type')}`{tag_suffix}")
        lines.append(f"  - 候选：{item.get('insight')}")
        if item.get("normalized_summary"):
            lines.append(f"  - 摘要：{item['normalized_summary']}")
        if item.get("reason"):
            lines.append(f"  - 提出原因：{item['reason']}")


def _format_source_suffix(item: dict[str, Any]) -> str:
    source_id = item.get("source_id")
    if source_id is None:
        return ""
    title = item.get("source_title")
    if title:
        return f", source=[{source_id}] {title}"
    return f", source=[{source_id}]"


def _format_confidence(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.3f}"
    return str(value)


if __name__ == "__main__":
    main()
