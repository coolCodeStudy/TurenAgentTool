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
from investment_knowledge_mcp.data_sources.pool import ResultCache
from investment_knowledge_mcp.data_sources.valuation import (
    MARKET_SNAPSHOT_METRICS,
    VALUATION_FACT_METRICS,
    ValuationDataSourcePool,
    ValuationFactsSource,
    valuation_financial_plan,
    valuation_financial_source_order,
    valuation_market_plan,
    valuation_market_source_order,
    valuation_source_descriptor,
)
from investment_knowledge_mcp.market_data_provider import _fetch_yahoo_symbol
from investment_knowledge_mcp.research.official_sources import (
    OfficialResearchProvider,
    _http_client,
    _lookup_sec_cik,
)
from investment_knowledge_mcp.research.models import SourceDocument


_SAFE_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")
_SAFE_COMPANY_NAME = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,120}$")
_MARKET_CURRENCY = {"US": "USD", "HK": "HKD", "KR": "KRW"}
_SK_HYNIX_IR_URL = "https://www.skhynix.com/ir/"
_DART_SEARCH_URL = "https://dart.fss.or.kr/dsab002/main.do"
_FSS_SEARCH_URL = "https://englishdart.fss.or.kr/dsbc001/main.do"
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
    known = _KNOWN_TARGETS.get((normalized_market, normalized_symbol))
    if known:
        target.update(known)
    elif normalized_name := _bounded_company_name(company_name):
        target["company_name"] = normalized_name
    return target


def fetch_valuation_snapshot(
    symbol: str,
    market: str,
    company_name: str | None = None,
) -> dict[str, object]:
    """Fetch a bounded snapshot through the shared pool and canonical adapters."""
    target = normalize_valuation_target(symbol, market, company_name)
    pool = default_valuation_pool(target)
    return _fetch_valuation_snapshot(target, pool)


def default_valuation_pool(
    target: dict[str, object],
    *,
    cache: ResultCache | None = None,
    official_provider: OfficialResearchProvider | None = None,
    http_client_factory=_http_client,
    market_loader=None,
) -> ValuationDataSourcePool:
    """Build the lazy valuation source registry without performing any fetch."""
    pool = ValuationDataSourcePool(cache=cache)
    official_provider = official_provider or OfficialResearchProvider()
    market = str(target["normalized_market"])
    symbol = str(target["normalized_symbol"])
    company_name = target.get("company_name") if isinstance(target.get("company_name"), str) else None
    sources: list[ValuationFactsSource] = []
    if market == "US":
        sources.extend((
            _financial_source(
                "sec_companyfacts",
                _sec_companyfacts_loader(http_client_factory),
                markets=("US",),
            ),
            _financial_source(
                "sec_filing",
                _official_attempt_loader(official_provider, "sec_filing", company_name=company_name),
                markets=("US",),
            ),
        ))
    elif market == "HK":
        for source_id in ("hkexnews", "hkex_filing", "company_report"):
            sources.append(_financial_source(
                source_id,
                _official_attempt_loader(official_provider, source_id, company_name=company_name),
                markets=("HK",),
            ))
    elif market == "KR":
        sources.extend((
            _financial_source(
                "dart_filing",
                _kr_regulator_probe_loader("dart_filing", target, http_client_factory),
                markets=("KR",),
            ),
            _financial_source(
                "fss_filing",
                _kr_regulator_probe_loader("fss_filing", target, http_client_factory),
                markets=("KR",),
            ),
        ))
        if symbol == "000660":
            sources.append(_financial_source(
                "company_ir",
                _company_ir_probe_loader(_SK_HYNIX_IR_URL, http_client_factory),
                markets=("KR",),
            ))
    sources.append(ValuationFactsSource(
        "yahoo",
        SourceCapability.MARKET_SNAPSHOT,
        "market_snapshot",
        "yahoo",
        market_loader or _load_shared_yahoo_snapshot,
        markets=(market,),
        default_ttl_seconds=60,
    ))
    for source in sources:
        pool.register(source)
    return pool


def _fetch_valuation_snapshot(
    target: dict[str, object],
    pool: ValuationDataSourcePool,
) -> dict[str, object]:
    market = str(target["normalized_market"])
    symbol = str(target["normalized_symbol"])
    provider_ticker = str(target["provider_market_ticker"])
    available_sources = pool.registered_source_ids
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
            *_safe_attempts(financial, valuation_financial_source_order(market)),
            *_safe_attempts(market_snapshot, valuation_market_source_order()),
        ],
    }


