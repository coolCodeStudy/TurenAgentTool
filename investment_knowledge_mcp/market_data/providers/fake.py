from __future__ import annotations

from datetime import datetime, timezone

from investment_knowledge_mcp.market_data.models import (
    BreadthSnapshot,
    FetchResult,
    HotIndustryCandidate,
    HotStockCandidate,
    IndexQuote,
    SessionState,
    TurnoverSnapshot,
)
from investment_knowledge_mcp.market_data.providers.base import EmptyMarketDataProvider


class FakeMarketDataProvider(EmptyMarketDataProvider):
    name = "fake"

    def probe_capabilities(self, markets: list[str]) -> dict[str, dict[str, str]]:
        return {
            market: {
                "session": "ok",
                "index_quotes": "ok",
                "turnover": "ok",
                "breadth": "ok",
                "hot_stocks": "ok",
                "hot_industries": "ok",
            }
            for market in markets
        }

    def get_index_quotes(self, market: str, session: SessionState) -> FetchResult[list[IndexQuote]]:
        data = [
            IndexQuote(symbol=f"{market}.INDEX1", name=f"{market} Main Index", price=1000, change_pct=1.2, turnover=100),
            IndexQuote(symbol=f"{market}.INDEX2", name=f"{market} Growth Index", price=800, change_pct=0.8, turnover=80),
        ]
        return self._ok(data)

    def get_market_turnover(self, market: str, session: SessionState) -> FetchResult[TurnoverSnapshot]:
        actual = 1200.0
        projected = None
        confidence = "high"
        if session.run_mode == "intraday" and session.elapsed_session_ratio:
            projected = actual / max(session.elapsed_session_ratio, 0.1)
            confidence = "medium"
        return self._ok(
            TurnoverSnapshot(
                actual_turnover=actual,
                projected_turnover=projected,
                currency="USD" if market == "US" else ("HKD" if market == "HK" else "CNY"),
                average_5d=1000,
                average_20d=950,
                average_60d=900,
                projection_confidence=confidence,
            )
        )

    def get_breadth(self, market: str, session: SessionState) -> FetchResult[BreadthSnapshot]:
        return self._ok(BreadthSnapshot(advancers=720, decliners=320, unchanged=55, limit_up=18, limit_down=2))

    def get_hot_stocks(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotStockCandidate]]:
        themes = {
            "CN": "AI infrastructure",
            "US": "Semiconductors",
            "HK": "China internet",
        }
        data = [
            HotStockCandidate(
                symbol=f"{market}.HOT{idx}",
                name=f"{market} Hot Stock {idx}",
                market=market,
                move_pct=8.0 - idx * 0.5,
                volume_heat=2.5 - idx * 0.1,
                turnover=1000000 * idx,
                catalyst="sector momentum",
                theme=themes.get(market, "Market heat"),
                relative_move=7.5 - idx * 0.4,
                source=self.name,
            )
            for idx in range(1, limit + 1)
        ]
        return self._ok(data)

    def get_hot_industries(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotIndustryCandidate]]:
        base = {
            "CN": "AI Servers",
            "US": "Semiconductor Equipment",
            "HK": "Internet Platforms",
        }.get(market, "Active Theme")
        data = [
            HotIndustryCandidate(
                industry=f"{base} {idx}",
                market=market,
                performance_pct=5.0 - idx * 0.35,
                volume_heat=2.2 - idx * 0.1,
                representative_stocks=[f"{market}.HOT{idx}", f"{market}.LEAD{idx}"],
                catalyst="capital rotation",
                theme_label=base,
                breadth=0.7 - idx * 0.03,
                source=self.name,
            )
            for idx in range(1, limit + 1)
        ]
        return self._ok(data)

    def _ok(self, data):
        return FetchResult(status="ok", provider=self.name, fetched_at=datetime.now(timezone.utc), data=data)
