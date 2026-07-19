"""Deterministic stock-valuation artifacts with one typed trust boundary."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any


CORE_FRAMES: tuple[dict[str, Any], ...] = (
    {"id": "fcf", "name": "Free Cash Flow", "core_question": "What durable free cash flow can the business produce?", "assumptions": ("Free cash flow reflects durable cash conversion", "reinvestment requirements remain observable"), "triggers": ("FCF turns positive", "cash conversion improves"), "failure_conditions": ("one-time cash release", "higher reinvestment")},
    {"id": "comparable_multiples", "name": "Comparable Multiples", "core_question": "Which multiple can comparable businesses support?", "assumptions": ("available market value and operating denominators are comparable", "peer evidence remains candidate until explicitly confirmed"), "triggers": ("quality improves", "peer multiple expands"), "failure_conditions": ("wrong peer group", "unsupported multiple expansion")},
    {"id": "sotp_asset_value", "name": "SOTP / Asset Value", "core_question": "Are parts or assets worth more than the consolidated value?", "assumptions": ("segment or asset values can be observed separately", "net debt and ownership claims remain visible"), "triggers": ("asset sale", "better segment disclosure"), "failure_conditions": ("assets cannot be monetized", "holding discount persists")},
    {"id": "cyclical", "name": "Cyclical", "core_question": "Are earnings at a cycle peak, trough, or mid-cycle?", "assumptions": ("cycle position can be distinguished from durable earnings", "supply and demand signals remain observable"), "triggers": ("pricing inflects", "inventory clears"), "failure_conditions": ("peak earnings treated as durable", "supply response")},
    {"id": "growth_scenario", "name": "Growth / Scenario", "core_question": "What is the value under explicit growth and milestone scenarios?", "assumptions": ("growth scenarios depend on observable milestones", "future scale is not treated as a confirmed fact"), "triggers": ("TAM rises", "milestone validates demand"), "failure_conditions": ("TAM overstated", "milestone delayed")},
)
SPECIALIST_FRAMES: tuple[dict[str, Any], ...] = (
    {"id": "dividend", "name": "Dividend", "core_question": "Can distributable cash flows sustain dividends?", "specialist_only": True},
    {"id": "residual_income", "name": "Residual Income / ROE-PB", "core_question": "Does return on equity exceed the cost of equity?", "specialist_only": True},
    {"id": "event_driven", "name": "Event-Driven", "core_question": "Does a defined corporate event change value realization?", "specialist_only": True},
)

_PACKET_KEYS = frozenset({"schema", "input", "stock", "target_resolution", "facts", "assumptions", "deterministic_calculations", "internal_frame_scores", "selected_frames", "market_implied_bridge", "interpretation", "watch_items", "source_coverage", "degraded_state", "safety"})
_SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_SAFE_PERIOD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FACT_METRICS = frozenset({"revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capex", "free_cash_flow", "cash", "debt", "net_debt", "shares_outstanding", "price", "market_cap", "enterprise_value", "ebitda", "book_value"})
_MONEY_METRICS = _FACT_METRICS - {"shares_outstanding", "price"}
_SOURCE_FAMILIES = frozenset({"company_ir", "market_snapshot", "official_financial", "regulator_filing", "unknown", "vendor_financial"})
_SOURCE_STATUSES = frozenset({"available", "attempted", "complete_missing", "failed", "failure", "missing", "not_attempted", "partial", "present", "stale", "success", "timeout", "unavailable", "unknown"})
_FRESHNESS_LABELS = frozenset({"latest_filing", "latest_market_session", "fresh", "stale"})
_MISSING_CATEGORIES = frozenset({"market_data", "official_financial_facts"})
_SOURCE_STATES = frozenset({"complete", "stale", "financial_missing", "market_missing", "both_missing"})
_MARKET_FACT_METRICS = frozenset({"price", "market_cap", "enterprise_value", "shares_outstanding"})
_OFFICIAL_FAMILIES = frozenset({"official_financial", "regulator_filing", "company_ir"})
_MARKET_STALE_AFTER = timedelta(days=7)
_PEER_STALE_AFTER = timedelta(days=30)
_MAX_ARTIFACT_BYTES = 1_000_000
_MAX_JSON_DEPTH = 40
_MAX_JSON_CONTAINERS = 2_048
_MAX_JSON_NODES = 10_000
_STOCK_WRITE_LOCKS = tuple(threading.Lock() for _ in range(64))
_CURRENT_MARKET_STATUSES = frozenset({"available", "present", "success"})
_LIMITED_MARKET_STATUSES = frozenset({"partial", "stale"})
_CORE_BY_ID = {str(item["id"]): item for item in CORE_FRAMES}
_ASSUMPTIONS = ("This artifact is deterministic research scaffolding, not a target price.", "Peer sets and analyst estimates require separately sourced evidence.")
_FRAME_WORDS = {
    "sotp_asset_value": ("asset", "segment", "holding", "资产", "分部"),
    "cyclical": ("cycle", "cyclical", "semiconductor", "memory", "周期", "半导体"),
    "growth_scenario": ("growth", "tam", "scenario", "ai", "增长", "市场空间"),
}
_SOURCE_TYPE_MAP: dict[str, tuple[str, str]] = {
    "sec_companyfacts": ("sec_companyfacts", "official_financial"),
    "sec_filing": ("sec_filing", "regulator_filing"),
    "hkexnews": ("hkexnews", "regulator_filing"),
    "hkex_filing": ("hkex_filing", "regulator_filing"),
    "dart_filing": ("dart_filing", "regulator_filing"),
    "fss_filing": ("fss_filing", "regulator_filing"),
    "company_ir": ("company_ir", "company_ir"),
    "company_report": ("company_report", "official_financial"),
    "market_snapshot": ("market_snapshot", "market_snapshot"),
    "vendor_financial": ("vendor_financial", "vendor_financial"),
}
_PROVIDER_MAP = {
    "sec": "sec", "sec_companyfacts": "sec", "sec_filing": "sec",
    "officialresearchprovider": "official_research", "official_research": "official_research",
    "hkex": "hkex", "hkexnews": "hkex", "dart": "dart", "fss": "fss",
    "company_ir": "company_ir", "yahoo": "yahoo", "yahoo_chart": "yahoo", "yahoo_finance": "yahoo",
    "shared_market": "shared_market", "market_snapshot": "shared_market", "futu": "shared_market",
    "vendor": "vendor", "vendor_financial": "vendor", "manual": "manual",
    "provider": "generic_provider", "generic_provider": "generic_provider",
}
_MAPPING_MAP = {
    "sec": "sec", "officialresearchprovider": "official_research", "official_research": "official_research",
    "hkex": "hkex", "dart": "dart", "fss": "fss", "company_ir": "company_ir",
    "yahoo": "yahoo", "yahoo_finance": "yahoo", "shared_market": "shared_market", "market_snapshot": "shared_market",
    "vendor": "vendor", "vendor_financial": "vendor", "manual": "manual",
    "provider": "generic_provider", "generic_provider": "generic_provider",
}
_GAP_COPY = {
    "missing_market_data": "latest market price or market cap is missing",
    "missing_enterprise_value": "enterprise value cannot be derived without market cap and net debt",
    "missing_revenue": "revenue is missing",
    "missing_fcf": "free cash flow is missing",
    "missing_net_income": "net income is missing",
    "missing_source_metadata": "source metadata is missing",
    "missing_confirmed_case": "no user-confirmed valuation case",
    "missing_peer_evidence": "comparable peer evidence is missing",
    "stale_peer_evidence": "comparable peer evidence is stale",
}
_REASON_COPY = {
    **_GAP_COPY,
    "context_identity_mismatch": "context stock identity mismatched the explicit target and was omitted",
    "snapshot_identity_mismatch": "provider snapshot identity mismatched the explicit target and was omitted",
    "missing_official_source": "official financial source coverage is missing",
    "missing_stock_profile": "stock profile is missing",
    "no_canonical_scoring_signal": "no canonical valuation scoring signal was derived from the stock profile",
    "stale_market_data": "one or more market fields are stale",
}
_CALC_SPECS: dict[str, tuple[str, tuple[str, ...], str, str | None]] = {
    "free_cash_flow": ("operating_cash_flow - abs(capex)", ("operating_cash_flow", "capex"), "currency", None),
    "net_debt": ("debt - cash", ("debt", "cash"), "currency", None),
    "market_cap": ("price * shares_outstanding", ("price", "shares_outstanding"), "currency", None),
    "enterprise_value": ("market_cap + net_debt", ("market_cap", "net_debt"), "currency", None),
    "gross_margin": ("gross_profit / revenue", ("gross_profit", "revenue"), "percent", None),
    "operating_margin": ("operating_income / revenue", ("operating_income", "revenue"), "percent", None),
    "fcf_margin": ("free_cash_flow / revenue", ("free_cash_flow", "revenue"), "percent", None),
    "fcf_yield": ("free_cash_flow / market_cap", ("free_cash_flow", "market_cap"), "percent", "negative FCF"),
    "pe": ("market_cap / net_income", ("market_cap", "net_income"), "multiple", "negative earnings"),
    "ps": ("market_cap / revenue", ("market_cap", "revenue"), "multiple", None),
    "ev_ebitda": ("enterprise_value / ebitda", ("enterprise_value", "ebitda"), "multiple", "negative EBITDA"),
    "ev_fcf": ("enterprise_value / free_cash_flow", ("enterprise_value", "free_cash_flow"), "multiple", "negative FCF"),
}


def valuation_method_library() -> list[dict[str, Any]]:
    """Return five core and three specialist-only method definitions."""
    return [{"id": item["id"], "name": item["name"], "core_question": item["core_question"], "triggers": list(item.get("triggers", ())), "failure_conditions": list(item.get("failure_conditions", ())), "specialist_only": bool(item.get("specialist_only"))} for item in (*CORE_FRAMES, *SPECIALIST_FRAMES)]


def render_valuation_methods() -> str:
    lines = ["Valuation method library (P0 ranks only the five core frames):"]
    for index, frame in enumerate(valuation_method_library(), 1):
        lines.append(f"{index}. {frame['name']}{' [specialist-only]' if frame['specialist_only'] else ''} — {frame['core_question']}")
    lines.append("Specialist frames are metadata only unless an explicit specialist workflow triggers them.")
    return "\n".join(lines)


def build_valuation_artifact(
    context: dict[str, object], *, symbol: str, market: str, output_dir: Path, command: str,
    provider_snapshot: dict[str, object] | None = None, now: datetime | None = None,
) -> tuple[dict[str, object], Path]:
    """Normalize untrusted inputs, validate one internal packet, and persist it."""
    if not isinstance(context, dict):
        raise TypeError("context must be a mapping")
    symbol, market = _validate_target(symbol, market)
    instant = _utc_instant(now)
    snapshot = provider_snapshot if isinstance(provider_snapshot, dict) else {}
    stock, context_mismatch = _normalize_stock(context, symbol, market)
    snapshot_mismatch = _snapshot_mismatch(snapshot, symbol, market)
    safe_context, safe_snapshot = ({} if context_mismatch else context), ({} if snapshot_mismatch else snapshot)
    facts, registry = _normalize_facts(safe_context, safe_snapshot)
    currency = _infer_currency(facts, market)
    facts = [_decorate_fact(fact, currency) for fact in facts]
    coverage = _coverage(facts, registry, safe_snapshot, instant)
    confirmed_case = _confirmed_case(safe_context, symbol, market)
    peer_evidence = _normalize_peer_evidence(safe_context, safe_snapshot, symbol, market, instant)
    domain = _canonical_domain(
        stock,
        facts,
        registry,
        confirmed_case,
        peer_evidence,
        market,
        str(coverage["market_snapshot_status"]),
    )
    calculations, gap_codes = domain["calculations"], domain["gap_codes"]
    identity_codes = []
    if context_mismatch:
        identity_codes.append("context_identity_mismatch")
    if snapshot_mismatch:
        identity_codes.append("snapshot_identity_mismatch")
    scores, bridge, selected = domain["scores"], domain["bridge"], domain["selected"]
    reason_codes = _reason_codes(gap_codes, coverage, stock, identity_codes)
    packet: dict[str, object] = {
        "schema": "stock_valuation_packet.v1",
        "input": {"symbol": symbol, "market": market, "command": f"valuation {market}.{symbol}", "created_at": instant.isoformat()},
        "stock": stock,
        "target_resolution": _target_resolution(symbol, market, currency, _mapping_category(safe_snapshot)),
        "facts": facts,
        "assumptions": _assumptions(confirmed_case, peer_evidence, selected),
        "deterministic_calculations": calculations,
        "internal_frame_scores": scores,
        "selected_frames": selected,
        "market_implied_bridge": bridge,
        "interpretation": _interpretation(selected, gap_codes),
        "watch_items": _watch_items(selected),
        "source_coverage": coverage,
        "degraded_state": _degraded_state(reason_codes, gap_codes, coverage),
        "safety": {"direct_investment_advice": False, "writes_formal_user_insight": False, "research_aid_only": True},
    }
    if not _valid_packet(packet, symbol, market):
        raise ValueError("normalized valuation packet failed validation")
    return packet, _write_packet(packet, Path(output_dir), symbol, market, instant)


def load_latest_valuation_artifact(*, symbol: str, market: str, output_dir: Path) -> dict[str, object] | None:
    symbol, market = _validate_target(symbol, market)
    path = Path(output_dir) / "valuation" / f"{symbol}_{market}_valuation_latest.json"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_ARTIFACT_BYTES + 1)
        if len(raw) > _MAX_ARTIFACT_BYTES:
            return None
        packet = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        _ensure_bounded_json_tree(packet)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError):
        return None
    try:
        return packet if isinstance(packet, dict) and _valid_packet(packet, symbol, market) else None
    except (OverflowError, RecursionError, TypeError, ValueError):
        return None


def build_valuation_artifact_evidence(packet: dict[str, object]) -> dict[str, object]:
    """Return the shared typed public projection; never read an artifact path."""
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    return _checked_public_projection(packet)


def render_valuation_card(packet: dict[str, object]) -> str:
    """Render only the shared typed public projection."""
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    public = _checked_public_projection(packet)
    stock, degraded = public["stock"], public["degraded_state"]
    coverage = public["source_coverage"]
    target = ".".join(str(stock[key]) for key in ("market", "symbol") if stock.get(key))
    lines = [f"Valuation research card: {target}{' ' + str(stock['name']) if stock.get('name') else ''}".rstrip(), f"Status: {'degraded' if degraded.get('degraded') else 'ok'}", "Data gaps:"]
    lines.extend(f"- {gap}" for gap in degraded.get("data_gaps", []))
    if not degraded.get("data_gaps"):
        lines.append("- none identified by the normalized packet")
    lines.append("Facts:")
    if public["facts"]:
        for fact in public["facts"]:
            observed = (
                f"period {fact['period_end']}" if fact.get("period_end")
                else f"as of {fact['timestamp']}" if fact.get("timestamp")
                else "period unavailable"
            )
            lines.append(
                f"- {fact['metric']}: {fact['display_value']} "
                f"({fact['source_family']}; {observed})"
            )
    else:
        lines.append("- none available")
    lines.append("Calculations:")
    if public["deterministic_calculations"]:
        for calculation in public["deterministic_calculations"]:
            refs = ", ".join(str(ref) for ref in calculation.get("input_refs", [])[:8])
            lines.append(
                f"- {calculation['metric']}: {calculation['display_value']} "
                f"(inputs: {refs or 'unavailable'})"
            )
    else:
        lines.append("- none available")
    lines.append("Data freshness:")
    lines.append(f"- Financials as of: {coverage.get('financials_as_of', 'unavailable')}")
    lines.append(f"- Market data as of: {coverage.get('market_data_as_of', 'unavailable')}")
    lines.append(f"- Stale fields: {', '.join(coverage.get('stale_fields', [])) or 'none'}")
    lines.append("Source coverage:")
    lines.append(f"- Attempted source families: {', '.join(coverage.get('attempted_source_families', [])) or 'none'}")
    lines.append(f"- Missing categories: {', '.join(coverage.get('missing_categories', [])) or 'none'}")
    retry_attempts = [
        item for item in coverage.get("source_attempts", [])
        if isinstance(item, dict) and item.get("status") in {"failed", "timeout"}
    ]
    if retry_attempts:
        retry_summary = ", ".join(
            f"{item['family']} ({'timed out' if item['status'] == 'timeout' else 'failed'})"
            for item in retry_attempts
        )
        lines.append(f"- Retry needed: {retry_summary}")
    recovery = {
        "financial_missing": "official financial facts are missing",
        "market_missing": "current market data is missing",
        "both_missing": "official financial facts and current market data are missing",
        "stale": "stale fields require refresh before current-market interpretation",
    }.get(str(degraded.get("source_state")))
    if recovery:
        lines.append(f"Recovery: {recovery}; rerun after the named source categories refresh.")
    lines.append("Market-implied bridge:")
    bridge_lines = public["market_implied_bridge"].get("bridge_lines", [])
    lines.extend(f"- {item['display']}" for item in bridge_lines)
    if not bridge_lines:
        lines.append("- unavailable because the required market inputs are missing")
    lines.append("Relevant frames:")
    for frame in public["selected_frames"]:
        lines.append(f"- {frame['name']} (fit={frame.get('fit_to_current_market_value', 'unknown')}, confidence={frame.get('confidence', 'low')})")
        lines.append(f"  Assumptions: {', '.join(frame.get('assumptions', []))}")
        lines.append(f"  Rerating triggers: {', '.join(frame.get('rerating_triggers', []))}")
        lines.append(f"  Failure conditions: {', '.join(frame.get('failure_conditions', []))}")
        provenance = frame.get("provenance") if isinstance(frame.get("provenance"), dict) else {}
        lines.append(f"  Rule provenance: {provenance.get('rule_id', 'unavailable')}")
    lines.append("Assumptions:")
    lines.extend(f"- {item}" for item in public["assumptions"].get("items", []))
    interpretation = public["interpretation"]
    lines.append("Interpretation:")
    lines.extend(f"- {item}" for item in interpretation.get("summary", []))
    optional = interpretation.get("optional_narrative", {})
    if isinstance(optional, dict):
        lines.append(f"- Optional narrative: {optional.get('status', 'unavailable')} ({str(optional.get('provenance', 'model_unavailable')).replace('_', ' ')})")
    lines.append("Watch items:")
    lines.extend(f"- {item}" for item in public["watch_items"])
    lines.append("Safety: research aid only; no buy/sell recommendation and no formal user insight was written.")
    return "\n".join(lines)


# Ingress normalization -----------------------------------------------------

def _validate_target(symbol: str, market: str) -> tuple[str, str]:
    symbol, market = str(symbol).strip().upper(), str(market).strip().upper()
    if not _SAFE_TARGET.fullmatch(symbol) or not _SAFE_TARGET.fullmatch(market):
        raise ValueError("target must be a market-qualified stock identifier")
    return symbol, market


def _utc_instant(now: datetime | None) -> datetime:
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(timezone.utc).replace(microsecond=0)


def _optional_target(value: object) -> str | None:
    normalized = value.strip().upper() if isinstance(value, str) else ""
    return normalized if _SAFE_TARGET.fullmatch(normalized) else None


def _qualified_target(value: object) -> tuple[str, str] | None:
    if not isinstance(value, str) or "." not in value:
        return None
    market, symbol = value.split(".", 1)
    normalized_market, normalized_symbol = _optional_target(market), _optional_target(symbol)
    return (normalized_market, normalized_symbol) if normalized_market and normalized_symbol else None


def _enum(value: object, allowed: set[str] | frozenset[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _normalize_stock(context: dict[str, object], symbol: str, market: str) -> tuple[dict[str, object], bool]:
    raw = context.get("stock") if isinstance(context.get("stock"), dict) else {}
    mismatch = bool(
        (raw.get("symbol") is not None and _optional_target(raw.get("symbol")) != symbol)
        or (raw.get("market") is not None and _optional_target(raw.get("market")) != market)
    )
    stock: dict[str, object] = {"symbol": symbol, "market": market}
    if mismatch:
        return stock, True
    if isinstance(raw.get("id"), int) and not isinstance(raw["id"], bool) and raw["id"] >= 0:
        stock["id"] = raw["id"]
    if any(isinstance(raw.get(field), str) and bool(raw[field].strip()) for field in ("name", "core_business", "stock_character")):
        stock["profile_present"] = True
    signals: dict[str, list[str]] = {}
    for field in ("core_business", "stock_character"):
        text = raw.get(field)
        if not isinstance(text, str): continue
        matches = sorted(frame_id for frame_id, words in _FRAME_WORDS.items() if any(_keyword_match(text, word) for word in words))
        if matches: signals[field] = matches
    if signals: stock["scoring_signals"] = signals
    return stock, False


def _keyword_match(text: str, keyword: str) -> bool:
    if keyword.isascii():
        return re.search(rf"(?<![A-Za-z0-9_]){re.escape(keyword)}(?![A-Za-z0-9_])", text, re.IGNORECASE) is not None
    return keyword in text


def _snapshot_mismatch(snapshot: dict[str, object], symbol: str, market: str) -> bool:
    target = snapshot.get("target_resolution") if isinstance(snapshot.get("target_resolution"), dict) else {}
    if "normalized_symbol" in target and _optional_target(target.get("normalized_symbol")) != symbol: return True
    if "normalized_market" in target and _optional_target(target.get("normalized_market")) != market: return True
    if "normalized_target" in target and _qualified_target(target.get("normalized_target")) != (market, symbol): return True
    return False


def _source_descriptor(raw: dict[str, object]) -> dict[str, object]:
    raw_type = raw.get("source_type")
    source_type, family = _SOURCE_TYPE_MAP.get(raw_type.strip().lower(), ("unknown", "unknown")) if isinstance(raw_type, str) else ("unknown", "unknown")
    result = {"family": family, "source_type": source_type}
    if provider := _provider_category(raw.get("provider")): result["provider_category"] = provider
    return result


def _provider_category(value: object) -> str | None:
    return _PROVIDER_MAP.get(value.strip().lower()) if isinstance(value, str) else None


def _mapping_category(snapshot: dict[str, object]) -> str | None:
    target = snapshot.get("target_resolution") if isinstance(snapshot.get("target_resolution"), dict) else {}
    value = target.get("mapping_source")
    return _MAPPING_MAP.get(value.strip().lower()) if isinstance(value, str) else None


def _source_id(descriptor: dict[str, object]) -> str:
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"source:{hashlib.sha256(canonical.encode('ascii')).hexdigest()[:16]}"


def _currency(value: object) -> str | None:
    normalized = value.strip().upper() if isinstance(value, str) else ""
    return normalized if re.fullmatch(r"[A-Z]{3}", normalized) else None


def _period(value: object) -> str | None:
    if not isinstance(value, str) or not _SAFE_PERIOD.fullmatch(value): return None
    try: datetime.fromisoformat(value)
    except ValueError: return None
    return value


def _timestamp(value: object) -> str | None:
    if not isinstance(value, str): return None
    try: parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError: return None
    if parsed.tzinfo is None or parsed.utcoffset() is None: return None
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _datetime_from_timestamp(value: object) -> datetime | None:
    normalized = _timestamp(value)
    return datetime.fromisoformat(normalized) if normalized is not None else None


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)): return None
    try: number = float(value)
    except (OverflowError, TypeError, ValueError): return None
    return number if math.isfinite(number) else None


def _normalize_facts(context: dict[str, object], snapshot: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    registry: dict[str, dict[str, object]] = {}
    latest: dict[str, dict[str, object]] = {}
    for owner in (context, snapshot):
        records = owner.get("facts")
        if not isinstance(records, list): continue
        for raw in records:
            if not isinstance(raw, dict) or not (metric := _enum(raw.get("metric"), _FACT_METRICS)) or (number := _finite(raw.get("value"))) is None: continue
            descriptor = _source_descriptor(raw)
            source_id = _source_id(descriptor); registry[source_id] = {"id": source_id, **descriptor}
            fact: dict[str, object] = {"id": f"fact:{metric}", "metric": metric, "value": number, "source_id": source_id, "source_type": descriptor["source_type"], "source_family": descriptor["family"]}
            if descriptor.get("provider_category"): fact["provider_category"] = descriptor["provider_category"]
            if normalized := _currency(raw.get("currency")): fact["currency"] = normalized
            if normalized := _period(raw.get("period_end")): fact["period_end"] = normalized
            if normalized := _timestamp(raw.get("timestamp")): fact["timestamp"] = normalized
            if normalized := _timestamp(raw.get("fetched_at")): fact["fetched_at"] = normalized
            if normalized := _enum(raw.get("freshness"), _FRESHNESS_LABELS): fact["freshness"] = normalized
            latest[metric] = fact
    for owner in (context, snapshot):
        records = owner.get("sources")
        if not isinstance(records, list): continue
        for raw in records:
            if isinstance(raw, dict):
                descriptor = _source_descriptor(raw); source_id = _source_id(descriptor)
                registry[source_id] = {"id": source_id, **descriptor}
    return [latest[key] for key in sorted(latest)], [registry[key] for key in sorted(registry)]


def _fact_kind(metric: str) -> str:
    return "currency" if metric in _MONEY_METRICS else "currency_per_share" if metric == "price" else "number"


def _decorate_fact(fact: dict[str, object], fallback_currency: str | None) -> dict[str, object]:
    result, kind = dict(fact), _fact_kind(str(fact["metric"]))
    normalized_currency = _currency(fact.get("currency")) or fallback_currency
    result["display_kind"] = kind
    if kind.startswith("currency") and normalized_currency: result["currency"] = normalized_currency
    else: result.pop("currency", None)
    result["display_value"] = _format(float(fact["value"]), kind, normalized_currency)
    return result


# Deterministic domain ------------------------------------------------------

def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0): return None
    try: return _finite(numerator / denominator)
    except (OverflowError, TypeError, ValueError, ZeroDivisionError): return None


def _format(value: float, kind: str, currency: str | None) -> str | None:
    if not math.isfinite(value): return None
    if kind == "percent":
        scaled = _finite(value * 100)
        return f"{scaled:.1f}%" if scaled is not None else None
    if kind == "multiple": return f"{value:.1f}x"
    prefix = {"USD": "$", "HKD": "HK$"}.get(str(currency or "").upper(), f"{str(currency).upper()} " if currency else "")
    if kind == "currency_per_share": return f"{prefix}{value:.2f}/share"
    if kind == "currency":
        scale, suffix = (1_000_000_000, "B") if abs(value) >= 1_000_000_000 else (1_000_000, "M") if abs(value) >= 1_000_000 else (1_000, "K") if abs(value) >= 1_000 else (1, "")
        return f"{prefix}{value / scale:.1f}{suffix}"
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _flatten_refs(inputs: tuple[str, ...], facts: dict[str, str], derived: dict[str, dict[str, object]]) -> tuple[str, ...]:
    refs: list[str] = []
    for metric in inputs:
        if metric in facts: refs.append(facts[metric]); continue
        upstream = derived.get(metric, {}).get("input_refs")
        if isinstance(upstream, (list, tuple)): refs.extend(ref for ref in upstream if isinstance(ref, str))
    return tuple(dict.fromkeys(refs))


def _calculate(values: dict[str, float], facts: dict[str, str], currency: str | None) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []; derived: dict[str, dict[str, object]] = {}
    def add(metric: str, value: float, formula: str, inputs: tuple[str, ...], kind: str, reason: str | None = None) -> None:
        if not math.isfinite(value): return
        value = round(value, 6)
        item: dict[str, object] = {"metric": metric, "value": value, "formula": formula, "inputs": list(inputs), "input_refs": _flatten_refs(inputs, facts, derived), "display_kind": kind, "meaningful": True}
        if currency and kind == "currency": item["currency"] = currency
        if reason: item.update({"value": None, "raw_value": value, "meaningful": False, "meaningfulness_reason": reason, "display_value": f"not meaningful ({reason})"})
        elif (display := _format(value, kind, currency)) is not None: item["display_value"] = display
        else: return
        result.append(item); derived[metric] = item
    fcf = values.get("free_cash_flow")
    if fcf is not None: add("free_cash_flow", fcf, "reported free_cash_flow", ("free_cash_flow",), "currency")
    elif "operating_cash_flow" in values and "capex" in values:
        fcf = values["operating_cash_flow"] - abs(values["capex"]); add("free_cash_flow", fcf, *_CALC_SPECS["free_cash_flow"][:3])
    net_debt = values.get("net_debt")
    if net_debt is not None: add("net_debt", net_debt, "reported net_debt", ("net_debt",), "currency")
    elif "debt" in values and "cash" in values:
        net_debt = values["debt"] - values["cash"]; add("net_debt", net_debt, *_CALC_SPECS["net_debt"][:3])
    market_cap = values.get("market_cap")
    if market_cap is not None: add("market_cap", market_cap, "reported market_cap", ("market_cap",), "currency")
    elif "price" in values and "shares_outstanding" in values:
        market_cap = values["price"] * values["shares_outstanding"]; add("market_cap", market_cap, *_CALC_SPECS["market_cap"][:3])
    enterprise_value = values.get("enterprise_value")
    if enterprise_value is not None: add("enterprise_value", enterprise_value, "reported enterprise_value", ("enterprise_value",), "currency")
    elif market_cap is not None and net_debt is not None:
        enterprise_value = market_cap + net_debt; add("enterprise_value", enterprise_value, *_CALC_SPECS["enterprise_value"][:3])
    ratios = (("gross_margin", values.get("gross_profit"), values.get("revenue")), ("operating_margin", values.get("operating_income"), values.get("revenue")), ("fcf_margin", fcf, values.get("revenue")), ("fcf_yield", fcf, market_cap), ("pe", market_cap, values.get("net_income")), ("ps", market_cap, values.get("revenue")), ("ev_ebitda", enterprise_value, values.get("ebitda")), ("ev_fcf", enterprise_value, fcf))
    for metric, numerator, denominator in ratios:
        if (ratio := _safe_divide(numerator, denominator)) is None: continue
        formula, inputs, kind, configured_reason = _CALC_SPECS[metric]
        reason = configured_reason if configured_reason and (denominator < 0 or (metric == "fcf_yield" and numerator < 0)) else None
        add(metric, ratio, formula, inputs, kind, reason)
    return result


def _data_gap_codes(
    values: dict[str, float],
    calculations: list[dict[str, object]],
    registry: list[dict[str, object]],
    confirmed_case: bool,
    peer_evidence: dict[str, object],
) -> list[str]:
    del confirmed_case
    derived, gaps = {str(item["metric"]) for item in calculations}, []
    if "price" not in values and "market_cap" not in values: gaps.append("missing_market_data")
    if "enterprise_value" not in values and "enterprise_value" not in derived: gaps.append("missing_enterprise_value")
    for metric in ("revenue", "free_cash_flow", "net_income"):
        if metric not in values and metric not in derived: gaps.append(f"missing_{metric.replace('free_cash_flow', 'fcf')}")
    if not any(item.get("source_type") != "unknown" for item in registry): gaps.append("missing_source_metadata")
    if peer_evidence.get("status") == "missing":
        gaps.append("missing_peer_evidence")
    elif peer_evidence.get("status") == "stale_candidate":
        gaps.append("stale_peer_evidence")
    return gaps


def _frame_supported(
    frame_id: str,
    values: dict[str, float],
    calculations: list[dict[str, object]],
    market_status: str | None = None,
    peer_evidence: dict[str, object] | None = None,
) -> bool:
    calculated = {str(item["metric"]): item for item in calculations}
    if frame_id == "fcf": return "free_cash_flow" in values or {"operating_cash_flow", "capex"} <= values.keys()
    if frame_id == "comparable_multiples":
        market_value = values.get("market_cap") if "market_cap" in values else _calculated_value(calculated.get("market_cap"))
        if _market_fit_state(market_status) == "unsupported": return False
        if not isinstance(peer_evidence, dict) or peer_evidence.get("status") not in {"candidate", "stale_candidate"}:
            return False
        return market_value is not None and market_value > 0 and any((values.get(metric) or 0) > 0 for metric in ("revenue", "net_income", "ebitda"))
    return True


def _market_fit_state(status: str | None) -> str:
    if status in _CURRENT_MARKET_STATUSES: return "current"
    if status in _LIMITED_MARKET_STATUSES: return "limited"
    return "unsupported"


def _score_frames(
    stock: dict[str, object],
    values: dict[str, float],
    calculations: list[dict[str, object]],
    gaps: list[str],
    facts: dict[str, str],
    market_status: str | None = None,
    peer_evidence: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    score = {"fcf": .15, "comparable_multiples": .2, "sotp_asset_value": .05, "cyclical": .05, "growth_scenario": .1}
    if _frame_supported("fcf", values, calculations): score["fcf"] += .55
    if _frame_supported("comparable_multiples", values, calculations, market_status, peer_evidence): score["comparable_multiples"] += .45
    matched = {key: [] for key in score}
    signals = stock.get("scoring_signals") if isinstance(stock.get("scoring_signals"), dict) else {}
    for frame_id in _FRAME_WORDS:
        for field in ("core_business", "stock_character"):
            if isinstance(signals.get(field), list) and frame_id in signals[field]: matched[frame_id].append(field)
        if matched[frame_id]: score[frame_id] += .65 if frame_id == "cyclical" else .55
    derived = {str(item["metric"]): item for item in calculations}
    fact_inputs = {"fcf": ("free_cash_flow", "operating_cash_flow", "capex"), "comparable_multiples": ("market_cap", "revenue", "net_income", "ebitda"), "sotp_asset_value": (), "cyclical": (), "growth_scenario": ()}
    result = []
    for frame_id, value in sorted(score.items(), key=lambda item: (-item[1], item[0])):
        refs = [f"packet:method_library:{frame_id}", *_flatten_refs(fact_inputs[frame_id], facts, derived), *(f"packet:stock:scoring_signals:{field}:{frame_id}" for field in matched[frame_id])]
        frame = _CORE_BY_ID[frame_id]
        input_refs = tuple(dict.fromkeys(refs))
        result.append({
            "id": frame_id,
            "name": frame["name"],
            "score": round(min(value, 1), 3),
            "reason": "ranked from normalized facts and declared stock fields",
            "input_refs": input_refs,
            "degraded_by": [gap for gap in gaps if frame_id.split("_")[0] in gap],
            "assumptions": list(frame["assumptions"]),
            "rerating_triggers": list(frame["triggers"]),
            "failure_conditions": list(frame["failure_conditions"]),
            "provenance": {
                "type": "deterministic_rule",
                "rule_id": "stock_valuation_frame_score.v1",
                "input_refs": input_refs,
            },
        })
    return result


def _calculated_value(item: dict[str, object] | None) -> float | None:
    if not item: return None
    return _finite(item.get("value")) if _finite(item.get("value")) is not None else _finite(item.get("raw_value"))


def _build_bridge(
    values: dict[str, float],
    calculations: list[dict[str, object]],
    scores: list[dict[str, object]],
    gaps: list[str],
    currency: str | None,
    facts: dict[str, str],
    market_status: str | None = None,
    peer_evidence: dict[str, object] | None = None,
) -> dict[str, object]:
    derived = {str(item["metric"]): item for item in calculations}
    enterprise_value = values.get("enterprise_value") if values.get("enterprise_value") is not None else _calculated_value(derived.get("enterprise_value"))
    revenue, lines = values.get("revenue"), []
    def add(kind: str, display: str, refs: tuple[str, ...] | list[str]) -> None: lines.append({"type": kind, "display": display, "input_refs": tuple(refs)})
    if (ps := derived.get("ps")) and isinstance(ps.get("display_value"), str): add("sales_anchor", f"P/S: {ps['display_value']} anchors current market value.", ps["input_refs"])
    if (ev_sales := _safe_divide(enterprise_value, revenue)) is not None and (display := _format(ev_sales, "multiple", currency)) is not None: add("ev_sales_anchor", f"EV/Sales: {display}.", _flatten_refs(("enterprise_value", "revenue"), facts, derived))
    if (fcf_yield := derived.get("fcf_yield")) and isinstance(fcf_yield.get("display_value"), str): add("fcf_yield", "FCF yield is not meaningful with negative FCF." if fcf_yield.get("meaningful") is False else f"FCF yield: {fcf_yield['display_value']}.", fcf_yield["input_refs"])
    ranking = []
    for item in scores:
        frame_gaps = list(gaps) if item["id"] == "comparable_multiples" else [
            gap for gap in gaps if gap not in {"missing_peer_evidence", "stale_peer_evidence"}
        ]
        supported = _frame_supported(str(item["id"]), values, calculations, market_status, peer_evidence)
        limited = item["id"] == "comparable_multiples" and (
            _market_fit_state(market_status) == "limited"
            or (isinstance(peer_evidence, dict) and peer_evidence.get("status") == "stale_candidate")
        )
        unconfirmed_peer = item["id"] == "comparable_multiples" and isinstance(peer_evidence, dict) and peer_evidence.get("status") in {"candidate", "stale_candidate"}
        fit = "insufficient_data" if not supported else "partial_fit" if limited else "fits" if item["score"] >= .6 else "partial_fit" if item["score"] >= .2 else "insufficient_data"
        ranking.append({**item, "fit_to_current_market_value": fit, "why_it_fits_or_not": "ranked using deterministic normalized inputs", "main_data_gaps": frame_gaps, "confidence": "low" if frame_gaps or not supported or limited or unconfirmed_peer else "medium"})
    return {"bridge_lines": lines, "frame_fit_ranking": ranking}


def _select_frames(ranking: list[dict[str, object]]) -> list[dict[str, object]]:
    order = {"fits": 0, "partial_fit": 1, "insufficient_data": 2, "does_not_fit": 3}
    ranked = sorted(ranking, key=lambda item: (order.get(str(item.get("fit_to_current_market_value")), 4), -float(item.get("score") or 0)))
    return [item for item in ranked if float(item.get("score") or 0) >= .2][:3] or ranked[:1]


def _status(value: object) -> str | None:
    return _enum(value, _SOURCE_STATUSES)


def _attempts(value: object) -> list[dict[str, str]]:
    candidates = [item for _, item in sorted(value.items(), key=lambda pair: str(pair[0]))] if isinstance(value, dict) else value if isinstance(value, list) else []
    return [{"family": family, "status": status} for item in candidates if isinstance(item, dict) and (family := _enum(item.get("family"), _SOURCE_FAMILIES)) and (status := _status(item.get("status")))]


def _coverage(
    facts: list[dict[str, object]],
    registry: list[dict[str, object]],
    snapshot: dict[str, object],
    created_at: datetime,
) -> dict[str, object]:
    market_facts = [item for item in facts if item.get("source_family") == "market_snapshot" and item.get("metric") in _MARKET_FACT_METRICS]
    official_facts = [item for item in facts if item.get("source_family") in _OFFICIAL_FAMILIES and item.get("metric") not in _MARKET_FACT_METRICS]
    financial_periods = sorted({str(item["period_end"]) for item in official_facts if isinstance(item.get("period_end"), str)})
    market_observations = sorted({str(item["timestamp"]) for item in market_facts if isinstance(item.get("timestamp"), str)})
    stale_fields = sorted({str(item["metric"]) for item in facts if _fact_is_stale(item, created_at)})
    missing_categories = sorted(
        (["market_data"] if not market_facts else [])
        + (["official_financial_facts"] if not official_facts else [])
    )
    attempts = _attempts(snapshot.get("source_attempts"))
    attempted_families = sorted({item["family"] for item in attempts if item["status"] != "not_attempted"})
    market_status = _status(snapshot.get("market_snapshot_status")) or "unknown"
    if any(item.get("metric") in stale_fields for item in market_facts):
        market_status = "stale"
    financial_status = _status(snapshot.get("financial_fact_status")) or ("present" if official_facts else "missing")
    result: dict[str, object] = {
        "fact_count": len(facts),
        "fact_source_id_count": len({item["source_id"] for item in facts}),
        "source_count": len(registry),
        "official_source_count": sum(item.get("family") in _OFFICIAL_FAMILIES for item in registry),
        "market_snapshot_status": market_status,
        "financial_fact_status": financial_status,
        "provider_statuses": {
            "market_snapshot": {"status": "available" if market_facts else "complete_missing"},
            "financial_facts": {"status": "available" if official_facts else "complete_missing"},
        },
        "source_attempts": attempts,
        "attempted_source_families": attempted_families,
        "missing_categories": missing_categories,
        "stale_fields": stale_fields,
        "source_registry": registry,
    }
    if financial_periods:
        result["financials_as_of"] = financial_periods[-1]
    if market_observations:
        result["market_data_as_of"] = market_observations[-1]
    return result


def _fact_is_stale(fact: dict[str, object], created_at: datetime) -> bool:
    if fact.get("freshness") == "stale":
        return True
    if fact.get("source_family") != "market_snapshot":
        return False
    timestamp = _timestamp(fact.get("timestamp"))
    if timestamp is None:
        return False
    observed_at = datetime.fromisoformat(timestamp)
    return created_at - observed_at > _MARKET_STALE_AFTER


def _interpretation(selected: list[dict[str, object]], gaps: list[str]) -> dict[str, object]:
    items = [f"{_CORE_BY_ID[str(item['id'])]['name']} is a selected research frame." for item in selected if str(item.get("id")) in _CORE_BY_ID]
    if gaps:
        items.append("Data gaps mean this is research scaffolding rather than a target price.")
    return {
        "summary": items,
        "provenance": {"type": "deterministic_rule", "rule_id": "stock_valuation_frame_selection.v1"},
        "optional_narrative": {"status": "unavailable", "provenance": "model_unavailable"},
    }


def _watch_items(selected: list[dict[str, object]]) -> list[str]:
    result: list[str] = []
    for item in selected:
        frame = _CORE_BY_ID.get(str(item.get("id")))
        if frame is None:
            continue
        result.append(f"{frame['name']} rerating triggers: {', '.join(frame['triggers'])}.")
        result.append(f"{frame['name']} failure conditions: {', '.join(frame['failure_conditions'])}.")
    return result


def _assumptions(
    confirmed_case: bool,
    peer_evidence: dict[str, object],
    selected: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "user_confirmed_valuation_case": confirmed_case,
        "peer_evidence": dict(peer_evidence),
        "items": list(_ASSUMPTIONS),
        "by_frame": [
            {"frame_id": str(item["id"]), "items": list(_CORE_BY_ID[str(item["id"])]["assumptions"])}
            for item in selected
            if str(item.get("id")) in _CORE_BY_ID
        ],
    }


def _target_resolution(symbol: str, market: str, fallback_currency: str | None, mapping_category: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {"input_target": f"{market}.{symbol}", "normalized_target": f"{market}.{symbol}", "normalized_symbol": symbol, "normalized_market": market}
    if fallback_currency: result["currency"] = fallback_currency
    if mapping_category: result["mapping_category"] = mapping_category
    return result


def _infer_currency(facts: list[dict[str, object]], market: str) -> str | None:
    return next((_currency(fact.get("currency")) for fact in facts if _currency(fact.get("currency"))), None) or {"US": "USD", "HK": "HKD", "KR": "KRW"}.get(market)


def _confirmed_case(context: dict[str, object], symbol: str, market: str) -> bool:
    del context, symbol, market
    # P0 has no trusted repository/verifier argument at artifact load time.
    # A stored boolean or checksum would therefore be self-asserted and forgeable.
    return False


def _normalize_peer_evidence(
    context: dict[str, object],
    snapshot: dict[str, object],
    symbol: str,
    market: str,
    created_at: datetime,
) -> dict[str, object]:
    result = _missing_peer_evidence()
    for owner in (context, snapshot):
        raw = owner.get("peer_evidence")
        if not isinstance(raw, dict) or raw.get("schema") != "stock_valuation_peer_evidence.v1":
            continue
        if raw.get("status") not in {"candidate", "manual_candidate", "confirmed"}:
            continue
        as_of = _timestamp(raw.get("as_of"))
        peers = raw.get("peers")
        if as_of is None or not isinstance(peers, (list, tuple)) or not 1 <= len(peers) <= 3:
            continue
        normalized_peers: set[tuple[str, str]] = set()
        for peer in peers:
            if not isinstance(peer, dict):
                normalized_peers.clear()
                break
            peer_symbol = _optional_target(peer.get("symbol"))
            peer_market = _optional_target(peer.get("market"))
            if not peer_symbol or not peer_market or (peer_symbol, peer_market) == (symbol, market):
                normalized_peers.clear()
                break
            normalized_peers.add((peer_symbol, peer_market))
        if not normalized_peers or len(normalized_peers) != len(peers):
            continue
        observed_at = datetime.fromisoformat(as_of)
        if observed_at > created_at + timedelta(days=1):
            continue
        status = "stale_candidate" if created_at - observed_at > _PEER_STALE_AFTER else "candidate"
        result = {
            "status": status,
            "as_of": as_of,
            "peer_count": len(normalized_peers),
            "user_confirmed": False,
        }
    return result


def _missing_peer_evidence() -> dict[str, object]:
    return {"status": "missing", "peer_count": 0, "user_confirmed": False}


def _canonical_peer_evidence(value: object, created_at: datetime) -> dict[str, object]:
    if not isinstance(value, dict):
        return _missing_peer_evidence()
    status = value.get("status")
    peer_count = value.get("peer_count")
    if status == "missing" and peer_count == 0 and value.get("user_confirmed") is False:
        return _missing_peer_evidence()
    as_of = _timestamp(value.get("as_of"))
    if (
        status not in {"candidate", "stale_candidate"}
        or not isinstance(peer_count, int)
        or isinstance(peer_count, bool)
        or not 1 <= peer_count <= 3
        or value.get("user_confirmed") is not False
        or as_of is None
    ):
        return _missing_peer_evidence()
    observed_at = datetime.fromisoformat(as_of)
    if observed_at > created_at + timedelta(days=1):
        return _missing_peer_evidence()
    canonical_status = "stale_candidate" if created_at - observed_at > _PEER_STALE_AFTER else "candidate"
    return {
        "status": canonical_status,
        "as_of": as_of,
        "peer_count": peer_count,
        "user_confirmed": False,
    }


def _canonical_domain(
    stock: dict[str, object],
    facts: list[dict[str, object]],
    registry: list[dict[str, object]],
    confirmed_case: bool,
    peer_evidence: dict[str, object],
    market: str,
    market_status: str | None = None,
) -> dict[str, object]:
    values = {str(fact["metric"]): float(fact["value"]) for fact in facts}
    fact_refs = {str(fact["metric"]): str(fact["id"]) for fact in facts}
    currency = _infer_currency(facts, market)
    calculations = _calculate(values, fact_refs, currency)
    gaps = _data_gap_codes(values, calculations, registry, confirmed_case, peer_evidence)
    scores = _score_frames(stock, values, calculations, gaps, fact_refs, market_status, peer_evidence)
    bridge = _build_bridge(values, calculations, scores, gaps, currency, fact_refs, market_status, peer_evidence)
    return {"values": values, "currency": currency, "calculations": calculations, "gap_codes": gaps, "scores": scores, "bridge": bridge, "selected": _select_frames(bridge["frame_fit_ranking"])}


def _reason_codes(gaps: list[str], coverage: dict[str, object], stock: dict[str, object], identity_codes: list[str] | tuple[str, ...] = ()) -> list[str]:
    profile_code = "no_canonical_scoring_signal" if stock.get("profile_present") else "missing_stock_profile"
    return sorted(set([
        *gaps,
        *identity_codes,
        *( [] if coverage.get("official_source_count") else ["missing_official_source"]),
        *( [] if stock.get("scoring_signals") else [profile_code]),
        *( ["stale_market_data"] if coverage.get("stale_fields") else []),
    ]))


def _source_state(coverage: dict[str, object]) -> str:
    missing = set(_codes(coverage.get("missing_categories"), set(_MISSING_CATEGORIES)))
    if missing == {"market_data", "official_financial_facts"}:
        return "both_missing"
    if "official_financial_facts" in missing:
        return "financial_missing"
    if "market_data" in missing:
        return "market_missing"
    if coverage.get("stale_fields"):
        return "stale"
    return "complete"


def _degraded_state(reason_codes: list[str], gap_codes: list[str], coverage: dict[str, object]) -> dict[str, object]:
    return {
        "degraded": bool(reason_codes),
        "reason_codes": reason_codes,
        "gap_codes": gap_codes,
        "source_state": _source_state(coverage),
        "missing_categories": list(coverage.get("missing_categories", [])),
        "attempted_source_families": list(coverage.get("attempted_source_families", [])),
        "stale_fields": list(coverage.get("stale_fields", [])),
    }


def _write_packet(packet: dict[str, object], output_dir: Path, symbol: str, market: str, instant: datetime) -> Path:
    directory = output_dir / "valuation"; directory.mkdir(parents=True, exist_ok=True)
    timestamped = directory / f"{symbol}_{market}_valuation_{instant.strftime('%Y%m%dT%H%M%SZ')}.json"
    latest = directory / f"{symbol}_{market}_valuation_latest.json"
    serialized = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if len(serialized.encode("utf-8")) > _MAX_ARTIFACT_BYTES:
        raise ValueError("valuation artifact exceeds byte limit")
    lock = _stock_write_lock(directory, symbol, market)
    with lock:
        with _interprocess_stock_write_lock(directory, symbol, market):
            if timestamped.is_file():
                try:
                    existing = timestamped.read_text(encoding="utf-8")
                except OSError as exc:
                    raise FileExistsError("valuation artifact timestamp collision") from exc
                if existing != serialized:
                    raise FileExistsError("valuation artifact timestamp collision")

            timestamp_temp: Path | None = None
            latest_temp: Path | None = None
            try:
                timestamp_temp = _validated_packet_temp(
                    directory, timestamped.name, serialized, symbol=symbol, market=market,
                )
                latest_temp = _validated_packet_temp(
                    directory, latest.name, serialized, symbol=symbol, market=market,
                )
                os.replace(timestamp_temp, timestamped)
                os.replace(latest_temp, latest)
                _fsync_directory(directory)
            finally:
                if timestamp_temp is not None:
                    timestamp_temp.unlink(missing_ok=True)
                if latest_temp is not None:
                    latest_temp.unlink(missing_ok=True)
    return timestamped


def _stock_write_lock(directory: Path, symbol: str, market: str) -> threading.Lock:
    key = f"{directory.resolve()}\0{market}\0{symbol}".encode("utf-8")
    index = int.from_bytes(hashlib.sha256(key).digest()[:2], "big") % len(_STOCK_WRITE_LOCKS)
    return _STOCK_WRITE_LOCKS[index]


@contextmanager
def _interprocess_stock_write_lock(directory: Path, symbol: str, market: str):
    lock_path = directory / f".{symbol}_{market}_valuation.lock"
    flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _validated_packet_temp(
    directory: Path,
    destination_name: str,
    serialized: str,
    *,
    symbol: str,
    market: str,
) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        dir=directory,
        prefix=f".{destination_name}.",
        suffix=".tmp",
        text=True,
    )
    temp_path = Path(raw_path)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        with temp_path.open("r", encoding="utf-8") as handle:
            candidate = json.load(
                handle,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
            )
        if not isinstance(candidate, dict) or not _valid_packet(candidate, symbol, market):
            raise ValueError("temporary valuation packet failed validation")
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


# Shared typed public projection ------------------------------------------

def _checked_public_projection(packet: dict[str, object]) -> dict[str, object]:
    try:
        _ensure_bounded_json_tree(packet)
        return _public_projection(packet)
    except (OverflowError, RecursionError, TypeError, ValueError) as exc:
        raise ValueError("valuation packet contains unsupported nested values") from exc


def _public_projection(packet: dict[str, object]) -> dict[str, object]:
    input_data = _project_input(packet.get("input")); symbol, market = str(input_data.get("symbol") or ""), str(input_data.get("market") or "")
    has_input_identity = bool(symbol and market)
    stock_mismatch = has_input_identity and _public_stock_mismatch(packet.get("stock"), symbol, market)
    target_mismatch = has_input_identity and _public_target_mismatch(packet.get("target_resolution"), symbol, market)
    identity_mismatch = not has_input_identity or stock_mismatch or target_mismatch
    raw_coverage = {} if identity_mismatch else packet.get("source_coverage")
    registry = _project_registry(raw_coverage); registry_by_id = {str(item["id"]): item for item in registry}
    facts = _project_facts(packet.get("facts"), registry_by_id)
    internal_stock = _project_stock(packet.get("stock"), symbol, market) if has_input_identity and not stock_mismatch else ({"symbol": symbol, "market": market} if has_input_identity else {})
    raw_assumptions = packet.get("assumptions") if isinstance(packet.get("assumptions"), dict) else {}
    confirmed = False
    created_at = _datetime_from_timestamp(input_data.get("created_at")) or datetime.fromtimestamp(0, timezone.utc)
    peer_evidence = (
        _missing_peer_evidence()
        if identity_mismatch
        else _canonical_peer_evidence(raw_assumptions.get("peer_evidence"), created_at)
    )
    coverage = _project_coverage(raw_coverage, facts, registry, created_at)
    domain = _canonical_domain(
        internal_stock,
        facts,
        registry,
        confirmed,
        peer_evidence,
        market,
        _status(coverage.get("market_snapshot_status")),
    )
    allowed = _allowed_refs({str(item["id"]) for item in facts}, internal_stock)
    calculations = _matching_records(packet.get("deterministic_calculations"), domain["calculations"], "metric", ("value", "raw_value", "meaningful", "meaningfulness_reason", "formula", "inputs", "input_refs", "currency"), allowed)
    scores = _matching_records(packet.get("internal_frame_scores"), domain["scores"], "id", ("score", "input_refs"), allowed)
    selected = _matching_records(packet.get("selected_frames"), domain["selected"], "id", ("score", "input_refs", "fit_to_current_market_value", "confidence"), allowed)[:3]
    raw_bridge = packet.get("market_implied_bridge") if isinstance(packet.get("market_implied_bridge"), dict) else {}
    bridge_lines = _matching_records(raw_bridge.get("bridge_lines"), domain["bridge"]["bridge_lines"], "type", ("input_refs",), allowed)
    ranking = _matching_records(raw_bridge.get("frame_fit_ranking"), domain["bridge"]["frame_fit_ranking"], "id", ("score", "input_refs", "fit_to_current_market_value", "confidence"), allowed)
    identity_codes = _codes((packet.get("degraded_state") or {}).get("reason_codes") if isinstance(packet.get("degraded_state"), dict) else None, {"context_identity_mismatch", "snapshot_identity_mismatch"})
    if stock_mismatch: identity_codes.append("context_identity_mismatch")
    if target_mismatch: identity_codes.append("snapshot_identity_mismatch")
    reasons = _reason_codes(domain["gap_codes"], coverage, internal_stock, identity_codes)
    public_selected = [_public_frame(item) for item in selected]
    assumptions = _assumptions(confirmed, peer_evidence, public_selected)
    degraded = {
        **_degraded_state(reasons, list(domain["gap_codes"]), coverage),
        "reasons": [_REASON_COPY[code] for code in reasons],
        "data_gaps": [_GAP_COPY[code] for code in domain["gap_codes"]],
    }
    currency = domain["currency"]
    raw_target = packet.get("target_resolution") if isinstance(packet.get("target_resolution"), dict) else {}
    mapping = None if identity_mismatch else _enum(raw_target.get("mapping_category"), frozenset(_MAPPING_MAP.values()))
    target = _target_resolution(symbol, market, currency, mapping) if symbol and market else ({"currency": currency} if currency else {})
    public_stock = {key: internal_stock[key] for key in ("symbol", "market", "profile_present", "scoring_signals") if key in internal_stock}
    return {"schema": "stock_valuation_evidence.v1", "input": input_data, "stock": public_stock, "target": target, "facts": facts, "assumptions": assumptions, "deterministic_calculations": calculations, "internal_frame_scores": [_public_frame(item) for item in scores], "selected_frames": public_selected, "market_implied_bridge": {"bridge_lines": bridge_lines, "frame_fit_ranking": [_public_frame(item) for item in ranking]}, "interpretation": _interpretation(public_selected, list(domain["gap_codes"])), "watch_items": _watch_items(public_selected), "source_coverage": coverage, "degraded_state": degraded, "safety": _project_safety()}


def _public_stock_mismatch(value: object, symbol: str, market: str) -> bool:
    raw = value if isinstance(value, dict) else {}
    return _optional_target(raw.get("symbol")) != symbol or _optional_target(raw.get("market")) != market


def _public_target_mismatch(value: object, symbol: str, market: str) -> bool:
    raw = value if isinstance(value, dict) else {}
    return bool(
        _optional_target(raw.get("normalized_symbol")) != symbol
        or _optional_target(raw.get("normalized_market")) != market
        or _qualified_target(raw.get("normalized_target")) != (market, symbol)
        or _qualified_target(raw.get("input_target")) != (market, symbol)
    )


def _project_input(value: object) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}; result: dict[str, object] = {}
    if normalized := _optional_target(raw.get("symbol")): result["symbol"] = normalized
    if normalized := _optional_target(raw.get("market")): result["market"] = normalized
    if normalized := _timestamp(raw.get("created_at")): result["created_at"] = normalized
    return result


def _project_stock(value: object, symbol: str, market: str) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}; result: dict[str, object] = {"symbol": symbol, "market": market}
    if isinstance(raw.get("id"), int) and not isinstance(raw["id"], bool) and raw["id"] >= 0: result["id"] = raw["id"]
    if raw.get("profile_present") is True: result["profile_present"] = True
    raw_signals = raw.get("scoring_signals"); signals: dict[str, list[str]] = {}
    if isinstance(raw_signals, dict):
        for field in ("core_business", "stock_character"):
            candidates = raw_signals.get(field)
            if isinstance(candidates, list) and (normalized := sorted(set(item for item in candidates if _enum(item, frozenset(_FRAME_WORDS))))): signals[field] = normalized
    if signals: result["scoring_signals"] = signals
    return result


def _project_registry(value: object) -> list[dict[str, object]]:
    coverage = value if isinstance(value, dict) else {}; records = coverage.get("source_registry")
    if not isinstance(records, (list, tuple)): return []
    result: dict[str, dict[str, object]] = {}
    canonical_pairs = set(_SOURCE_TYPE_MAP.values()) | {("unknown", "unknown")}
    for raw in records:
        pair = (_enum(raw.get("source_type"), frozenset(item[0] for item in canonical_pairs)), _enum(raw.get("family"), _SOURCE_FAMILIES)) if isinstance(raw, dict) else (None, None)
        if pair not in canonical_pairs: continue
        descriptor = {"family": pair[1], "source_type": pair[0]}; expected_id = _source_id(descriptor)
        if provider := _enum(raw.get("provider_category"), frozenset(_PROVIDER_MAP.values())): descriptor["provider_category"] = provider; expected_id = _source_id(descriptor)
        if raw.get("id") != expected_id: continue
        result[expected_id] = {"id": expected_id, **descriptor}
    return [result[key] for key in sorted(result)]


def _project_facts(value: object, registry: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)): return []
    result: dict[str, dict[str, object]] = {}
    for raw in value:
        if not isinstance(raw, dict) or not (metric := _enum(raw.get("metric"), _FACT_METRICS)) or (number := _finite(raw.get("value"))) is None or not isinstance(raw.get("source_id"), str) or raw["source_id"] not in registry: continue
        source, kind = registry[raw["source_id"]], _fact_kind(metric); normalized_currency = _currency(raw.get("currency"))
        item: dict[str, object] = {"id": f"fact:{metric}", "metric": metric, "value": number, "source_id": source["id"], "source_type": source["source_type"], "source_family": source["family"], "display_kind": kind, "display_value": _format(number, kind, normalized_currency)}
        if source.get("provider_category"): item["provider_category"] = source["provider_category"]
        if kind.startswith("currency") and normalized_currency: item["currency"] = normalized_currency
        if normalized := _period(raw.get("period_end")): item["period_end"] = normalized
        if normalized := _timestamp(raw.get("timestamp")): item["timestamp"] = normalized
        if normalized := _timestamp(raw.get("fetched_at")): item["fetched_at"] = normalized
        if normalized := _enum(raw.get("freshness"), _FRESHNESS_LABELS): item["freshness"] = normalized
        result[metric] = item
    return [result[key] for key in sorted(result)]


def _allowed_refs(fact_ids: set[str], stock: dict[str, object]) -> set[str]:
    refs = {*fact_ids, *(f"packet:method_library:{frame_id}" for frame_id in _CORE_BY_ID)}
    signals = stock.get("scoring_signals") if isinstance(stock.get("scoring_signals"), dict) else {}
    refs.update(f"packet:stock:scoring_signals:{field}:{frame_id}" for field, frame_ids in signals.items() if isinstance(frame_ids, list) for frame_id in frame_ids)
    return refs


def _matching_records(value: object, expected: object, key: str, fields: tuple[str, ...], allowed_refs: set[str]) -> list[dict[str, object]]:
    raw_records = value if isinstance(value, (list, tuple)) else []; expected_records = expected if isinstance(expected, (list, tuple)) else []
    raw_by_key = {item[key]: item for item in raw_records if isinstance(item, dict) and isinstance(item.get(key), str)}
    return [_plain(item) for item in expected_records if isinstance(item, dict) and isinstance(item.get("input_refs"), (list, tuple)) and bool(item["input_refs"]) and set(item["input_refs"]) <= allowed_refs and isinstance((raw := raw_by_key.get(item.get(key))), dict) and all(_plain(raw.get(field)) == _plain(item.get(field)) for field in fields)]


def _public_frame(item: dict[str, object]) -> dict[str, object]:
    result = dict(item)
    result["degraded_by"] = [_GAP_COPY[code] for code in _codes(item.get("degraded_by"), set(_GAP_COPY))]
    if "main_data_gaps" in item: result["main_data_gaps"] = [_GAP_COPY[code] for code in _codes(item.get("main_data_gaps"), set(_GAP_COPY))]
    return result


def _project_coverage(
    value: object,
    facts: list[dict[str, object]],
    registry: list[dict[str, object]],
    created_at: datetime,
) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}
    projected_input = {
        "market_snapshot_status": _status(raw.get("market_snapshot_status")) or "unknown",
        "financial_fact_status": _status(raw.get("financial_fact_status")) or "unknown",
        "source_attempts": _attempts(raw.get("source_attempts")),
    }
    result = _coverage(facts, registry, projected_input, created_at)
    raw_statuses = raw.get("provider_statuses")
    projected_statuses: dict[str, dict[str, str]] = {}
    if isinstance(raw_statuses, dict):
        for name in ("market_snapshot", "financial_facts"):
            record = raw_statuses.get(name)
            normalized = _status(record.get("status")) if isinstance(record, dict) else None
            if normalized:
                projected_statuses[name] = {"status": normalized}
    result["provider_statuses"] = projected_statuses
    return result


def _codes(value: object, allowed: set[str]) -> list[str]:
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item in allowed)) if isinstance(value, (list, tuple)) else []


def _project_safety() -> dict[str, object]:
    return {"direct_investment_advice": False, "writes_formal_user_insight": False, "research_aid_only": True, "omits_local_path": True, "provider_error_detail_omitted": True}


# Strict internal packet validation ---------------------------------------

def _ensure_bounded_json_tree(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0
    containers = 0
    text_bytes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            raise ValueError("JSON shape exceeds valuation artifact limits")
        if current is None or isinstance(current, bool):
            continue
        if isinstance(current, str):
            text_bytes += len(current.encode("utf-8"))
            if text_bytes > _MAX_ARTIFACT_BYTES:
                raise ValueError("JSON text exceeds valuation artifact limits")
            continue
        if isinstance(current, int):
            if current.bit_length() > 4096:
                raise ValueError("integer exceeds valuation artifact limits")
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise ValueError("non-finite number is not supported")
            continue
        if not isinstance(current, (dict, list, tuple)):
            raise TypeError("valuation packet must contain JSON-compatible values")
        containers += 1
        if containers > _MAX_JSON_CONTAINERS:
            raise ValueError("JSON container count exceeds valuation artifact limits")
        if isinstance(current, dict):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise TypeError("valuation packet keys must be strings")
                text_bytes += len(key.encode("utf-8"))
                if text_bytes > _MAX_ARTIFACT_BYTES:
                    raise ValueError("JSON text exceeds valuation artifact limits")
                stack.append((item, depth + 1))
        else:
            stack.extend((item, depth + 1) for item in current)


def _plain(value: object) -> object:
    _ensure_bounded_json_tree(value)
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except RecursionError as exc:
        raise ValueError("valuation packet contains unsupported nested values") from exc


def _valid_packet(packet: dict[str, object], symbol: str, market: str) -> bool:
    if set(packet) != _PACKET_KEYS or packet.get("schema") != "stock_valuation_packet.v1": return False
    try: plain = _plain(packet)
    except (RecursionError, TypeError, ValueError, json.JSONDecodeError): return False
    assert isinstance(plain, dict)
    input_data, stock = plain.get("input"), plain.get("stock")
    if not isinstance(input_data, dict) or set(input_data) != {"symbol", "market", "command", "created_at"}: return False
    if input_data != {"symbol": symbol, "market": market, "command": f"valuation {market}.{symbol}", "created_at": _timestamp(input_data.get("created_at"))}: return False
    if not isinstance(stock, dict) or _project_stock(stock, symbol, market) != stock: return False
    coverage = plain.get("source_coverage"); registry = _project_registry(coverage)
    if not isinstance(coverage, dict) or registry != coverage.get("source_registry"): return False
    registry_by_id = {str(item["id"]): item for item in registry}; facts = _project_facts(plain.get("facts"), registry_by_id)
    if facts != plain.get("facts"): return False
    raw_assumptions = plain.get("assumptions")
    if not isinstance(raw_assumptions, dict) or not isinstance(raw_assumptions.get("user_confirmed_valuation_case"), bool): return False
    if raw_assumptions.get("user_confirmed_valuation_case") is not False: return False
    created_at = _datetime_from_timestamp(input_data.get("created_at"))
    if created_at is None: return False
    peer_evidence = _canonical_peer_evidence(raw_assumptions.get("peer_evidence"), created_at)
    expected_coverage = _coverage(facts, registry, coverage, created_at)
    if coverage != _plain(expected_coverage): return False
    domain = _canonical_domain(
        stock,
        facts,
        registry,
        False,
        peer_evidence,
        market,
        _status(coverage.get("market_snapshot_status")),
    )
    assumptions = _assumptions(False, peer_evidence, domain["selected"])
    if assumptions != plain.get("assumptions"): return False
    raw_target = plain.get("target_resolution"); mapping = _enum(raw_target.get("mapping_category"), frozenset(_MAPPING_MAP.values())) if isinstance(raw_target, dict) else None
    if raw_target != _target_resolution(symbol, market, domain["currency"], mapping): return False
    for key, expected in (("deterministic_calculations", domain["calculations"]), ("internal_frame_scores", domain["scores"]), ("market_implied_bridge", domain["bridge"]), ("selected_frames", domain["selected"])):
        if plain.get(key) != _plain(expected): return False
    selected = plain["selected_frames"]
    if not isinstance(selected, list) or not 1 <= len(selected) <= 3 or len(plain["internal_frame_scores"]) != 5: return False
    degraded = plain.get("degraded_state"); identity_codes = _codes(degraded.get("reason_codes") if isinstance(degraded, dict) else None, {"context_identity_mismatch", "snapshot_identity_mismatch"})
    reasons = _reason_codes(domain["gap_codes"], expected_coverage, stock, identity_codes)
    if degraded != _degraded_state(reasons, domain["gap_codes"], expected_coverage): return False
    if plain.get("interpretation") != _interpretation(selected, domain["gap_codes"]) or plain.get("watch_items") != _watch_items(selected): return False
    return plain.get("safety") == {"direct_investment_advice": False, "writes_formal_user_insight": False, "research_aid_only": True}
