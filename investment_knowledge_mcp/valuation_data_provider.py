from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import ssl
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
YAHOO_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

SEC_FACT_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "operating_cash_flow": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"),
    "debt": (
        "LongTermDebtAndFinanceLeaseObligations",
        "LongTermDebt",
        "DebtCurrent",
        "ShortTermBorrowings",
    ),
    "shares_outstanding": ("EntityCommonStockSharesOutstanding",),
}


def fetch_provider_snapshot(symbol: str, market: str, *, timeout: float = 8.0) -> dict[str, Any]:
    normalized_symbol = symbol.strip().upper()
    normalized_market = market.strip().upper()
    snapshot: dict[str, Any] = {
        "facts": [],
        "sources": [],
        "errors": [],
        "market_snapshot_status": "missing",
        "financial_fact_status": "missing",
    }
    if normalized_market != "US":
        snapshot["errors"].append(f"provider snapshot is not implemented for market {normalized_market}")
        return snapshot

    sec_result = _fetch_sec_companyfacts(normalized_symbol, timeout=timeout)
    snapshot["facts"].extend(sec_result["facts"])
    snapshot["sources"].extend(sec_result["sources"])
    snapshot["errors"].extend(sec_result["errors"])
    if sec_result["facts"]:
        snapshot["financial_fact_status"] = "present"

    yahoo_result = _fetch_yahoo_quote(normalized_symbol, timeout=timeout)
    snapshot["facts"].extend(yahoo_result["facts"])
    snapshot["sources"].extend(yahoo_result["sources"])
    snapshot["errors"].extend(yahoo_result["errors"])
    if yahoo_result["facts"]:
        snapshot["market_snapshot_status"] = "present"

    return snapshot


def _fetch_sec_companyfacts(symbol: str, *, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {"facts": [], "sources": [], "errors": []}
    try:
        tickers = _get_json(SEC_TICKERS_URL, timeout=timeout, headers=_sec_headers())
        cik = _lookup_cik(tickers, symbol)
        if cik is None:
            result["errors"].append(f"SEC CIK lookup missing for {symbol}")
            return result
        facts_payload = _get_json(SEC_COMPANYFACTS_URL.format(cik=f"{cik:010d}"), timeout=timeout, headers=_sec_headers())
        extracted = _extract_sec_facts(symbol=symbol, cik=cik, payload=facts_payload)
        result["facts"].extend(extracted)
        if extracted:
            result["sources"].append(
                {
                    "id": f"sec:{symbol}:companyfacts",
                    "source_type": "sec_companyfacts",
                    "title": f"SEC companyfacts {symbol}",
                    "url": SEC_COMPANYFACTS_URL.format(cik=f"{cik:010d}"),
                    "published_at": max((str(fact.get("period_end") or "") for fact in extracted), default=None),
                }
            )
    except Exception as exc:  # pragma: no cover - exact request exceptions vary by runtime.
        result["errors"].append(f"SEC companyfacts unavailable: {exc}")
    return result


def _fetch_yahoo_quote(symbol: str, *, timeout: float) -> dict[str, Any]:
    result: dict[str, Any] = {"facts": [], "sources": [], "errors": []}
    quote_time: Any = None
    try:
        payload = _get_json(YAHOO_QUOTE_URL, timeout=timeout, params={"symbols": symbol}, headers=_yahoo_headers())
        quote = (((payload.get("quoteResponse") or {}).get("result") or [])[:1] or [{}])[0]
        quote_time = quote.get("regularMarketTime")
        facts = _extract_yahoo_quote_facts(symbol, quote)
        if not facts:
            facts = _extract_yahoo_chart_facts(symbol, _get_json(YAHOO_CHART_URL.format(symbol=symbol), timeout=timeout, headers=_yahoo_headers()))
        result["facts"].extend(facts)
    except Exception as exc:  # pragma: no cover - exact request exceptions vary by runtime.
        result["errors"].append(f"Yahoo quote unavailable: {exc}")
        try:
            facts = _extract_yahoo_chart_facts(symbol, _get_json(YAHOO_CHART_URL.format(symbol=symbol), timeout=timeout, headers=_yahoo_headers()))
            quote_time = next((fact.get("timestamp") for fact in facts if fact.get("timestamp")), None)
            result["facts"].extend(facts)
        except Exception as chart_exc:  # pragma: no cover - exact request exceptions vary by runtime.
            result["errors"].append(f"Yahoo chart unavailable: {chart_exc}")
    if result["facts"]:
        result["sources"].append(
            {
                "id": f"yahoo:{symbol}:quote",
                "source_type": "yahoo_quote",
                "title": f"Yahoo Finance quote {symbol}",
                "url": YAHOO_QUOTE_URL,
                "published_at": _timestamp_to_iso(quote_time) or quote_time,
            }
        )
    return result


def _get_json(url: str, *, timeout: float, headers: dict[str, str] | None = None, params: dict[str, str] | None = None) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=timeout, context=_ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def _ssl_context() -> ssl.SSLContext | None:
    cafile = _certifi_cafile() or _system_cafile()
    if cafile is None:
        return None
    return ssl.create_default_context(cafile=cafile)


def _certifi_cafile() -> str | None:
    try:
        import certifi  # type: ignore
    except ModuleNotFoundError:
        return None
    return str(certifi.where())


def _system_cafile() -> str | None:
    for candidate in ("/etc/ssl/cert.pem", "/opt/homebrew/etc/ca-certificates/cert.pem"):
        if os.path.exists(candidate):
            return candidate
    return None


def _sec_headers() -> dict[str, str]:
    contact = os.getenv("SEC_USER_AGENT") or os.getenv("CONTACT_EMAIL") or "TurenAgentTool valuation research contact@example.com"
    return {"User-Agent": contact}


def _yahoo_headers() -> dict[str, str]:
    return {"User-Agent": "Mozilla/5.0 (compatible; InvestmentKnowledgeBot/0.1)", "Accept": "application/json"}


def _lookup_cik(payload: Any, symbol: str) -> int | None:
    records = payload.values() if isinstance(payload, dict) else payload
    for record in records or []:
        if str(record.get("ticker") or "").upper() == symbol:
            return int(record["cik_str"])
    return None


def _extract_sec_facts(*, symbol: str, cik: int, payload: dict) -> list[dict[str, Any]]:
    fact_groups = payload.get("facts") or {}
    us_gaap = fact_groups.get("us-gaap") or {}
    dei = fact_groups.get("dei") or {}
    facts: list[dict[str, Any]] = []
    for metric, tags in SEC_FACT_TAGS.items():
        if metric == "debt":
            value = 0.0
            entries: list[dict[str, Any]] = []
            for tag in tags:
                entry = _latest_usd_entry(us_gaap.get(tag) or {})
                if entry is not None:
                    value += float(entry["val"])
                    entries.append({"tag": tag, **entry})
            if entries:
                latest = max(entries, key=_entry_sort_key)
                facts.append(_provider_fact(symbol, metric, value, f"sec:{symbol}:debt", "sec_companyfacts", latest, cik=cik))
            continue

        namespace = dei if metric == "shares_outstanding" else us_gaap
        for tag in tags:
            entry = _latest_usd_entry(namespace.get(tag) or {})
            if entry is not None:
                facts.append(_provider_fact(symbol, metric, float(entry["val"]), f"sec:{symbol}:{tag}", "sec_companyfacts", entry, cik=cik))
                break
    return facts


def _latest_usd_entry(tag_payload: dict) -> dict[str, Any] | None:
    units = tag_payload.get("units") or {}
    candidates = list(units.get("USD") or units.get("shares") or [])
    candidates = [item for item in candidates if item.get("val") is not None]
    if not candidates:
        return None
    annual = [item for item in candidates if str(item.get("form") or "").upper() in {"10-K", "20-F", "40-F"}]
    return max(annual or candidates, key=_entry_sort_key)


def _entry_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("filed") or ""), str(item.get("end") or ""))


