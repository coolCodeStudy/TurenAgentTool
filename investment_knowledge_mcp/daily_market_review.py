from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from typing import Any
from zoneinfo import ZoneInfo

from investment_knowledge_mcp import repository
from investment_knowledge_mcp.market_data.models import (
    BreadthSnapshot,
    FetchResult,
    HotIndustryCandidate,
    HotStockCandidate,
    IndexQuote,
    SessionState,
    TurnoverSnapshot,
    to_plain,
)
from investment_knowledge_mcp.market_data.providers.akshare_quote import AkShareQuoteProvider
from investment_knowledge_mcp.market_data.providers.base import EmptyMarketDataProvider, MarketDataProvider
from investment_knowledge_mcp.market_data.providers.fake import FakeMarketDataProvider
from investment_knowledge_mcp.market_data.providers.futu_quote import FutuQuoteProvider
from investment_knowledge_mcp.market_data.scoring import (
    classify_volume,
    rank_hot_industries,
    rank_hot_stocks,
    score_sentiment,
)
from investment_knowledge_mcp.market_data.session_calendar import DEFAULT_USER_TZ, resolve_review_sessions


DEFAULT_MARKETS = ["CN", "US", "HK"]


@dataclass(frozen=True)
class DailyMarketReviewResult:
    context: dict[str, Any]
    markdown: str
    saved_report: dict[str, Any] | None = None
    saved_review: dict[str, Any] | None = None


def build_daily_market_review(
    review_date: date | None = None,
    markets: list[str] | None = None,
    mode: str | None = None,
    force_refresh: bool = False,
    save: bool = True,
    providers: list[MarketDataProvider] | None = None,
) -> DailyMarketReviewResult:
    normalized_markets = normalize_markets(markets)
    requested_date = review_date or datetime.now(DEFAULT_USER_TZ).date()
    review_key = build_review_key(requested_date=requested_date, markets=normalized_markets, mode=mode or "auto")
    if save and not force_refresh:
        existing = repository.get_daily_market_review_by_key(review_key)
        if existing and existing.get("markdown") and existing.get("structured_payload"):
            context = existing["structured_payload"]
            markdown = str(existing["markdown"])
            return DailyMarketReviewResult(context=context, markdown=markdown, saved_review=existing)

    context = build_daily_market_review_context(
        review_date=requested_date,
        markets=normalized_markets,
        mode=mode,
        force_refresh=force_refresh,
        providers=providers,
    )
    markdown = render_daily_market_review_markdown(context)
    saved_report = None
    saved_review = None
    if save:
        saved_report = save_daily_market_review_report(context=context, markdown=markdown)
        saved_review = save_daily_market_review_payload(context=context, saved_report=saved_report)
    return DailyMarketReviewResult(context=context, markdown=markdown, saved_report=saved_report, saved_review=saved_review)


