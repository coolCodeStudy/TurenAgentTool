from __future__ import annotations

from copy import deepcopy

from investment_knowledge_mcp.model_providers.base import EnrichmentRequest, ModelProvider


class MockModelProvider(ModelProvider):
    """Deterministic provider used to test the enrichment workflow."""

    def enrich_research_draft(self, request: EnrichmentRequest) -> dict:
        draft = deepcopy(request.draft)
        stock = draft.setdefault("stock", {})
        sources = draft.setdefault("sources", [])
        first_source_key = sources[0]["key"] if sources else None
        source_ref = {"source_key": first_source_key} if first_source_key else {}

        stock["name"] = stock.get("name") or f"{stock.get('symbol', '')}.{stock.get('market', '')}"
        stock["core_business"] = stock.get("core_business") or "MOCK: 待模型根据资料来源补全核心业务。"
        stock["equity_structure"] = stock.get("equity_structure") or "MOCK: 待模型根据资料来源补全股权结构。"
        stock["stock_character"] = stock.get("stock_character") or "MOCK: 待模型根据资料来源补全股性判断。"
        stock["notable_history"] = stock.get("notable_history") or "MOCK: 待模型根据资料来源补全突出历史。"

        if not draft.get("sectors"):
            draft["sectors"] = [
                {
                    "path": ["待分类"],
                    "relation_type": "related",
                    "confidence": 0.1,
                    **source_ref,
                    "description": "MOCK: 需要模型或用户确认真实板块归属。",
                    "recent_status": "MOCK: 需要补全板块近况。",
                }
            ]

        draft["knowledge_items"] = [
            item
            for item in draft.get("knowledge_items", [])
            if item.get("knowledge_type") != "research_source"
        ]
        if not draft["knowledge_items"]:
            draft["knowledge_items"].append(
                {
                    "knowledge_type": "watch_item",
                    "content": "MOCK: 已完成流程联调，真实内容需要模型根据来源补全。",
                    "confidence": 0.1,
                    **source_ref,
                }
            )

        draft["user_insights"] = draft.get("user_insights") or []
        draft.pop("draft_status", None)
        draft.pop("research_notes", None)
        return draft

