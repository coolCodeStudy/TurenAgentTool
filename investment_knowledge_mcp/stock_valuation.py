"""Deterministic stock-valuation artifacts with one typed trust boundary."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


CORE_FRAMES: tuple[dict[str, Any], ...] = (
    {"id": "fcf", "name": "Free Cash Flow", "core_question": "What durable free cash flow can the business produce?", "triggers": ("FCF turns positive", "cash conversion improves"), "failure_conditions": ("one-time cash release", "higher reinvestment")},
    {"id": "comparable_multiples", "name": "Comparable Multiples", "core_question": "Which multiple can comparable businesses support?", "triggers": ("quality improves", "peer multiple expands"), "failure_conditions": ("wrong peer group", "unsupported multiple expansion")},
    {"id": "sotp_asset_value", "name": "SOTP / Asset Value", "core_question": "Are parts or assets worth more than the consolidated value?", "triggers": ("asset sale", "better segment disclosure"), "failure_conditions": ("assets cannot be monetized", "holding discount persists")},
    {"id": "cyclical", "name": "Cyclical", "core_question": "Are earnings at a cycle peak, trough, or mid-cycle?", "triggers": ("pricing inflects", "inventory clears"), "failure_conditions": ("peak earnings treated as durable", "supply response")},
    {"id": "growth_scenario", "name": "Growth / Scenario", "core_question": "What is the value under explicit growth and milestone scenarios?", "triggers": ("TAM rises", "milestone validates demand"), "failure_conditions": ("TAM overstated", "milestone delayed")},
)
SPECIALIST_FRAMES: tuple[dict[str, Any], ...] = (
    {"id": "dividend", "name": "Dividend", "core_question": "Can distributable cash flows sustain dividends?", "specialist_only": True},
    {"id": "residual_income", "name": "Residual Income", "core_question": "Does return on equity exceed the cost of equity?", "specialist_only": True},
    {"id": "event_driven", "name": "Event-Driven", "core_question": "Does a defined corporate event change value realization?", "specialist_only": True},
)

_PACKET_KEYS = frozenset({"schema", "input", "stock", "target_resolution", "facts", "assumptions", "deterministic_calculations", "internal_frame_scores", "selected_frames", "market_implied_bridge", "interpretation", "watch_items", "source_coverage", "degraded_state", "safety"})
_SAFE_TARGET = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_SAFE_SOURCE_ID = re.compile(r"^source:[0-9a-f]{16}$")
_SAFE_PERIOD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FACT_METRICS = frozenset({"revenue", "gross_profit", "operating_income", "net_income", "operating_cash_flow", "capex", "free_cash_flow", "cash", "debt", "net_debt", "shares_outstanding", "price", "market_cap", "enterprise_value", "ebitda", "book_value"})
_MONEY_METRICS = _FACT_METRICS - {"shares_outstanding", "price"}
_SOURCE_FAMILIES = frozenset({"company_ir", "market_snapshot", "official_financial", "regulator_filing", "unknown", "vendor_financial"})
_SOURCE_STATUSES = frozenset({"available", "attempted", "complete_missing", "failed", "failure", "missing", "not_attempted", "partial", "present", "stale", "success", "unavailable", "unknown"})
_FRAME_FITS = frozenset({"fits", "partial_fit", "insufficient_data", "does_not_fit"})
_CONFIDENCE = frozenset({"low", "medium", "high"})
_BRIDGE_TYPES = frozenset({"sales_anchor", "ev_sales_anchor", "fcf_yield"})
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
_GAP_COPY = {
    "missing_market_data": "latest market price or market cap is missing",
    "missing_enterprise_value": "enterprise value cannot be derived without market cap and net debt",
    "missing_revenue": "revenue is missing",
    "missing_fcf": "free cash flow is missing",
    "missing_net_income": "net income is missing",
    "missing_source_metadata": "source metadata is missing",
    "missing_confirmed_case": "no user-confirmed valuation case",
}
_REASON_COPY = {
    **_GAP_COPY,
    "context_identity_mismatch": "context stock identity mismatched the explicit target and was omitted",
    "snapshot_identity_mismatch": "provider snapshot identity mismatched the explicit target and was omitted",
    "missing_official_source": "official financial source coverage is missing",
    "minimal_stock_profile": "stock profile appears minimal and needs research import",
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
    domain = _canonical_domain(stock, facts, registry, _confirmed_case(safe_context), market)
    calculations, gap_codes = domain["calculations"], domain["gap_codes"]
    identity_codes = []
    if context_mismatch:
        identity_codes.append("context_identity_mismatch")
    if snapshot_mismatch:
        identity_codes.append("snapshot_identity_mismatch")
    scores, bridge, selected = domain["scores"], domain["bridge"], domain["selected"]
    coverage = _coverage(facts, registry, safe_snapshot)
    reason_codes = _reason_codes(gap_codes, coverage, stock, identity_codes)
    packet: dict[str, object] = {
        "schema": "stock_valuation_packet.v1",
        "input": {"symbol": symbol, "market": market, "command": f"valuation {market}.{symbol}", "created_at": instant.isoformat()},
        "stock": stock,
        "target_resolution": _target_resolution(symbol, market, currency),
        "facts": facts,
        "assumptions": {"user_confirmed_valuation_case": _confirmed_case(safe_context), "items": list(_ASSUMPTIONS)},
        "deterministic_calculations": calculations,
        "internal_frame_scores": scores,
        "selected_frames": selected,
        "market_implied_bridge": bridge,
        "interpretation": _interpretation(selected, gap_codes),
        "watch_items": _watch_items(selected),
        "source_coverage": coverage,
        "degraded_state": {"degraded": bool(reason_codes), "reason_codes": reason_codes, "gap_codes": gap_codes},
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
        packet = json.loads(path.read_text(encoding="utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return packet if isinstance(packet, dict) and _valid_packet(packet, symbol, market) else None


def build_valuation_artifact_evidence(packet: dict[str, object]) -> dict[str, object]:
    """Return the shared typed public projection; never read an artifact path."""
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    return _public_projection(packet)


def render_valuation_card(packet: dict[str, object]) -> str:
    """Render only the shared typed public projection."""
    if not isinstance(packet, dict):
        raise TypeError("packet must be a mapping")
    public = _public_projection(packet)
    stock, degraded = public["stock"], public["degraded_state"]
    calculations = {str(item["metric"]): item for item in public["deterministic_calculations"]}
    target = ".".join(str(stock[key]) for key in ("market", "symbol") if stock.get(key))
    lines = [f"Valuation research card: {target}{' ' + str(stock['name']) if stock.get('name') else ''}".rstrip(), f"Status: {'degraded' if degraded.get('degraded') else 'ok'}", "Data gaps:"]
    lines.extend(f"- {gap}" for gap in degraded.get("data_gaps", []))
    if not degraded.get("data_gaps"):
        lines.append("- none identified by the normalized packet")
    lines.append("Valuation snapshot:")
    for label, metric in (("Market cap", "market_cap"), ("Enterprise value", "enterprise_value"), ("FCF margin", "fcf_margin"), ("PE", "pe"), ("P/S", "ps"), ("EV/EBITDA", "ev_ebitda"), ("EV/FCF", "ev_fcf")):
        if metric in calculations:
            lines.append(f"- {label}: {calculations[metric]['display_value']}")
    lines.append("Relevant frames:")
    lines.extend(f"- {frame['name']} (fit={frame.get('fit_to_current_market_value', 'unknown')})" for frame in public["selected_frames"])
    for heading, values in (("Assumptions:", public["assumptions"].get("items", [])), ("Interpretation:", public["interpretation"]), ("Watch items:", public["watch_items"])):
        lines.append(heading); lines.extend(f"- {item}" for item in values)
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
    signals: dict[str, list[str]] = {}
    for field in ("core_business", "stock_character"):
        text = raw.get(field)
        if not isinstance(text, str): continue
        matches = sorted(frame_id for frame_id, words in _FRAME_WORDS.items() if any(word in text.lower() for word in words))
        if matches: signals[field] = matches
    if signals: stock["scoring_signals"] = signals
    return stock, False


def _snapshot_mismatch(snapshot: dict[str, object], symbol: str, market: str) -> bool:
    target = snapshot.get("target_resolution") if isinstance(snapshot.get("target_resolution"), dict) else {}
    if target.get("normalized_symbol") is not None and _optional_target(target.get("normalized_symbol")) != symbol: return True
    if target.get("normalized_market") is not None and _optional_target(target.get("normalized_market")) != market: return True
    candidate_symbol, candidate_market = _optional_target(target.get("normalized_symbol")), _optional_target(target.get("normalized_market"))
    normalized = target.get("normalized_target")
    if normalized is not None and (not isinstance(normalized, str) or "." not in normalized): return True
    if isinstance(normalized, str):
        market_part, symbol_part = normalized.split(".", 1)
        candidate_symbol, candidate_market = candidate_symbol or _optional_target(symbol_part), candidate_market or _optional_target(market_part)
        if candidate_symbol is None or candidate_market is None: return True
    return bool((candidate_symbol not in (None, symbol)) or (candidate_market not in (None, market)))


def _source_descriptor(raw: dict[str, object]) -> dict[str, object]:
    raw_type = raw.get("source_type")
    source_type, family = _SOURCE_TYPE_MAP.get(raw_type.strip().lower(), ("unknown", "unknown")) if isinstance(raw_type, str) else ("unknown", "unknown")
    return {"family": family, "source_type": source_type}


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
            if not isinstance(raw, dict) or raw.get("metric") not in _FACT_METRICS or (number := _finite(raw.get("value"))) is None: continue
            metric, descriptor = str(raw["metric"]), _source_descriptor(raw)
            source_id = _source_id(descriptor); registry[source_id] = {"id": source_id, **descriptor}
            fact: dict[str, object] = {"id": f"fact:{metric}", "metric": metric, "value": number, "source_id": source_id, "source_type": descriptor["source_type"], "source_family": descriptor["family"]}
            if normalized := _currency(raw.get("currency")): fact["currency"] = normalized
            if normalized := _period(raw.get("period_end")): fact["period_end"] = normalized
            if normalized := _timestamp(raw.get("timestamp")): fact["timestamp"] = normalized
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

def _format(value: float, kind: str, currency: str | None) -> str:
    if kind == "percent": return f"{value * 100:.1f}%"
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
        else: item["display_value"] = _format(value, kind, currency)
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
        if numerator is None or denominator in (None, 0): continue
        formula, inputs, kind, configured_reason = _CALC_SPECS[metric]
        reason = configured_reason if configured_reason and (denominator < 0 or (metric == "fcf_yield" and numerator < 0)) else None
        add(metric, numerator / denominator, formula, inputs, kind, reason)
    return result


def _data_gap_codes(values: dict[str, float], calculations: list[dict[str, object]], registry: list[dict[str, object]], confirmed_case: bool) -> list[str]:
    derived, gaps = {str(item["metric"]) for item in calculations}, []
    if "price" not in values and "market_cap" not in values: gaps.append("missing_market_data")
    if "enterprise_value" not in values and "enterprise_value" not in derived: gaps.append("missing_enterprise_value")
    for metric in ("revenue", "free_cash_flow", "net_income"):
        if metric not in values and metric not in derived: gaps.append(f"missing_{metric.replace('free_cash_flow', 'fcf')}")
    if not any(item.get("source_type") != "unknown" for item in registry): gaps.append("missing_source_metadata")
    if not confirmed_case: gaps.append("missing_confirmed_case")
    return gaps


def _frame_supported(frame_id: str, values: dict[str, float], calculations: list[dict[str, object]]) -> bool:
    calculated = {str(item["metric"]): item for item in calculations}
    if frame_id == "fcf": return "free_cash_flow" in values or {"operating_cash_flow", "capex"} <= values.keys()
    if frame_id == "comparable_multiples":
        market_value = values.get("market_cap") if "market_cap" in values else _calculated_value(calculated.get("market_cap"))
        return market_value is not None and any(values.get(metric) not in (None, 0) for metric in ("revenue", "net_income", "ebitda"))
    return True


def _score_frames(stock: dict[str, object], values: dict[str, float], calculations: list[dict[str, object]], gaps: list[str], facts: dict[str, str]) -> list[dict[str, object]]:
    score = {"fcf": .15, "comparable_multiples": .2, "sotp_asset_value": .05, "cyclical": .05, "growth_scenario": .1}
    if _frame_supported("fcf", values, calculations): score["fcf"] += .55
    if _frame_supported("comparable_multiples", values, calculations): score["comparable_multiples"] += .45
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
        result.append({"id": frame_id, "name": _CORE_BY_ID[frame_id]["name"], "score": round(min(value, 1), 3), "reason": "ranked from normalized facts and declared stock fields", "input_refs": tuple(dict.fromkeys(refs)), "degraded_by": [gap for gap in gaps if frame_id.split("_")[0] in gap]})
    return result


def _calculated_value(item: dict[str, object] | None) -> float | None:
    if not item: return None
    return _finite(item.get("value")) if _finite(item.get("value")) is not None else _finite(item.get("raw_value"))


def _build_bridge(values: dict[str, float], calculations: list[dict[str, object]], scores: list[dict[str, object]], gaps: list[str], currency: str | None, facts: dict[str, str]) -> dict[str, object]:
    derived = {str(item["metric"]): item for item in calculations}
    market_cap = values.get("market_cap") if values.get("market_cap") is not None else _calculated_value(derived.get("market_cap"))
    enterprise_value = values.get("enterprise_value") if values.get("enterprise_value") is not None else _calculated_value(derived.get("enterprise_value"))
    fcf = values.get("free_cash_flow") if values.get("free_cash_flow") is not None else _calculated_value(derived.get("free_cash_flow"))
    revenue, lines = values.get("revenue"), []
    def add(kind: str, display: str, inputs: tuple[str, ...]) -> None: lines.append({"type": kind, "display": display, "input_refs": _flatten_refs(inputs, facts, derived)})
    if market_cap is not None and revenue not in (None, 0): add("sales_anchor", f"P/S: {_format(market_cap / revenue, 'multiple', currency)} anchors current market value.", ("market_cap", "revenue"))
    if enterprise_value is not None and revenue not in (None, 0): add("ev_sales_anchor", f"EV/Sales: {_format(enterprise_value / revenue, 'multiple', currency)}.", ("enterprise_value", "revenue"))
    if fcf is not None and market_cap not in (None, 0): add("fcf_yield", "FCF yield is not meaningful with negative FCF." if fcf < 0 else f"FCF yield: {_format(fcf / market_cap, 'percent', currency)}.", ("free_cash_flow", "market_cap"))
    ranking = []
    for item in scores:
        supported = _frame_supported(str(item["id"]), values, calculations)
        fit = "insufficient_data" if not supported else "fits" if item["score"] >= .6 else "partial_fit" if item["score"] >= .2 else "insufficient_data"
        ranking.append({**item, "fit_to_current_market_value": fit, "why_it_fits_or_not": "ranked using deterministic normalized inputs", "main_data_gaps": list(gaps), "confidence": "low" if gaps or not supported else "medium"})
    return {"bridge_lines": lines, "frame_fit_ranking": ranking}


def _select_frames(ranking: list[dict[str, object]]) -> list[dict[str, object]]:
    order = {"fits": 0, "partial_fit": 1, "insufficient_data": 2, "does_not_fit": 3}
    ranked = sorted(ranking, key=lambda item: (order.get(str(item.get("fit_to_current_market_value")), 4), -float(item.get("score") or 0)))
    return [item for item in ranked if float(item.get("score") or 0) >= .2][:3] or ranked[:1]


def _status(value: object) -> str | None:
    return value if isinstance(value, str) and value in _SOURCE_STATUSES else None


def _attempts(value: object) -> list[dict[str, str]]:
    candidates = [item for _, item in sorted(value.items(), key=lambda pair: str(pair[0]))] if isinstance(value, dict) else value if isinstance(value, list) else []
    return [{"family": item["family"], "status": status} for item in candidates if isinstance(item, dict) and item.get("family") in _SOURCE_FAMILIES and (status := _status(item.get("status")))]


def _coverage(facts: list[dict[str, object]], registry: list[dict[str, object]], snapshot: dict[str, object]) -> dict[str, object]:
    market_present = any(item.get("metric") in {"price", "market_cap"} for item in facts)
    financial_present = any(item.get("metric") in _MONEY_METRICS - {"market_cap", "enterprise_value"} for item in facts)
    return {"fact_count": len(facts), "fact_source_id_count": len({item["source_id"] for item in facts}), "source_count": len(registry), "official_source_count": sum(item.get("family") == "official_financial" for item in registry), "market_snapshot_status": _status(snapshot.get("market_snapshot_status")) or ("present" if market_present else "missing"), "financial_fact_status": _status(snapshot.get("financial_fact_status")) or ("present" if financial_present else "missing"), "provider_statuses": {"market_snapshot": {"status": "available" if market_present else "complete_missing"}, "financial_facts": {"status": "available" if financial_present else "complete_missing"}}, "source_attempts": _attempts(snapshot.get("source_attempts")), "source_registry": registry}


def _interpretation(selected: list[dict[str, object]], gaps: list[str]) -> list[str]:
    items = [f"{_CORE_BY_ID[str(item['id'])]['name']} is a selected research frame." for item in selected if str(item.get("id")) in _CORE_BY_ID]
    if gaps: items.append("Data gaps mean this is research scaffolding rather than a target price.")
    return items


def _watch_items(selected: list[dict[str, object]]) -> list[str]:
    return [f"{_CORE_BY_ID[str(item['id'])]['name']} triggers: {', '.join(_CORE_BY_ID[str(item['id'])]['triggers'])}." for item in selected if str(item.get("id")) in _CORE_BY_ID]


def _target_resolution(symbol: str, market: str, fallback_currency: str | None) -> dict[str, object]:
    result: dict[str, object] = {"input_target": f"{market}.{symbol}", "normalized_target": f"{market}.{symbol}", "normalized_symbol": symbol, "normalized_market": market}
    if fallback_currency: result["currency"] = fallback_currency
    return result


def _infer_currency(facts: list[dict[str, object]], market: str) -> str | None:
    return next((_currency(fact.get("currency")) for fact in facts if _currency(fact.get("currency"))), None) or {"US": "USD", "HK": "HKD", "KR": "KRW"}.get(market)


def _confirmed_case(context: dict[str, object]) -> bool:
    return any(isinstance(item, dict) and item.get("confirmed_by_user") is True for group in ("stock_insights", "stock_knowledge") for item in (context.get(group) if isinstance(context.get(group), list) else []))


def _canonical_domain(stock: dict[str, object], facts: list[dict[str, object]], registry: list[dict[str, object]], confirmed_case: bool, market: str) -> dict[str, object]:
    values = {str(fact["metric"]): float(fact["value"]) for fact in facts}
    fact_refs = {str(fact["metric"]): str(fact["id"]) for fact in facts}
    currency = _infer_currency(facts, market)
    calculations = _calculate(values, fact_refs, currency)
    gaps = _data_gap_codes(values, calculations, registry, confirmed_case)
    scores = _score_frames(stock, values, calculations, gaps, fact_refs)
    bridge = _build_bridge(values, calculations, scores, gaps, currency, fact_refs)
    return {"values": values, "currency": currency, "calculations": calculations, "gap_codes": gaps, "scores": scores, "bridge": bridge, "selected": _select_frames(bridge["frame_fit_ranking"])}


def _reason_codes(gaps: list[str], coverage: dict[str, object], stock: dict[str, object], identity_codes: list[str] | tuple[str, ...] = ()) -> list[str]:
    return sorted(set([*gaps, *identity_codes, *( [] if coverage.get("official_source_count") else ["missing_official_source"]), *( [] if stock.get("scoring_signals") else ["minimal_stock_profile"])]))


def _write_packet(packet: dict[str, object], output_dir: Path, symbol: str, market: str, instant: datetime) -> Path:
    directory = output_dir / "valuation"; directory.mkdir(parents=True, exist_ok=True)
    timestamped = directory / f"{symbol}_{market}_valuation_{instant.strftime('%Y%m%dT%H%M%SZ')}.json"
    latest = directory / f"{symbol}_{market}_valuation_latest.json"
    serialized = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    timestamped.write_text(serialized + "\n", encoding="utf-8"); latest.write_text(serialized + "\n", encoding="utf-8")
    return timestamped


# Shared typed public projection ------------------------------------------

def _public_projection(packet: dict[str, object]) -> dict[str, object]:
    input_data = _project_input(packet.get("input")); symbol, market = str(input_data.get("symbol") or ""), str(input_data.get("market") or "")
    registry = _project_registry(packet.get("source_coverage")); registry_by_id = {str(item["id"]): item for item in registry}
    facts = _project_facts(packet.get("facts"), registry_by_id)
    internal_stock = _project_stock(packet.get("stock"), symbol, market) if symbol and market else {}
    assumptions = _project_assumptions(packet.get("assumptions")); confirmed = assumptions.get("user_confirmed_valuation_case") is True
    domain = _canonical_domain(internal_stock, facts, registry, confirmed, market)
    allowed = _allowed_refs({str(item["id"]) for item in facts}, internal_stock)
    calculations = _matching_records(packet.get("deterministic_calculations"), domain["calculations"], "metric", ("value", "raw_value", "meaningful", "meaningfulness_reason", "formula", "inputs", "input_refs", "currency"), allowed)
    scores = _matching_records(packet.get("internal_frame_scores"), domain["scores"], "id", ("score", "input_refs"), allowed)
    selected = _matching_records(packet.get("selected_frames"), domain["selected"], "id", ("score", "input_refs", "fit_to_current_market_value", "confidence"), allowed)[:3]
    raw_bridge = packet.get("market_implied_bridge") if isinstance(packet.get("market_implied_bridge"), dict) else {}
    bridge_lines = _matching_records(raw_bridge.get("bridge_lines"), domain["bridge"]["bridge_lines"], "type", ("input_refs",), allowed)
    ranking = _matching_records(raw_bridge.get("frame_fit_ranking"), domain["bridge"]["frame_fit_ranking"], "id", ("score", "input_refs", "fit_to_current_market_value", "confidence"), allowed)
    coverage = _project_coverage(packet.get("source_coverage"), facts, registry)
    identity_codes = _codes((packet.get("degraded_state") or {}).get("reason_codes") if isinstance(packet.get("degraded_state"), dict) else None, {"context_identity_mismatch", "snapshot_identity_mismatch"})
    reasons = _reason_codes(domain["gap_codes"], coverage, internal_stock, identity_codes)
    degraded = {"degraded": bool(reasons), "reason_codes": reasons, "gap_codes": list(domain["gap_codes"]), "reasons": [_REASON_COPY[code] for code in reasons], "data_gaps": [_GAP_COPY[code] for code in domain["gap_codes"]]}
    public_selected = [_public_frame(item) for item in selected]
    currency = domain["currency"]
    target = _target_resolution(symbol, market, currency) if symbol and market else ({"currency": currency} if currency else {})
    public_stock = {key: internal_stock[key] for key in ("symbol", "market", "scoring_signals") if key in internal_stock}
    return {"schema": "stock_valuation_evidence.v1", "input": input_data, "stock": public_stock, "target": target, "facts": facts, "assumptions": assumptions, "deterministic_calculations": calculations, "internal_frame_scores": [_public_frame(item) for item in scores], "selected_frames": public_selected, "market_implied_bridge": {"bridge_lines": bridge_lines, "frame_fit_ranking": [_public_frame(item) for item in ranking]}, "interpretation": _interpretation(public_selected, list(domain["gap_codes"])), "watch_items": _watch_items(public_selected), "source_coverage": coverage, "degraded_state": degraded, "safety": _project_safety()}


def _project_input(value: object) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}; result: dict[str, object] = {}
    if normalized := _optional_target(raw.get("symbol")): result["symbol"] = normalized
    if normalized := _optional_target(raw.get("market")): result["market"] = normalized
    if normalized := _timestamp(raw.get("created_at")): result["created_at"] = normalized
    return result


def _project_stock(value: object, symbol: str, market: str) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}; result: dict[str, object] = {"symbol": symbol, "market": market}
    if isinstance(raw.get("id"), int) and not isinstance(raw["id"], bool) and raw["id"] >= 0: result["id"] = raw["id"]
    raw_signals = raw.get("scoring_signals"); signals: dict[str, list[str]] = {}
    if isinstance(raw_signals, dict):
        for field in ("core_business", "stock_character"):
            candidates = raw_signals.get(field)
            if isinstance(candidates, list) and (normalized := sorted(set(item for item in candidates if item in _FRAME_WORDS))): signals[field] = normalized
    if signals: result["scoring_signals"] = signals
    return result


def _project_registry(value: object) -> list[dict[str, object]]:
    coverage = value if isinstance(value, dict) else {}; records = coverage.get("source_registry")
    if not isinstance(records, (list, tuple)): return []
    result: dict[str, dict[str, object]] = {}
    canonical_pairs = set(_SOURCE_TYPE_MAP.values()) | {("unknown", "unknown")}
    for raw in records:
        pair = (raw.get("source_type"), raw.get("family")) if isinstance(raw, dict) else (None, None)
        if pair not in canonical_pairs: continue
        descriptor = {"family": pair[1], "source_type": pair[0]}; expected_id = _source_id(descriptor)
        if raw.get("id") != expected_id: continue
        result[expected_id] = {"id": expected_id, **descriptor}
    return [result[key] for key in sorted(result)]


def _project_facts(value: object, registry: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)): return []
    result: dict[str, dict[str, object]] = {}
    for raw in value:
        if not isinstance(raw, dict) or raw.get("metric") not in _FACT_METRICS or (number := _finite(raw.get("value"))) is None or raw.get("source_id") not in registry: continue
        metric, source, kind = str(raw["metric"]), registry[str(raw["source_id"])], _fact_kind(str(raw["metric"])); normalized_currency = _currency(raw.get("currency"))
        item: dict[str, object] = {"id": f"fact:{metric}", "metric": metric, "value": number, "source_id": source["id"], "source_type": source["source_type"], "source_family": source["family"], "display_kind": kind, "display_value": _format(number, kind, normalized_currency)}
        if kind.startswith("currency") and normalized_currency: item["currency"] = normalized_currency
        if normalized := _period(raw.get("period_end")): item["period_end"] = normalized
        if normalized := _timestamp(raw.get("timestamp")): item["timestamp"] = normalized
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


def _project_assumptions(value: object) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}
    return {"user_confirmed_valuation_case": raw.get("user_confirmed_valuation_case") is True, "items": list(_ASSUMPTIONS)}


def _project_coverage(value: object, facts: list[dict[str, object]], registry: list[dict[str, object]]) -> dict[str, object]:
    raw = value if isinstance(value, dict) else {}; result: dict[str, object] = {"fact_count": len(facts), "fact_source_id_count": len({item["source_id"] for item in facts}), "source_count": len(registry), "official_source_count": sum(item.get("family") == "official_financial" for item in registry), "source_registry": registry}
    for key in ("market_snapshot_status", "financial_fact_status"):
        if normalized := _status(raw.get(key)): result[key] = normalized
    statuses = raw.get("provider_statuses"); projected_statuses = {}
    if isinstance(statuses, dict):
        for name in ("market_snapshot", "financial_facts"):
            record = statuses.get(name); normalized = _status(record.get("status")) if isinstance(record, dict) else None
            if normalized: projected_statuses[name] = {"status": normalized}
    result.update({"provider_statuses": projected_statuses, "source_attempts": _attempts(raw.get("source_attempts"))})
    return result


def _codes(value: object, allowed: set[str]) -> list[str]:
    return list(dict.fromkeys(item for item in value if isinstance(item, str) and item in allowed)) if isinstance(value, (list, tuple)) else []


def _project_safety() -> dict[str, object]:
    return {"direct_investment_advice": False, "writes_formal_user_insight": False, "research_aid_only": True, "omits_local_path": True, "provider_error_detail_omitted": True}


# Strict internal packet validation ---------------------------------------

def _plain(value: object) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _valid_packet(packet: dict[str, object], symbol: str, market: str) -> bool:
    if set(packet) != _PACKET_KEYS or packet.get("schema") != "stock_valuation_packet.v1": return False
    try: plain = _plain(packet)
    except (TypeError, ValueError, json.JSONDecodeError): return False
    assert isinstance(plain, dict)
    input_data, stock = plain.get("input"), plain.get("stock")
    if not isinstance(input_data, dict) or set(input_data) != {"symbol", "market", "command", "created_at"}: return False
    if input_data != {"symbol": symbol, "market": market, "command": f"valuation {market}.{symbol}", "created_at": _timestamp(input_data.get("created_at"))}: return False
    if not isinstance(stock, dict) or _project_stock(stock, symbol, market) != stock: return False
    coverage = plain.get("source_coverage"); registry = _project_registry(coverage)
    if not isinstance(coverage, dict) or registry != coverage.get("source_registry"): return False
    registry_by_id = {str(item["id"]): item for item in registry}; facts = _project_facts(plain.get("facts"), registry_by_id)
    if facts != plain.get("facts"): return False
    assumptions = _project_assumptions(plain.get("assumptions"))
    if assumptions != plain.get("assumptions"): return False
    domain = _canonical_domain(stock, facts, registry, assumptions["user_confirmed_valuation_case"] is True, market)
    if plain.get("target_resolution") != _target_resolution(symbol, market, domain["currency"]): return False
    for key, expected in (("deterministic_calculations", domain["calculations"]), ("internal_frame_scores", domain["scores"]), ("market_implied_bridge", domain["bridge"]), ("selected_frames", domain["selected"])):
        if plain.get(key) != _plain(expected): return False
    selected = plain["selected_frames"]
    if not isinstance(selected, list) or not 1 <= len(selected) <= 3 or len(plain["internal_frame_scores"]) != 5: return False
    expected_coverage = _coverage(facts, registry, coverage)
    if coverage != _plain(expected_coverage): return False
    degraded = plain.get("degraded_state"); identity_codes = _codes(degraded.get("reason_codes") if isinstance(degraded, dict) else None, {"context_identity_mismatch", "snapshot_identity_mismatch"})
    reasons = _reason_codes(domain["gap_codes"], expected_coverage, stock, identity_codes)
    if degraded != {"degraded": bool(reasons), "reason_codes": reasons, "gap_codes": domain["gap_codes"]}: return False
    if plain.get("interpretation") != _interpretation(selected, domain["gap_codes"]) or plain.get("watch_items") != _watch_items(selected): return False
    return plain.get("safety") == {"direct_investment_advice": False, "writes_formal_user_insight": False, "research_aid_only": True}