def build_daily_market_review_context(
    review_date: date | None = None,
    markets: list[str] | None = None,
    mode: str | None = None,
    force_refresh: bool = False,
    providers: list[MarketDataProvider] | None = None,
) -> dict[str, Any]:
    requested_date = review_date or datetime.now(DEFAULT_USER_TZ).date()
    normalized_markets = normalize_markets(markets)
    provider_chain = providers or get_default_providers()
    review_dt = datetime.combine(requested_date, datetime.now(DEFAULT_USER_TZ).time(), tzinfo=DEFAULT_USER_TZ)
    sessions = resolve_review_sessions(review_dt=review_dt, mode=mode, markets=normalized_markets)

    market_payloads: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    warnings: list[str] = []
    all_hot_stocks: list[dict[str, Any]] = []
    all_hot_industries: list[dict[str, Any]] = []

    for market in normalized_markets:
        session = sessions[market]
        indexes_result = _fetch_domain(provider_chain, "index_quotes", market, session)
        turnover_result = _fetch_domain(provider_chain, "market_turnover", market, session)
        breadth_result = _fetch_domain(provider_chain, "breadth", market, session)
        hot_stocks_result = _fetch_domain(provider_chain, "hot_stocks", market, session, limit=5)
        hot_industries_result = _fetch_domain(provider_chain, "hot_industries", market, session, limit=5)

        domain_results = {
            "index_quotes": indexes_result,
            "market_turnover": turnover_result,
            "breadth": breadth_result,
            "hot_stocks": hot_stocks_result,
            "hot_industries": hot_industries_result,
        }
        coverage = _market_coverage(domain_results)
        volume = classify_volume(_data_or_none(turnover_result), turnover_result.status)
        sentiment = score_sentiment(
            indexes=_data_or_empty(indexes_result),
            breadth=_data_or_none(breadth_result),
            volume_state=volume["state"],
            coverage_status=coverage["status"],
        )
        ranked_stocks = rank_hot_stocks(_data_or_empty(hot_stocks_result))
        ranked_industries = rank_hot_industries(_data_or_empty(hot_industries_result))
        all_hot_stocks.extend(ranked_stocks)
        all_hot_industries.extend(ranked_industries)
        diagnostics[market] = {name: result.diagnostics() for name, result in domain_results.items()}
        market_warnings = [warning for result in domain_results.values() for warning in result.warnings]
        warnings.extend(f"{market}: {warning}" for warning in market_warnings)

        market_payloads[market] = {
            "session": to_plain(session),
            "sentiment": sentiment,
            "volume": volume,
            "indexes": to_plain(_data_or_empty(indexes_result)),
            "breadth": to_plain(_data_or_none(breadth_result)),
            "hot_stocks": ranked_stocks,
            "hot_industries": ranked_industries,
            "coverage": coverage,
            "warnings": market_warnings,
        }

    source_coverage = {market: payload["coverage"] for market, payload in market_payloads.items()}
    context = {
        "request": {
            "requested_date": requested_date.isoformat(),
            "markets": normalized_markets,
            "mode": mode or "auto",
            "timezone": str(DEFAULT_USER_TZ),
            "force_refresh": force_refresh,
            "review_key": build_review_key(requested_date=requested_date, markets=normalized_markets, mode=mode or "auto"),
        },
        "sessions": {market: to_plain(session) for market, session in sessions.items()},
        "session_label": _session_label(list(sessions.values())),
        "executive_snapshot": _build_executive_snapshot(market_payloads),
        "center_of_gravity": _build_center_of_gravity(market_payloads),
        "markets": market_payloads,
        "theme_persistence": _build_theme_persistence(requested_date=requested_date, current_industries=all_hot_industries),
        "portfolio_relevance": _build_portfolio_relevance(all_hot_stocks, all_hot_industries),
        "source_diagnostics": diagnostics,
        "source_coverage": source_coverage,
        "warnings": warnings,
        "generated_at": datetime.now(DEFAULT_USER_TZ).isoformat(),
    }
    return context


