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
