from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path

from investment_knowledge_mcp.research.models import ResearchBundle, SourceDocument


class ResearchProvider(ABC):
    @abstractmethod
    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        """Collect research source documents for a stock."""


class ManualResearchProvider(ResearchProvider):
    """Load user-curated source documents from a local JSON file."""

    def __init__(self, source_file: Path) -> None:
        self.source_file = source_file

    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        payload = json.loads(self.source_file.read_text(encoding="utf-8"))
        stock = payload.get("stock") or {}
        bundle_symbol = symbol or stock.get("symbol")
        bundle_market = market or stock.get("market")
        if not bundle_symbol or not bundle_market:
            raise ValueError("symbol and market are required")

        sources = [
            SourceDocument(
                key=item["key"],
                source_type=item.get("source_type", "web"),
                title=item["title"],
                url=item.get("url"),
                publisher=item.get("publisher"),
                published_at=item.get("published_at"),
                notes=item.get("notes"),
            )
            for item in payload.get("sources", [])
        ]

        return ResearchBundle(
            symbol=bundle_symbol,
            market=bundle_market,
            company_name=company_name or stock.get("name"),
            sources=sources,
            notes=payload.get("notes", []),
        )


class EmptyResearchProvider(ResearchProvider):
    """Create a skeleton bundle when no external provider has been configured."""

    def collect(self, symbol: str, market: str, company_name: str | None = None) -> ResearchBundle:
        return ResearchBundle(symbol=symbol, market=market, company_name=company_name)