def _safe_attempts(result: DataResult, source_order: tuple[str, ...]) -> list[dict[str, str]]:
    attempts: list[dict[str, str]] = []
    failures = {failure.source_id: failure.code for failure in result.failures}
    for source_id in source_order:
        descriptor = valuation_source_descriptor(source_id)
        if source_id == result.selected_source:
            status = _result_status(result)
        elif source_id not in result.attempted_sources:
            status = "not_attempted"
        elif failures.get(source_id) in {"complete_missing", "empty_result"}:
            status = "complete_missing"
        else:
            status = "failed"
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


def _bounded_company_name(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value).strip()
    if not _SAFE_COMPANY_NAME.fullmatch(normalized):
        return None
    if re.search(r"(?i)\b(token|api[_ -]?key|password|secret|authorization)\b|https?://", normalized):
        return None
    return normalized


def _alias_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _financial_source(
    source_id: str,
    loader,
    *,
    markets: tuple[str, ...],
) -> ValuationFactsSource:
    descriptor = valuation_source_descriptor(source_id)
    return ValuationFactsSource(
        source_id,
        SourceCapability.OFFICIAL_FINANCIAL_FACTS,
        descriptor["source_type"],
        descriptor["provider"],
        loader,
        markets=markets,
    )


def _sec_companyfacts_loader(http_client_factory):
    def load(symbol: str, market: str) -> dict[str, object]:
        return _load_sec_companyfacts(symbol, market, http_client_factory=http_client_factory)
    return load


def _load_sec_companyfacts(
    symbol: str,
    market: str,
    *,
    http_client_factory=_http_client,
) -> dict[str, object]:
    if market != "US":
        return _empty_payload(attempt_status="complete_missing")
    with http_client_factory(8.0) as client:
        cik = _lookup_sec_cik(client, symbol)
        if cik is None:
            return _empty_payload(attempt_status="complete_missing")
        response = client.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
        response.raise_for_status()
        payload = response.json()
    facts = _extract_sec_companyfacts(payload)
    return {
        "facts": facts,
        "attempt_status": "complete_missing" if not facts else "available",
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


def _official_attempt_loader(
    provider: OfficialResearchProvider,
    source_id: str,
    *,
    company_name: str | None = None,
):
    def load(symbol: str, market: str) -> dict[str, object]:
        bundle = provider.collect(symbol=symbol, market=market, company_name=company_name)
        matching = [
            source
            for source in bundle.sources
            if _official_document_matches(source_id, source)
        ]
        return {
            "facts": [],
            "attempt_status": "complete_missing",
            "fetched_at": datetime.now(timezone.utc),
            "source_count": len(matching),
        }
    return load


def _official_document_matches(source_id: str, source: SourceDocument) -> bool:
    publisher_key = str(source.publisher or "").casefold()
    source_type = source.source_type.strip().casefold()
    key = source.key.strip().casefold()
    is_hkex = "hkex" in publisher_key or key.startswith("hkex_")
    is_sec = publisher_key == "sec" or key.startswith("sec_")
    hkex_news_types = {
        "announcement",
        "annual_results",
        "interim_results",
        "quarterly_results",
        "profit_warning",
        "transaction_announcement",
    }
    hkex_filing_types = {"annual_report", "prospectus"}
    company_report_types = {"annual_report", "annual_results", "interim_results", "quarterly_results"}
    if source_id == "hkexnews":
        return is_hkex and source_type in hkex_news_types
    if source_id == "hkex_filing":
        return is_hkex and source_type in hkex_filing_types
    if source_id == "company_ir":
        return not is_hkex and not is_sec and source_type == "company_ir" and "ir" in key
    if source_id == "company_report":
        return not is_hkex and not is_sec and source_type in company_report_types and (
            key.startswith("issuer_ir_") or key.startswith("company_")
        )
    return source_id == "sec_filing" and is_sec and source_type in {
        "annual_report", "quarterly_results", "announcement",
    }


def _kr_regulator_probe_loader(source_id: str, target: dict[str, object], http_client_factory):
    endpoint = {"dart_filing": _DART_SEARCH_URL, "fss_filing": _FSS_SEARCH_URL}[source_id]
    query = str(target.get("company_name") or target["normalized_symbol"])

    def load(symbol: str, market: str) -> dict[str, object]:
        del symbol, market
        with http_client_factory(8.0) as client:
            response = client.get(endpoint, params={"textCrpNm": query})
            response.raise_for_status()
            _ = response.text
        return _empty_payload(attempt_status="complete_missing")
    return load


def _company_ir_probe_loader(url: str, http_client_factory):
    def load(symbol: str, market: str) -> dict[str, object]:
        del symbol, market
        with http_client_factory(8.0) as client:
            response = client.get(url)
            response.raise_for_status()
            _ = response.text
        return _empty_payload(attempt_status="complete_missing")
    return load


def _empty_payload(*, attempt_status: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"facts": [], "fetched_at": datetime.now(timezone.utc)}
    if attempt_status:
        payload["attempt_status"] = attempt_status
    return payload


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
