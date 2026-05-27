from __future__ import annotations

import json
import os
from typing import Any

import httpx

from investment_knowledge_mcp.model_providers.openai_provider import extract_response_text
from scripts.build_analysis_context import render_stock_context


RESPONSES_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.2"


def generate_stock_analysis_with_openai(context: dict[str, Any]) -> str | None:
    if os.getenv("OPENAI_ANALYSIS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    prompt = build_stock_analysis_prompt(context)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "你是一个谨慎的投资研究助理。只基于用户提供的知识库上下文分析，"
                    "不要编造实时行情、估值、新闻或未给出的事实。"
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "max_output_tokens": 1800,
    }

    with httpx.Client(timeout=120) as client:
        response = client.post(
            RESPONSES_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    return extract_response_text(response.json()).strip()


def generate_portfolio_analysis_with_openai(context: dict[str, Any]) -> str | None:
    if os.getenv("OPENAI_ANALYSIS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "你是一个谨慎的组合复盘助理。只基于用户提供的持仓和知识库上下文分析，"
                    "不要编造实时行情、新闻、公告或未给出的事实；不要给下单建议。"
                ),
            },
            {
                "role": "user",
                "content": build_portfolio_analysis_prompt(context),
            },
        ],
        "max_output_tokens": 2200,
    }

    with httpx.Client(timeout=120) as client:
        response = client.post(
            RESPONSES_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    return extract_response_text(response.json()).strip()


def build_portfolio_analysis_prompt(context: dict[str, Any]) -> str:
    compact_context = {
        "snapshot": context.get("snapshot"),
        "summary": context.get("summary"),
        "market_exposure": context.get("market_exposure"),
        "top_positions": context.get("top_positions"),
        "profit_leaders": context.get("profit_leaders"),
        "loss_leaders": context.get("loss_leaders"),
        "large_loss_positions": context.get("large_loss_positions"),
        "knowledge_matches": _compact_knowledge_matches(context.get("knowledge_matches") or []),
        "global_insights": context.get("global_insights"),
        "global_candidate_insights": context.get("global_candidate_insights"),
        "context_warnings": context.get("context_warnings"),
    }
    return f"""请基于下面的 InvestmentKnowledge 持仓上下文，输出一版中文组合复盘。

要求：
- 不要给买入/卖出/申购等操作指令，只做结构、风险和后续跟踪分析。
- 不要声称知道实时新闻、公告、财报或估值，除非上下文明确给出。
- 先讲组合结构和风险，再讲你的一版看法。
- 要结合用户已确认的 portfolio/strategy 级心得；候选心得只能提示待确认。
- 适合钉钉阅读，不要太长。

输出格式：
## 组合概览
- 3 到 5 条

## 仓位结构
- 3 到 5 条

## 主要风险
- 3 到 5 条

## 我的看法
- 3 到 5 条

## 后续跟踪
- 2 到 4 条

上下文 JSON：
```json
{json.dumps(compact_context, ensure_ascii=False, indent=2)}
```
"""


def _compact_knowledge_matches(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in matches[:12]:
        compact.append(
            {
                "position": item.get("position"),
                "stock": item.get("stock"),
                "sectors": [
                    {
                        "path": sector.get("path"),
                        "relation_type": sector.get("relation_type"),
                    }
                    for sector in item.get("sectors", [])[:3]
                ],
                "stock_insights": item.get("stock_insights", [])[:2],
                "sector_insights": item.get("sector_insights", [])[:2],
                "stock_knowledge": item.get("stock_knowledge", [])[:2],
            }
        )
    return compact


def build_stock_analysis_prompt(context: dict[str, Any]) -> str:
    stock = context.get("stock") or {}
    display_name = stock.get("name") or stock.get("symbol") or "该股票"
    source_context = render_stock_context(context)
    compact_payload = {
        "stock": context.get("stock"),
        "sectors": context.get("sectors"),
        "stock_knowledge_count": len(context.get("stock_knowledge") or []),
        "stock_insight_count": len(context.get("stock_insights") or []),
        "sector_insight_count": len(context.get("sector_insights") or []),
        "global_insight_count": len(context.get("global_insights") or []),
        "pending_candidate_count": _candidate_count(context),
    }
    return f"""请基于下面的 InvestmentKnowledge 上下文，输出一版中文投资分析。

要求：
- 不要给买卖建议，不要使用“应该买入/卖出”这类结论。
- 不要声称知道实时股价、最新公告或数据库以外的信息。
- 如果信息不足，要明确说“当前知识库不足”。
- 要结合用户已确认心得；待确认候选心得只能提示为待确认，不能当成正式偏好。
- 输出尽量短，适合在钉钉里阅读。

输出格式：
## {display_name}：核心判断
- 2 到 4 条要点

## 主要看点
- 3 到 5 条要点

## 主要风险
- 2 到 4 条要点

## 和用户偏好的关系
- 2 到 4 条要点

## 后续跟踪
- 2 到 4 条要点

统计摘要：
```json
{json.dumps(compact_payload, ensure_ascii=False, indent=2)}
```

完整上下文：
```markdown
{source_context}
```
"""


def _candidate_count(context: dict[str, Any]) -> int:
    return (
        len(context.get("stock_candidate_insights") or [])
        + len(context.get("sector_candidate_insights") or [])
        + len(context.get("global_candidate_insights") or [])
    )