def _provider_fact(
    symbol: str,
    metric: str,
    value: float,
    source_id: str,
    source_type: str,
    entry: dict[str, Any],
    *,
    cik: int | None = None,
) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "source_id": source_id,
        "source_type": source_type,
        "knowledge_id": None,
        "confidence": 0.82 if source_type == "sec_companyfacts" else 0.62,
        "confirmed_by_user": False,
        "timestamp": entry.get("filed") or entry.get("timestamp") or _now_iso(),
        "period_end": entry.get("end"),
        "input_text": f"{source_type} {symbol} {metric}",
        "provider": source_type,
        "cik": cik,
    }


def _extract_yahoo_quote_facts(symbol: str, quote: dict[str, Any]) -> list[dict[str, Any]]:
    timestamp = _timestamp_to_iso(quote.get("regularMarketTime")) or _now_iso()
    fields = {
        "price": quote.get("regularMarketPrice"),
        "market_cap": quote.get("marketCap"),
        "shares_outstanding": quote.get("sharesOutstanding"),
    }
    facts: list[dict[str, Any]] = []
    for metric, raw in fields.items():
        value = _raw_number(raw)
        if value is None:
            continue
        facts.append(
            {
                "metric": metric,
                "value": value,
                "source_id": f"yahoo:{symbol}:{metric}",
                "source_type": "yahoo_quote",
                "knowledge_id": None,
                "confidence": 0.62,
                "confirmed_by_user": False,
                "timestamp": timestamp,
                "period_end": None,
                "input_text": f"Yahoo Finance quote {symbol} {metric}",
                "provider": "yahoo_quote",
                "currency": quote.get("currency"),
            }
        )
    return facts


def _extract_yahoo_chart_facts(symbol: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = (((payload.get("chart") or {}).get("result") or [])[:1] or [{}])[0]
    meta = result.get("meta") or {}
    quote = {
        "regularMarketPrice": meta.get("regularMarketPrice"),
        "regularMarketTime": meta.get("regularMarketTime"),
        "currency": meta.get("currency"),
    }
    return _extract_yahoo_quote_facts(symbol, quote)


def _raw_number(raw: Any) -> float | None:
    if isinstance(raw, dict):
        raw = raw.get("raw")
    if raw in (None, ""):
        return None
    return float(raw)


def _timestamp_to_iso(raw: Any) -> str | None:
    if raw in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(raw), tz=timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
