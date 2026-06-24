from __future__ import annotations

import json
import os
from typing import Any

import httpx

from investment_knowledge_mcp.model_providers.openai_provider import extract_response_text
from scripts.build_analysis_context import render_stock_context


RESPONSES_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.2"


def route_command_intent_with_openai(command: str) -> dict[str, Any] | None:
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
                    "你是 InvestmentKnowledge 的意图路由器。只输出 JSON，不要输出解释。"
                    "你的任务是把用户自然语言映射到安全意图；不要执行动作。"
                ),
            },
            {
                "role": "user",
                "content": build_intent_router_prompt(command),
            },
        ],
        "max_output_tokens": 900,
    }

    with httpx.Client(timeout=60) as client:
        response = client.post(
            RESPONSES_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    text = extract_response_text(response.json()).strip()
    return _parse_json_object(text)


def propose_command_workbench_parse_with_openai(
    command: str,
    *,
    registry_summary: list[dict[str, Any]],
    entity_candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
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
                    "You are the bounded parser for the InvestmentKnowledge Command Workbench. "
                    "Return only JSON. Propose a registered action and fields; never execute anything."
                ),
            },
            {
                "role": "user",
                "content": build_command_workbench_parse_prompt(
                    command,
                    registry_summary=registry_summary,
                    entity_candidates=entity_candidates,
                ),
            },
        ],
        "max_output_tokens": 450,
    }

    with httpx.Client(timeout=45) as client:
        response = client.post(
            RESPONSES_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()

    text = extract_response_text(response.json()).strip()
    return _parse_json_object(text)


def build_command_workbench_parse_prompt(
    command: str,
    *,
    registry_summary: list[dict[str, Any]],
    entity_candidates: list[dict[str, Any]],
) -> str:
    return f"""Map the user input to a Command Workbench parse proposal.

Allowed action registry:
{json.dumps(registry_summary, ensure_ascii=False)}

Local entity candidates:
{json.dumps(entity_candidates[:8], ensure_ascii=False)}

Return JSON:
{{
  "action_id": "one registered id or unsupported",
  "fields": {{"stock": "target text if any", "service": "service name if any"}},
  "confidence": 0.0,
  "reason": "short reason"
}}

Rules:
- Do not invent actions outside the registry.
- Do not choose an ambiguous entity silently.
- Do not output an exact command.
- If the request is trading, deployment, or unsupported maintenance, use action_id "unsupported".
- Keep fields short; do not include portfolio data, reports, or long context.

User input:
{command}
"""


def build_intent_router_prompt(command: str) -> str:
    return f"""请把用户输入路由成一个 JSON 对象。

允许的 intent：
- portfolio_analysis：用户想分析持仓/仓位/组合风险。
- portfolio_positions：用户想看当前持仓列表。
- ipo_status：用户想看港股新股、IPO 或 IPO 提醒状态。
- system_status：用户想检查系统、部署、OpenD、OpenAI、机器人是否正常。
- trade_review：用户想看交易记录、收益复盘、月度/区间收益。
- coding_task：用户想让系统修代码、改功能、排查 bug、调整部署、创建开发任务。
- memory_candidate：用户在表达可沉淀为组合/策略记忆的观点、偏好、痛点、目标或复盘反思。
- unknown：不确定。

输出 JSON schema：
{{
  "intent": "portfolio_analysis|portfolio_positions|ipo_status|system_status|trade_review|coding_task|memory_candidate|unknown",
  "confidence": 0.0,
  "target_type": "portfolio|strategy|null",
  "memory_candidate": "适合写入候选心得的一句话；仅 memory_candidate 使用，否则 null",
  "coding_task": "适合作为开发任务标题的一句话；仅 coding_task 使用，否则 null",
  "reason": "一句话说明为什么这样路由",
  "time_range": "用户提到的月份或日期范围；仅 trade_review 使用，否则 null"
}}

安全规则：
- 不要把用户观点直接标成正式心得，只能作为 memory_candidate。
- 如果用户是在说系统长期目标、投资方式、管理成本、复盘方式，target_type 多数为 strategy。
- 如果用户是在说当前组合、仓位结构、某组持仓风险，target_type 多数为 portfolio。
- 如果用户问“为什么没提醒/机器人没反应/系统有没有问题”，路由 system_status 或 ipo_status。
- 如果用户问“这个月赚在哪亏在哪/交易记录/收益”，路由 trade_review。
- 如果用户让你“修/改/实现/优化/部署/排查”某个系统或代码问题，路由 coding_task，不要假装已经改完。

用户输入：
{command}
"""


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


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
        "currency_exposure": context.get("currency_exposure"),
        "market_exposure": context.get("market_exposure"),
        "top_positions": context.get("top_positions"),
        "top_positions_by_currency": context.get("top_positions_by_currency"),
        "profit_leaders": context.get("profit_leaders"),
        "loss_leaders": context.get("loss_leaders"),
        "loss_leaders_by_currency": context.get("loss_leaders_by_currency"),
        "large_loss_positions": context.get("large_loss_positions"),
        "knowledge_matches": _compact_knowledge_matches(context.get("knowledge_matches") or []),
        "global_insights": context.get("global_insights"),
        "global_candidate_insights": context.get("global_candidate_insights"),
        "context_warnings": context.get("context_warnings"),
        "data_quality_warnings": context.get("data_quality_warnings"),
    }
    return f"""请基于下面的 InvestmentKnowledge 持仓上下文，输出一版中文组合复盘。

要求：
- 不要给买入/卖出/申购等操作指令，只做结构、风险和后续跟踪分析。
- 不要声称知道实时新闻、公告、财报或估值，除非上下文明确给出。
- 先讲数据口径，再讲组合结构、风险和你的一版看法。
- 要结合用户已确认的 portfolio/strategy 级心得；候选心得只能提示待确认。
- 如果 summary.has_mixed_currency=true，严禁输出“总市值约 X”“Top3 占比 X”这类跨币种合计结论；只能按币种/市场分组讨论，或明确说明未配置汇率换算。
- 如果 summary.top_weights_available=false，不要把 top_positions.weight 当作可用结论；主要持仓和拖累项优先使用 top_positions_by_currency / loss_leaders_by_currency，并用 currency_weight 描述币种内占比。
- 用词要直接、少套话，适合钉钉阅读；每段 2 到 4 条，宁可短一点。

输出格式：
## 数据口径
- 2 到 3 条，必须说明是否多币种、是否能合计总市值

## 组合概览
- 2 到 4 条

## 仓位结构
- 2 到 4 条

## 主要风险
- 2 到 4 条

## 我的看法
- 2 到 4 条

## 后续跟踪
- 2 到 3 条

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
