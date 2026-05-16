from __future__ import annotations

from typing import Any

from investment_knowledge_mcp.research.models import ResearchBundle


def build_stock_research_draft(bundle: ResearchBundle) -> dict[str, Any]:
    """Build a conservative research draft skeleton from collected sources."""
    source_key = bundle.sources[0].key if bundle.sources else None
    source_ref = {"source_key": source_key} if source_key else {}
    display_name = bundle.company_name or ""

    draft: dict[str, Any] = {
        "stock": {
            "symbol": bundle.symbol,
            "market": bundle.market,
            "name": display_name,
            "core_business": "",
            "equity_structure": "",
            "stock_character": "",
            "notable_history": "",
        },
        "sources": [source.to_draft_source() for source in bundle.sources],
        "sectors": [],
        "knowledge_items": [],
        "user_insights": [],
        "draft_status": "needs_model_or_user_completion",
        "research_notes": bundle.notes,
    }

    if bundle.sources:
        draft["knowledge_items"].append(
            {
                "knowledge_type": "research_source",
                "content": f"已收集 {display_name or bundle.symbol} 的候选研究来源，需由大模型或用户提炼为事实知识。",
                "confidence": 0.3,
                **source_ref,
            }
        )

    return draft