def render_daily_market_review_markdown(context: dict[str, Any]) -> str:
    lines = [
        f"# Daily Market Review: {context.get('session_label') or context['request']['requested_date']}",
        "",
        "## 1. Executive Snapshot",
    ]
    snapshot = context.get("executive_snapshot") or {}
    lines.extend(
        [
            f"- Market mood: {snapshot.get('market_mood', 'data_insufficient')}",
            f"- Volume state: {snapshot.get('volume_state', 'data_insufficient')}",
            f"- Dominant focus: {snapshot.get('dominant_focus', 'data insufficient')}",
            f"- Strongest market: {snapshot.get('strongest_market', 'unavailable')}",
            f"- Weakest market: {snapshot.get('weakest_market', 'unavailable')}",
            f"- Confidence: {snapshot.get('confidence', 'low')}",
            f"- Next verification: {snapshot.get('next_verification', 'Check provider coverage and source freshness.')}",
            "",
            "## 2. Cross-Market Center Of Gravity",
        ]
    )
    cog = context.get("center_of_gravity") or {}
    lines.extend(
        [
            f"- Main focus: {cog.get('main_focus', 'data insufficient')}",
            f"- Confirming evidence: {cog.get('confirming_evidence', 'unavailable')}",
            f"- Diverging evidence: {cog.get('diverging_evidence', 'unavailable')}",
            f"- Volume confirmation: {cog.get('volume_confirmation', 'unavailable')}",
            f"- Portfolio relevance: {cog.get('portfolio_relevance', 'unavailable')}",
            f"- Next verification: {cog.get('next_verification', 'Check missing data domains.')}",
        ]
    )

    section_names = [("CN", "A-Share Market"), ("US", "U.S. Market"), ("HK", "Hong Kong Market")]
    for number, (market, title) in enumerate(section_names, start=3):
        payload = (context.get("markets") or {}).get(market)
        lines.extend(["", f"## {number}. {title}"])
        if not payload:
            lines.append("- Market not requested.")
            continue
        lines.extend(_render_market_section(market, payload))

    lines.extend(["", "## 6. Theme Persistence And Rotation"])
    persistence = context.get("theme_persistence") or {}
    lines.extend(
        [
            f"- Persistent themes: {_join_or_note(persistence.get('persistent_themes'), 'not enough history')}",
            f"- New themes: {_join_or_note(persistence.get('new_themes'), 'not enough history')}",
            f"- Fading themes: {_join_or_note(persistence.get('fading_themes'), 'not enough history')}",
            f"- Crowding signal: {persistence.get('crowding_signal', 'not enough history')}",
        ]
    )
    lines.extend(["", "## 7. Portfolio/Watchlist Relevance"])
    relevance = context.get("portfolio_relevance") or {}
    lines.extend(
        [
            f"- Portfolio overlap: {_join_or_note(relevance.get('portfolio_overlap'), 'unavailable')}",
            f"- Theme overlap: {_join_or_note(relevance.get('theme_overlap'), 'unavailable')}",
            f"- Watchlist overlap: {_join_or_note(relevance.get('watchlist_overlap'), 'unavailable')}",
            f"- Knowledge overlap: {_join_or_note(relevance.get('knowledge_overlap'), 'unavailable')}",
        ]
    )
    lines.extend(["", "## 8. Data Coverage And Caveats"])
    lines.extend(_render_coverage_table(context.get("source_diagnostics") or {}))
    warnings = context.get("warnings") or []
    if warnings:
        lines.append("")
        lines.extend(f"- {warning}" for warning in warnings[:10])
    lines.append("")
    lines.append("Safety note: this review is read-only market context and does not provide buy, sell, hold, stop-loss, or target-price instructions.")
    return "\n".join(lines)


def render_daily_market_review_json(context: dict[str, Any], markdown: str) -> str:
    payload = dict(context)
    payload["markdown"] = markdown
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def save_daily_market_review_report(context: dict[str, Any], markdown: str) -> dict[str, Any]:
    session_dates = [session["session_date"] for session in (context.get("sessions") or {}).values()]
    period_start = min(session_dates) if session_dates else context["request"]["requested_date"]
    period_end = max(session_dates) if session_dates else context["request"]["requested_date"]
    return repository.upsert_review_report(
        report_key=context["request"]["review_key"],
        report_date=context["request"]["requested_date"],
        report_type="daily_market",
        period_start=period_start,
        period_end=period_end,
        summary=markdown,
        portfolio_snapshot=context.get("portfolio_relevance") or {},
        risks=[],
        opportunities=_all_ranked_items(context, "hot_stocks")[:10],
        new_knowledge_candidates=[],
        source_status=context.get("source_diagnostics") or {},
        highlights=[context.get("executive_snapshot") or {}],
        story=context.get("center_of_gravity") or {},
    )


