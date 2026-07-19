"""Canonical target resolution and provider-neutral valuation snapshots."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import math
import re
from typing import Any

from investment_knowledge_mcp.data_sources.contracts import (
    DataRequest,
    DataResult,
    DataStatus,
    SourceCapability,
)
from investment_knowledge_mcp.data_sources.pool import DataSourcePool, ResultCache
from investment_knowledge_mcp.data_sources.valuation import (
    MARKET_SNAPSHOT_METRICS,
    VALUATION_FACT_METRICS,
    ValuationFactsSource,
    valuation_financial_plan,
    valuation_market_plan,
    valuation_source_descriptor,
)
from investment_knowledge_mcp.market_data_provider import _fetch_yahoo_symbol
from investment_knowledge_mcp.research.official_sources import (
    OfficialResearchProvider,
    _http_client,
    _lookup_sec_cik,
)


_SAFE_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
_MARKET_CURRENCY = {"US": "USD", "HK": "HKD", "KR": "KRW"}
_KNOWN_TARGETS: dict[tuple[str, str], dict[str, str]] = {
    ("US", "INTC"): {"company_name": "Intel Corporation"},
    ("KR", "000660"): {"company_name": "SK hynix Inc."},
    ("HK", "01888"): {"company_name": "Kingboard Laminates Holdings Limited"},
}
_HK_ALIASES = {
    "1888": "01888",
    "01888": "01888",
    "建滔积层板": "01888",
    "建滔積層板": "01888",
    "建滔积层板控股有限公司": "01888",
    "建滔積層板控股有限公司": "01888",
    "kingboard laminates": "01888",
    "kingboard laminates holdings": "01888",
    "kingboard laminates holdings limited": "01888",
}
_SEC_FACT_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt": ("LongTermDebtAndFinanceLeaseObligations", "LongTermDebt", "DebtCurrent"),
    "shares_outstanding": ("EntityCommonStockSharesOutstanding",),
}


def normalize_valuation_target(
    symbol: str,
    market: str,
    company_name: str | None = None,
) -> dict[str, object]:
    """Resolve supported aliases into one canonical market-qualified target."""
    del company_name
    raw_symbol = _required_text(symbol, "symbol")
    normalized_market = str(market).strip().upper()
    raw_symbol, qualified_market = _split_qualified_symbol(raw_symbol)
    if qualified_market:
        if normalized_market and normalized_market != qualified_market:
            raise ValueError("symbol qualifier conflicts with market")
        normalized_market = qualified_market
    if normalized_market not in _MARKET_CURRENCY:
        raise ValueError("valuation market must be US, HK, or KR")

    if normalized_market == "HK":
        normalized_symbol = _HK_ALIASES.get(_alias_key(raw_symbol), raw_symbol.strip().upper())
        if normalized_symbol.isdigit():
            normalized_symbol = normalized_symbol.zfill(5)
    elif normalized_market == "KR":
        normalized_symbol = raw_symbol.strip().upper()
        if normalized_symbol.isdigit():
            normalized_symbol = normalized_symbol.zfill(6)
    else:
        normalized_symbol = raw_symbol.strip().upper()
    if not _SAFE_SYMBOL.fullmatch(normalized_symbol):
        raise ValueError("symbol must be a bounded stock identifier or supported alias")

    provider_ticker = normalized_symbol
    if normalized_market == "HK":
        provider_ticker = f"{int(normalized_symbol)}.HK" if normalized_symbol.isdigit() else f"{normalized_symbol}.HK"
    elif normalized_market == "KR":
        provider_ticker = f"{normalized_symbol}.KS"
    target: dict[str, object] = {
        "input_target": f"{normalized_market}.{normalized_symbol}",
        "normalized_symbol": normalized_symbol,
        "normalized_market": normalized_market,
        "normalized_target": f"{normalized_market}.{normalized_symbol}",
        "provider_market_ticker": provider_ticker,
        "currency": _MARKET_CURRENCY[normalized_market],
        "mapping_source": {"US": "sec", "HK": "hkex", "KR": "dart"}[normalized_market],
    }
    if known := _KNOWN_TARGETS.get((normalized_market, normalized_symbol)):
        target.update(known)
    return target


def fetch_valuation_snapshot(
    symbol: str,
    market: str,
    company_name: str | None = None,
) -> dict[str, object]:
    """Fetch a bounded snapshot through the shared pool and canonical adapters."""
    target = normalize_valuation_target(symbol, market, company_name)
    pool = default_valuation_pool()
    return _fetch_valuation_snapshot(target, pool)


def default_valuation_pool(*, cache: ResultCache | None = None) -> DataSourcePool:
    """Build the lazy valuation source registry without performing any fetch."""
    pool = DataSourcePool(cache=cache)
    official_provider = OfficialResearchProvider()
    sources = (
        ValuationFactsSource(
            "sec_companyfacts",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "sec_companyfacts",
            "sec",
            _load_sec_companyfacts,
        ),
        ValuationFactsSource(
            "sec_filing",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "sec_filing",
            "sec",
            _official_attempt_loader(official_provider, "sec_filing"),
        ),
        ValuationFactsSource(
            "hkexnews",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "hkexnews",
            "hkex",
            _official_attempt_loader(official_provider, "hkexnews"),
        ),
        ValuationFactsSource(
            "hkex_filing",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "hkex_filing",
            "hkex",
            _official_attempt_loader(official_provider, "hkex_filing"),
        ),
        ValuationFactsSource(
            "dart_filing",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "dart_filing",
            "dart",
            _empty_official_attempt,
        ),
        ValuationFactsSource(
            "fss_filing",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "fss_filing",
            "fss",
            _empty_official_attempt,
        ),
        ValuationFactsSource(
            "company_ir",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "company_ir",
            "company_ir",
            _official_attempt_loader(official_provider, "company_ir"),
        ),
        ValuationFactsSource(
            "company_report",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "company_report",
            "official_research",
            _official_attempt_loader(official_provider, "company_report"),
        ),
        ValuationFactsSource(
            "vendor_financial",
            SourceCapability.OFFICIAL_FINANCIAL_FACTS,
            "vendor_financial",
            "vendor",
            _empty_official_attempt,
        ),
        ValuationFactsSource(
            "yahoo",
            SourceCapability.MARKET_SNAPSHOT,
            "market_snapshot",
            "yahoo",
            _load_shared_yahoo_snapshot,
            default_ttl_seconds=60,
        ),
    )
    for source in sources:
        pool.register(source)
    return pool


def _fetch_valuation_snapshot(target: dict[str, object], pool: DataSourcePool) -> dict[str, object]:
    market = str(target["normalized_market"])
    symbol = str(target["normalized_symbol"])
    provider_ticker = str(target["provider_market_ticker"])
    available_sources = tuple(pool._providers)
    financial_request = DataRequest(
        SourceCapability.OFFICIAL_FINANCIAL_FACTS,
        market,
        (symbol,),
        freshness="latest_filing",
        required_fields=VALUATION_FACT_METRICS,
    )
    market_request = DataRequest(
        SourceCapability.MARKET_SNAPSHOT,
        market,
        (provider_ticker,),
        freshness="latest_market_session",
        required_fields=MARKET_SNAPSHOT_METRICS,
    )
    financial = pool.fetch(
        financial_request,
        valuation_financial_plan(market, available_sources=available_sources),
    )
    market_snapshot = pool.fetch(
        market_request,
        valuation_market_plan(available_sources=available_sources),
    )
    facts = [dict(record) for result in (financial, market_snapshot) for record in result.records]
    sources = _sources_from_facts(facts)
    return {
        "target_resolution": dict(target),
        "facts": facts,
        "sources": sources,
        "financial_fact_status": _result_status(financial),
        "market_snapshot_status": _result_status(market_snapshot),
        "source_attempts": [
            *_safe_attempts(financial),
            *_safe_attempts(market_snapshot),
        ],
    }


def _safe_attempts(result: DataResult) -> list[dict[str, str]]:
    attempts = []
    for source_id in result.attempted_sources:
        descriptor = valuation_source_descriptor(source_id)
        status = _result_status(result) if source_id == result.selected_source else "unavailable"
        attempts.append({
            "family": descriptor["family"],
            "status": status,
            "source_type": descriptor["source_type"],
            "provider": descriptor["provider"],
        })
    return attempts


def _sources_from_facts(facts: list[dict[str, object]]) -> list[dict[str, str]]:
    sources: dict[tuple[str, str], dict[str, str]] = {}
    for fact in facts:
        source_type = fact.get("source_type")
        provider = fact.get("provider")
        if isinstance(source_type, str) and isinstance(provider, str):
            sources[(source_type, provider)] = {
                "source_type": source_type,
                "provider": provider,
            }
    return [sources[key] for key in sorted(sources)]


def _result_status(result: DataResult) -> str:
    return {
        DataStatus.OK: "available",
        DataStatus.PARTIAL: "partial",
        DataStatus.UNAVAILABLE: "unavailable",
    }[result.status]


def _split_qualified_symbol(symbol: str) -> tuple[str, str | None]:
    value = symbol.strip()
    prefix = re.fullmatch(r"(US|HK|KR)\.(.+)", value, flags=re.IGNORECASE)
    if prefix:
        return prefix.group(2).strip(), prefix.group(1).upper()
    suffix = re.fullmatch(r"(.+?)\s+(US|HK|KR)", value, flags=re.IGNORECASE)
    if suffix:
        return suffix.group(1).strip(), suffix.group(2).upper()
    return value, None


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise ValueError(f"{field} must be non-empty")
    return normalized


def _alias_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _load_sec_companyfacts(symbol: str, market: str) -> dict[str, object]:
    if market != "US":
        return _empty_payload()
    with _http_client(8.0) as client:
        cik = _lookup_sec_cik(client, symbol)
        if cik is None:
            return _empty_payload()
        response = client.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        response.raise_for_status()
        payload = response.json()
    return {
        "facts": _extract_sec_companyfacts(payload),
        "fetched_at": datetime.now(timezone.utc),
    }


def _extract_sec_companyfacts(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return []
    us_gaap = facts.get("us-gaap") if isinstance(facts.get("us-gaap"), dict) else {}
    dei = facts.get("dei") if isinstance(facts.get("dei"), dict) else {}
    result: list[dict[str, object]] = []
    for metric, tags in _SEC_FACT_TAGS.items():
        namespace = dei if metric == "shares_outstanding" else us_gaap
        for tag in tags:
            tag_payload = namespace.get(tag) if isinstance(namespace, dict) else None
            entry = _latest_sec_entry(tag_payload, shares=metric == "shares_outstanding")
            if entry is None:
                continue
            value = entry.get("val")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            number = float(value)
            if not math.isfinite(number):
                continue
            fact: dict[str, object] = {"metric": metric, "value": number}
            if metric != "shares_outstanding":
                fact["currency"] = "USD"
            if isinstance(entry.get("end"), str):
                fact["period_end"] = entry["end"]
            if isinstance(entry.get("filed"), str):
                fact["timestamp"] = f"{entry['filed']}T00:00:00+00:00"
            result.append(fact)
            break
    return result


def _latest_sec_entry(payload: object, *, shares: bool) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("units"), dict):
        return None
    units = payload["units"]
    candidates = units.get("shares" if shares else "USD")
    if not isinstance(candidates, list):
        return None
    valid = [item for item in candidates if isinstance(item, dict) and item.get("val") is not None]
    annual = [item for item in valid if str(item.get("form") or "").upper() in {"10-K", "20-F", "40-F"}]
    return max(annual or valid, key=lambda item: (str(item.get("filed") or ""), str(item.get("end") or "")), default=None)


def _official_attempt_loader(provider: OfficialResearchProvider, source_id: str):
    def load(symbol: str, market: str) -> dict[str, object]:
        bundle = provider.collect(symbol=symbol, market=market)
        matching = [
            source
            for source in bundle.sources
            if _official_document_matches(source_id, source.source_type, source.publisher)
        ]
        return {"facts": [], "fetched_at": datetime.now(timezone.utc), "source_count": len(matching)}
    return load


def _official_document_matches(source_id: str, source_type: str, publisher: str | None) -> bool:
    publisher_key = str(publisher or "").casefold()
    if source_id in {"hkexnews", "hkex_filing"}:
        return "hkex" in publisher_key
    if source_id == "company_ir":
        return "hkex" not in publisher_key
    if source_id == "company_report":
        return source_type in {"annual_report", "annual_results", "interim_results", "quarterly_results"}
    return source_id == "sec_filing" and "sec" in publisher_key


def _empty_official_attempt(symbol: str, market: str) -> dict[str, object]:
    del symbol, market
    return _empty_payload()


def _empty_payload() -> dict[str, object]:
    return {"facts": [], "fetched_at": datetime.now(timezone.utc)}


def _load_shared_yahoo_snapshot(symbol: str, market: str) -> dict[str, object]:
    end = date.today()
    bars = _fetch_yahoo_symbol(symbol, end - timedelta(days=10), end, 5.0)
    if not bars:
        return _empty_payload()
    latest = max(bars, key=lambda item: str(item.get("date") or ""))
    close = latest.get("close")
    if isinstance(close, bool) or not isinstance(close, (int, float)):
        return _empty_payload()
    period = str(latest.get("date") or "")
    return {
        "facts": [{
            "metric": "price",
            "value": float(close),
            "currency": _MARKET_CURRENCY[market],
            "timestamp": f"{period}T00:00:00+00:00",
        }],
        "fetched_at": datetime.now(timezone.utc),
    }
