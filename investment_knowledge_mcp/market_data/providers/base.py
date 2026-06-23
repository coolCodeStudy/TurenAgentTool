from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from investment_knowledge_mcp.market_data.models import (
    BreadthSnapshot,
    CatalystSnippet,
    FetchResult,
    HotIndustryCandidate,
    HotStockCandidate,
    IndexQuote,
    SessionState,
    TurnoverSnapshot,
)
from investment_knowledge_mcp.market_data.session_calendar import resolve_review_sessions


class MarketDataProvider(Protocol):
    name: str

    def probe_capabilities(self, markets: list[str]) -> dict[str, dict[str, str]]:
        ...

    def get_session_state(self, market: str, review_dt: datetime) -> SessionState:
        ...

    def get_index_quotes(self, market: str, session: SessionState) -> FetchResult[list[IndexQuote]]:
        ...

    def get_market_turnover(self, market: str, session: SessionState) -> FetchResult[TurnoverSnapshot]:
        ...

    def get_breadth(self, market: str, session: SessionState) -> FetchResult[BreadthSnapshot]:
        ...

    def get_hot_stocks(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotStockCandidate]]:
        ...

    def get_hot_industries(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotIndustryCandidate]]:
        ...

    def get_catalysts(
        self,
        market: str,
        symbols: list[str],
        themes: list[str],
    ) -> FetchResult[list[CatalystSnippet]]:
        ...


class EmptyMarketDataProvider:
    name = "empty"

    def probe_capabilities(self, markets: list[str]) -> dict[str, dict[str, str]]:
        return {market: {"status": "not_configured"} for market in markets}

    def get_session_state(self, market: str, review_dt: datetime) -> SessionState:
        return resolve_review_sessions(review_dt, None, [market])[market]

    def get_index_quotes(self, market: str, session: SessionState) -> FetchResult[list[IndexQuote]]:
        return self._missing("index_quotes")

    def get_market_turnover(self, market: str, session: SessionState) -> FetchResult[TurnoverSnapshot]:
        return self._missing("market_turnover")

    def get_breadth(self, market: str, session: SessionState) -> FetchResult[BreadthSnapshot]:
        return self._missing("breadth")

    def get_hot_stocks(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotStockCandidate]]:
        return self._missing("hot_stocks")

    def get_hot_industries(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotIndustryCandidate]]:
        return self._missing("hot_industries")

    def get_catalysts(
        self,
        market: str,
        symbols: list[str],
        themes: list[str],
    ) -> FetchResult[list[CatalystSnippet]]:
        return self._missing("catalysts")

    def _missing(self, domain: str) -> FetchResult:
        return FetchResult(
            status="not_configured",
            provider=self.name,
            fetched_at=datetime.now(timezone.utc),
            data=None,
            warnings=[f"{domain} provider is not configured."],
        )