def save_daily_market_review_payload(context: dict[str, Any], saved_report: dict[str, Any]) -> dict[str, Any]:
    snapshots = []
    hot_stocks = []
    hot_industries = []
    for market, payload in (context.get("markets") or {}).items():
        session = payload.get("session") or {}
        snapshots.append(
            {
                "market": market,
                "session_date": session.get("session_date"),
                "run_mode": session.get("run_mode"),
                "mood": (payload.get("sentiment") or {}).get("label"),
                "sentiment_score": (payload.get("sentiment") or {}).get("score"),
                "volume_state": (payload.get("volume") or {}).get("state"),
                "confidence": (payload.get("sentiment") or {}).get("confidence"),
                "snapshot": payload,
                "source_status": payload.get("coverage") or {},
            }
        )
        hot_stocks.extend(payload.get("hot_stocks") or [])
        hot_industries.extend(payload.get("hot_industries") or [])
    return repository.upsert_daily_market_review(
        review_key=context["request"]["review_key"],
        report_id=saved_report.get("id"),
        requested_date=context["request"]["requested_date"],
        session_label=context.get("session_label") or context["request"]["requested_date"],
        markets=context["request"]["markets"],
        run_mode=context["request"]["mode"],
        generated_at=context["generated_at"],
        source_coverage=context.get("source_coverage") or {},
        structured_payload=context,
        market_snapshots=snapshots,
        hot_stocks=hot_stocks,
        hot_industries=hot_industries,
    )


def get_latest_daily_market_review(markets: list[str] | None = None) -> dict[str, Any] | None:
    rows = repository.list_daily_market_reviews(limit=20)
    normalized = normalize_markets(markets) if markets else None
    for row in rows:
        if normalized is None or row.get("markets") == normalized:
            return row
    return None


def get_daily_market_review_by_date(review_date: date, markets: list[str] | None = None, mode: str = "auto") -> dict[str, Any] | None:
    return repository.get_daily_market_review_by_key(build_review_key(review_date, normalize_markets(markets), mode))


def normalize_markets(markets: list[str] | None) -> list[str]:
    if not markets:
        return list(DEFAULT_MARKETS)
    valid = []
    for item in markets:
        market = item.strip().upper()
        if market in {"CN", "US", "HK"} and market not in valid:
            valid.append(market)
    return valid or list(DEFAULT_MARKETS)


def build_review_key(requested_date: date, markets: list[str], mode: str) -> str:
    market_key = ",".join(sorted(normalize_markets(markets)))
    return f"daily_market:{requested_date.isoformat()}:{market_key}:{mode or 'auto'}"


def get_default_providers() -> list[MarketDataProvider]:
    if os.getenv("DAILY_MARKET_REVIEW_PROVIDER", "").lower() == "fake":
        return [FakeMarketDataProvider()]
    return [FutuQuoteProvider(), AkShareQuoteProvider(), EmptyMarketDataProvider()]


def _fetch_domain(
    providers: list[MarketDataProvider],
    domain: str,
    market: str,
    session: SessionState,
    limit: int | None = None,
) -> FetchResult:
    for provider in providers:
        method = getattr(provider, f"get_{domain}")
        result = method(market, session, limit) if limit is not None else method(market, session)
        if result.status in {"ok", "partial"} and result.data:
            return result
    return result


def _market_coverage(results: dict[str, FetchResult]) -> dict[str, Any]:
    statuses = {name: result.status for name, result in results.items()}
    useful = sum(1 for result in results.values() if result.status in {"ok", "partial"} and result.data)
    if useful == len(results):
        status = "complete"
    elif useful >= 2:
        status = "partial_coverage"
    elif useful >= 1:
        status = "partial_coverage"
    elif any(result.status == "failed" for result in results.values()):
        status = "failed"
    else:
        status = "not_configured"
    return {"status": status, "domains": statuses}


