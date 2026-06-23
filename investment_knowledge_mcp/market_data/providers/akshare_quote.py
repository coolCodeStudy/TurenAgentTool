from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from investment_knowledge_mcp.market_data.models import FetchResult, HotIndustryCandidate, HotStockCandidate, SessionState
from investment_knowledge_mcp.market_data.providers.base import EmptyMarketDataProvider


class AkShareQuoteProvider(EmptyMarketDataProvider):
    name = "akshare"

    def probe_capabilities(self, markets: list[str]) -> dict[str, dict[str, str]]:
        try:
            import akshare  # noqa: F401
        except ImportError:
            return {market: {"status": "dependency_missing"} for market in markets}
        return {market: {"status": "configured", "note": "endpoint coverage is checked per fetch"} for market in markets}

    def get_hot_stocks(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotStockCandidate]]:
        try:
            import akshare as ak
        except ImportError:
            return self._dependency_missing("hot_stocks")
        try:
            fn = _first_callable(ak, ["stock_hot_rank_em", "stock_hk_hot_rank_em"])
            if fn is None:
                return self._dependency_missing("hot_stocks", "No supported AkShare hot-rank endpoint found.")
            rows = _dataframe_rows(fn())
            candidates = []
            for row in rows[:limit]:
                symbol = str(row.get("代码") or row.get("code") or row.get("股票代码") or "")
                name = str(row.get("名称") or row.get("股票名称") or row.get("name") or symbol)
                candidates.append(
                    HotStockCandidate(
                        symbol=symbol,
                        name=name,
                        market=market,
                        move_pct=_float(row.get("涨跌幅") or row.get("涨跌幅%")),
                        volume_heat=_float(row.get("热度") or row.get("排名")),
                        catalyst="AkShare hot rank",
                        theme=None,
                        source=self.name,
                    )
                )
            return FetchResult(status="partial" if candidates else "missing", provider=self.name, fetched_at=datetime.now(timezone.utc), data=candidates)
        except Exception as exc:
            return FetchResult(status="failed", provider=self.name, fetched_at=datetime.now(timezone.utc), warnings=[f"AkShare hot stock fetch failed: {exc}"])

    def get_hot_industries(self, market: str, session: SessionState, limit: int) -> FetchResult[list[HotIndustryCandidate]]:
        try:
            import akshare as ak
        except ImportError:
            return self._dependency_missing("hot_industries")
        try:
            fn = _first_callable(ak, ["stock_board_industry_name_em", "stock_board_concept_name_em"])
            if fn is None:
                return self._dependency_missing("hot_industries", "No supported AkShare board endpoint found.")
            rows = _dataframe_rows(fn())
            candidates = []
            for row in rows[:limit]:
                industry = str(row.get("板块名称") or row.get("名称") or row.get("name") or "")
                if not industry:
                    continue
                candidates.append(
                    HotIndustryCandidate(
                        industry=industry,
                        market=market,
                        performance_pct=_float(row.get("涨跌幅") or row.get("涨跌幅%")),
                        volume_heat=_float(row.get("换手率") or row.get("总市值")),
                        representative_stocks=[str(row.get("领涨股票") or "")],
                        catalyst="AkShare board ranking",
                        theme_label=industry,
                        source=self.name,
                    )
                )
            return FetchResult(status="partial" if candidates else "missing", provider=self.name, fetched_at=datetime.now(timezone.utc), data=candidates)
        except Exception as exc:
            return FetchResult(status="failed", provider=self.name, fetched_at=datetime.now(timezone.utc), warnings=[f"AkShare industry fetch failed: {exc}"])

    def _dependency_missing(self, domain: str, reason: str = "AkShare is not installed.") -> FetchResult[Any]:
        return FetchResult(status="not_configured", provider=self.name, fetched_at=datetime.now(timezone.utc), warnings=[reason], raw_metadata={"domain": domain})


def _first_callable(module: Any, names: list[str]):
    for name in names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


def _dataframe_rows(value) -> list[dict]:
    if hasattr(value, "to_dict"):
        return list(value.to_dict("records"))
    return []


def _float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
