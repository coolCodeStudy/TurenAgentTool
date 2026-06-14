from __future__ import annotations

from typing import Any


DECISION_CARD_LIMIT = 3


def build_stock_decision_card(
    context: dict[str, Any],
    *,
    latest_research_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stock = context.get("stock")
    if not stock:
        return {
            "stock": None,
            "one_line_thesis": "",
            "key_drivers": [],
            "core_risks": [],
            "watch_items": [],
            "data_freshness": "no stock profile",
            "source_status": "0 sources",
            "audit_status": "unknown",
            "knowledge_count": 0,
            "source_count": 0,
        }

    stock_knowledge = list(context.get("stock_knowledge") or context.get("knowledge_items") or [])
    sources = list(context.get("sources") or [])
    source_count = len(sources)
    knowledge_count = len(stock_knowledge)
    grouped = _group_knowledge(stock_knowledge)

    business_items = grouped.get("business", [])
    thesis = _first_text(
        [
            stock.get("core_business"),
            *_contents(business_items),
            stock.get("stock_character"),
        ]
    )
    key_drivers = _pick_items(
        [
            *_contents(business_items),
            *_contents(grouped.get("sector_logic", [])),
            stock.get("notable_history"),
        ]
    )
    core_risks = _pick_items(_contents(grouped.get("risk", [])))
    watch_items = _pick_items(_contents(grouped.get("watch_item", [])))

    stale_after = _latest_text_value(item.get("stale_after") for item in stock_knowledge)
    latest_source_date = _latest_text_value(source.get("published_at") for source in sources)
    data_freshness = _data_freshness(latest_source_date=latest_source_date, stale_after=stale_after)

    return {
        "stock": {
            "symbol": stock.get("symbol"),
            "market": stock.get("market"),
            "name": stock.get("name"),
        },
        "one_line_thesis": _truncate_sentence(thesis) or "暂无明确 thesis，需补充业务和投资逻辑事实。",
        "key_drivers": key_drivers,
        "core_risks": core_risks or ["暂无显式风险条目，需补充 risk 类型事实。"],
        "watch_items": watch_items or ["暂无显式跟踪项，需补充 watch_item 类型事实。"],
        "data_freshness": data_freshness,
        "source_status": _source_status(source_count),
        "audit_status": _audit_status(latest_research_job),
        "knowledge_count": knowledge_count,
        "source_count": source_count,
    }


def render_stock_decision_card(card: dict[str, Any]) -> str:
    stock = card.get("stock") or {}
    if not stock:
        return "未找到股票。"

    symbol = stock.get("symbol") or ""
    market = stock.get("market") or ""
    name = stock.get("name") or ""
    title = f"{symbol} {market}".strip()
    if name:
        title = f"{title} ({name})"

    lines = [
        title,
        f"Thesis: {card.get('one_line_thesis') or '暂无'}",
        "Drivers:",
    ]
    lines.extend(_render_bullets(card.get("key_drivers") or ["暂无明确驱动条目。"]))
    lines.append("Risks:")
    lines.extend(_render_bullets(card.get("core_risks") or ["暂无显式风险条目。"]))
    lines.append("Watch:")
    lines.extend(_render_bullets(card.get("watch_items") or ["暂无显式跟踪项。"]))
    lines.append(f"Freshness: {card.get('data_freshness') or 'unknown'}")
    lines.append(
        "Evidence: "
        f"{card.get('source_count', 0)} sources, "
        f"{card.get('knowledge_count', 0)} facts, "
        f"audit {card.get('audit_status') or 'unknown'}"
    )
    return "\n".join(lines)


def _group_knowledge(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        knowledge_type = str(item.get("knowledge_type") or "").strip()
        grouped.setdefault(knowledge_type, []).append(item)
    return grouped


def _contents(items: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("content") or "").strip() for item in items if str(item.get("content") or "").strip()]


def _pick_items(values: list[str], *, limit: int = DECISION_CARD_LIMIT) -> list[str]:
    picked: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _truncate_sentence(value)
        key = text.casefold()
        if not text or key in seen:
            continue
        picked.append(text)
        seen.add(key)
        if len(picked) >= limit:
            break
    return picked


def _first_text(values: list[Any]) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _truncate_sentence(value: str, *, max_length: int = 180) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "..."


def _latest_text_value(values: Any) -> str | None:
    cleaned = sorted(str(value) for value in values if value)
    return cleaned[-1] if cleaned else None


def _data_freshness(*, latest_source_date: str | None, stale_after: str | None) -> str:
    parts = []
    if latest_source_date:
        parts.append(f"latest source {latest_source_date}")
    if stale_after:
        parts.append(f"stale after {stale_after}")
    return ", ".join(parts) if parts else "no dated source or stale_after metadata"


def _source_status(source_count: int) -> str:
    if source_count <= 0:
        return "0 sources"
    return f"{source_count} sources"


def _audit_status(latest_research_job: dict[str, Any] | None) -> str:
    if not latest_research_job:
        return "unknown"
    audit_status = latest_research_job.get("audit_status")
    if audit_status:
        return str(audit_status)
    artifacts = latest_research_job.get("artifacts")
    if isinstance(artifacts, dict) and artifacts.get("audit_status"):
        return str(artifacts["audit_status"])
    return "unknown"


def _render_bullets(items: list[str]) -> list[str]:
    return [f"- {item}" for item in items[:DECISION_CARD_LIMIT]]