def _build_executive_snapshot(markets: dict[str, Any]) -> dict[str, Any]:
    ranked = sorted(
        (
            (market, (payload.get("sentiment") or {}).get("score"))
            for market, payload in markets.items()
            if (payload.get("sentiment") or {}).get("score") is not None
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    strongest = ranked[0][0] if ranked else "unavailable"
    weakest = ranked[-1][0] if ranked else "unavailable"
    themes = _top_themes(markets)
    coverage = [payload.get("coverage", {}).get("status") for payload in markets.values()]
    confidence = "medium" if any(status == "complete" for status in coverage) else "low"
    return {
        "market_mood": _combined_mood(markets),
        "volume_state": _combined_volume(markets),
        "dominant_focus": themes[0] if themes else "data insufficient",
        "strongest_market": strongest,
        "weakest_market": weakest,
        "confidence": confidence,
        "next_verification": "Verify provider coverage for any market marked partial, failed, or not_configured.",
    }


def _build_center_of_gravity(markets: dict[str, Any]) -> dict[str, Any]:
    themes = _top_themes(markets)
    useful_markets = [market for market, payload in markets.items() if payload.get("coverage", {}).get("status") in {"complete", "partial_coverage"}]
    main_focus = themes[0] if themes else "data insufficient"
    evidence = []
    for market in useful_markets[:3]:
        payload = markets[market]
        mood = (payload.get("sentiment") or {}).get("label")
        volume = (payload.get("volume") or {}).get("state")
        evidence.append(f"{market} mood {mood}, volume {volume}")
    return {
        "main_focus": main_focus,
        "confirming_evidence": "; ".join(evidence) if evidence else "Only diagnostics are available.",
        "diverging_evidence": "Cross-market divergence is unavailable until at least two markets have useful coverage." if len(useful_markets) < 2 else "No major divergence detected from available deterministic scores.",
        "volume_confirmation": _combined_volume(markets),
        "portfolio_relevance": "See Portfolio/Watchlist Relevance section.",
        "next_verification": "Check hot-stock catalyst evidence and turnover freshness before relying on the narrative.",
    }


def _build_theme_persistence(requested_date: date, current_industries: list[dict[str, Any]]) -> dict[str, Any]:
    previous = repository.list_daily_market_reviews(limit=5)
    if len(previous) < 2:
        return {
            "persistent_themes": [],
            "new_themes": [item.get("theme_label") or item.get("industry") for item in current_industries[:5]],
            "fading_themes": [],
            "crowding_signal": "not enough history",
        }
    prior_themes: set[str] = set()
    for review in previous:
        payload = review.get("structured_payload") or {}
        for market_payload in (payload.get("markets") or {}).values():
            for industry in market_payload.get("hot_industries") or []:
                prior_themes.add(str(industry.get("theme_label") or industry.get("industry")))
    current = [str(item.get("theme_label") or item.get("industry")) for item in current_industries[:10]]
    return {
        "persistent_themes": [theme for theme in current if theme in prior_themes],
        "new_themes": [theme for theme in current if theme not in prior_themes],
        "fading_themes": sorted(prior_themes.difference(current))[:5],
        "crowding_signal": _crowding_signal(current_industries),
    }


def _build_portfolio_relevance(hot_stocks: list[dict[str, Any]], hot_industries: list[dict[str, Any]]) -> dict[str, Any]:
    overlaps = [item["symbol"] for item in hot_stocks if item.get("user_relevance") not in {None, "unavailable"}]
    return {
        "portfolio_overlap": overlaps,
        "theme_overlap": sorted({item.get("theme") for item in hot_stocks if item.get("theme") and item.get("theme") != "unknown"})[:5],
        "watchlist_overlap": [],
        "knowledge_overlap": sorted({item.get("theme_label") or item.get("industry") for item in hot_industries if item.get("theme_label") or item.get("industry")})[:5],
    }


def _render_market_section(market: str, payload: dict[str, Any]) -> list[str]:
    sentiment = payload.get("sentiment") or {}
    volume = payload.get("volume") or {}
    session = payload.get("session") or {}
    lines = [
        f"- Session: {session.get('label', market)}",
        f"- Sentiment: {sentiment.get('label', 'data_insufficient')} (score: {sentiment.get('score', 'n/a')}, confidence: {sentiment.get('confidence', 'low')})",
        f"- Volume: {volume.get('state', 'data_insufficient')} ({volume.get('explanation', 'unavailable')})",
        "",
        "| Rank | Stock | Move | Volume heat | Catalyst | Theme | Why hot | User relevance | Confidence |",
        "|---|---|---:|---:|---|---|---|---|---|",
    ]
    stocks = payload.get("hot_stocks") or []
    if stocks:
        for item in stocks:
            lines.append(
                f"| {item['rank']} | {item['symbol']} {item.get('name') or ''} | {_fmt_pct(item.get('move_pct'))} | {_fmt_x(item.get('volume_heat'))} | {item.get('catalyst', 'unknown')} | {item.get('theme', 'unknown')} | {item.get('why_hot', '')} | {item.get('user_relevance', 'unavailable')} | {item.get('confidence', 'low')} |"
            )
    else:
        lines.append("| - | unavailable | - | - | unknown | unknown | Hot-stock data unavailable. | unavailable | data_insufficient |")
    lines.extend(["", "| Rank | Industry/theme | Performance | Volume heat | Representative stocks | Catalyst | Why it matters | Confidence |", "|---|---|---:|---:|---|---|---|---|"])
    industries = payload.get("hot_industries") or []
    if industries:
        for item in industries:
            lines.append(
                f"| {item['rank']} | {item.get('theme_label') or item.get('industry')} | {_fmt_pct(item.get('performance_pct'))} | {_fmt_x(item.get('volume_heat'))} | {', '.join(item.get('representative_stocks') or [])} | {item.get('catalyst', 'unknown')} | {item.get('why_it_matters', '')} | {item.get('confidence', 'low')} |"
            )
    else:
        lines.append("| - | unavailable | - | - | - | unknown | Industry/theme data unavailable. | data_insufficient |")
    return lines


def _render_coverage_table(diagnostics: dict[str, Any]) -> list[str]:
    lines = ["| Market | Provider | Domain | Status | Fetched At | Notes |", "|---|---|---|---|---|---|"]
    for market, domains in diagnostics.items():
        for domain, item in domains.items():
            lines.append(
                f"| {market} | {item.get('provider', 'unknown')} | {domain} | {item.get('status', 'missing')} | {item.get('fetched_at', '')} | {'; '.join(item.get('warnings') or [])} |"
            )
    return lines


def _data_or_empty(result: FetchResult) -> list:
    return result.data if isinstance(result.data, list) else []


def _data_or_none(result: FetchResult):
    return result.data


def _all_ranked_items(context: dict[str, Any], field: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for payload in (context.get("markets") or {}).values():
        items.extend(payload.get(field) or [])
    return sorted(items, key=lambda item: item.get("score") or 0, reverse=True)


def _session_label(sessions: list[SessionState]) -> str:
    labels = [session.label for session in sessions]
    return "; ".join(labels)


def _top_themes(markets: dict[str, Any]) -> list[str]:
    themes: dict[str, int] = {}
    for payload in markets.values():
        for item in payload.get("hot_industries") or []:
            theme = item.get("theme_label") or item.get("industry")
            if theme:
                themes[theme] = themes.get(theme, 0) + 1
        for item in payload.get("hot_stocks") or []:
            theme = item.get("theme")
            if theme and theme != "unknown":
                themes[theme] = themes.get(theme, 0) + 1
    return [theme for theme, _ in sorted(themes.items(), key=lambda pair: pair[1], reverse=True)]


def _combined_mood(markets: dict[str, Any]) -> str:
    labels = [(payload.get("sentiment") or {}).get("label") for payload in markets.values()]
    if all(label == "data_insufficient" for label in labels):
        return "data_insufficient"
    if any(label == "risk_off" for label in labels):
        return "mixed"
    if any(label == "risk_on_but_narrow" for label in labels):
        return "narrow_theme"
    if any(label == "strong_risk_on" for label in labels):
        return "risk_on"
    return "mixed"


def _combined_volume(markets: dict[str, Any]) -> str:
    states = [(payload.get("volume") or {}).get("state") for payload in markets.values()]
    for candidate in ["expanding", "projected_high", "contracting", "projected_low", "normal"]:
        if candidate in states:
            return candidate
    return "data_insufficient"


def _crowding_signal(items: list[dict[str, Any]]) -> str:
    if not items:
        return "not enough history"
    top_theme = items[0].get("theme_label") or items[0].get("industry")
    concentration = sum(1 for item in items[:5] if (item.get("theme_label") or item.get("industry")) == top_theme)
    return "narrow concentration" if concentration >= 3 else "not obvious"


def _join_or_note(items, note: str) -> str:
    cleaned = [str(item) for item in (items or []) if item]
    return ", ".join(cleaned) if cleaned else note


def _fmt_pct(value) -> str:
    return "-" if value is None else f"{float(value):.2f}%"


def _fmt_x(value) -> str:
    return "-" if value is None else f"{float(value):.2f}x"
