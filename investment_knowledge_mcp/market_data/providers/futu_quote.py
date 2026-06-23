from __future__ import annotations

from datetime import datetime, timezone

from investment_knowledge_mcp.config import get_config
from investment_knowledge_mcp.market_data.models import FetchResult, IndexQuote, SessionState
from investment_knowledge_mcp.market_data.providers.base import EmptyMarketDataProvider


INDEX_SYMBOLS = {
    "CN": [("SH.000300", "CSI 300"), ("SH.000688", "STAR 50"), ("SZ.399006", "ChiNext")],
    "US": [("US.SPY", "S&P 500 ETF"), ("US.QQQ", "Nasdaq 100 ETF"), ("US.IWM", "Russell 2000 ETF")],
    "HK": [("HK.800000", "Hang Seng Index"), ("HK.800700", "Hang Seng Tech"), ("HK.800100", "HSCEI")],
}


class FutuQuoteProvider(EmptyMarketDataProvider):
    name = "futu"

    def probe_capabilities(self, markets: list[str]) -> dict[str, dict[str, str]]:
        try:
            import futu  # noqa: F401
        except ImportError:
            return {market: {"status": "dependency_missing"} for market in markets}
        return {market: {"status": "configured", "note": "live quote permission is checked per fetch"} for market in markets}

    def get_index_quotes(self, market: str, session: SessionState) -> FetchResult[list[IndexQuote]]:
        symbols = INDEX_SYMBOLS.get(market.upper())
        if not symbols:
            return self._missing("index_quotes")
        try:
            import futu as ft
        except ImportError:
            return FetchResult(
                status="not_configured",
                provider=self.name,
                fetched_at=datetime.now(timezone.utc),
                warnings=["futu-api is not installed."],
            )

        config = get_config()
        context = ft.OpenQuoteContext(host=config.futu_opend_host, port=config.futu_opend_port)
        try:
            codes = [code for code, _ in symbols]
            ret, data = context.get_market_snapshot(codes)
            if ret != ft.RET_OK:
                return FetchResult(
                    status="failed",
                    provider=self.name,
                    fetched_at=datetime.now(timezone.utc),
                    warnings=[f"Futu market snapshot failed: {data}"],
                    raw_metadata={"codes": codes},
                )
            rows = _dataframe_rows(data)
            quotes = []
            name_by_code = dict(symbols)
            for row in rows:
                code = str(row.get("code") or row.get("stock_code") or "")
                if not code:
                    continue
                quotes.append(
                    IndexQuote(
                        symbol=code,
                        name=str(row.get("stock_name") or row.get("name") or name_by_code.get(code) or code),
                        price=_float(row.get("last_price") or row.get("price")),
                        change_pct=_float(row.get("change_rate") or row.get("change_pct")),
                        turnover=_float(row.get("turnover")),
                    )
                )
            return FetchResult(
                status="ok" if quotes else "missing",
                provider=self.name,
                fetched_at=datetime.now(timezone.utc),
                data=quotes,
                raw_metadata={"codes": codes, "row_count": len(rows)},
            )
        except Exception as exc:
            return FetchResult(
                status="failed",
                provider=self.name,
                fetched_at=datetime.now(timezone.utc),
                warnings=[f"Futu quote fetch failed: {exc}"],
            )
        finally:
            context.close()


def _dataframe_rows(value) -> list[dict]:
    if hasattr(value, "to_dict"):
        return list(value.to_dict("records"))
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _float(value) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
