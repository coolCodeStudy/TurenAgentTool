from __future__ import annotations

from statistics import mean
from typing import Any

from investment_knowledge_mcp.market_data.models import (
    BreadthSnapshot,
    HotIndustryCandidate,
    HotStockCandidate,
    IndexQuote,
    TurnoverSnapshot,
)


def classify_volume(turnover: TurnoverSnapshot | None, status: str) -> dict[str, Any]:
    if turnover is None or status not in {"ok", "partial"}:
        return {
            "state": "data_insufficient",
            "relative_to_20d": None,
            "confidence": "unavailable",
            "explanation": "Turnover data is unavailable from configured providers.",
        }
    actual = turnover.projected_turnover or turnover.actual_turnover
    baseline = turnover.average_20d or turnover.average_5d or turnover.average_60d
    if not actual or not baseline:
        return {
            "state": "data_insufficient",
            "relative_to_20d": None,
            "confidence": turnover.projection_confidence,
            "explanation": "Turnover baseline is unavailable, so volume confirmation is limited.",
        }
    ratio = actual / baseline
    if turnover.projected_turnover is not None and ratio >= 1.2:
        state = "projected_high"
    elif turnover.projected_turnover is not None and ratio <= 0.8:
        state = "projected_low"
    elif ratio >= 1.15:
        state = "expanding"
    elif ratio <= 0.85:
        state = "contracting"
    else:
        state = "normal"
    return {
        "state": state,
        "relative_to_20d": ratio,
        "confidence": turnover.projection_confidence,
        "explanation": f"Turnover is {ratio:.2f}x the selected rolling baseline.",
    }


def score_sentiment(
    indexes: list[IndexQuote],
    breadth: BreadthSnapshot | None,
    volume_state: str,
    coverage_status: str,
) -> dict[str, Any]:
    if coverage_status in {"failed", "not_configured"} or not indexes:
        return {"score": None, "label": "data_insufficient", "confidence": "low"}
    changes = [item.change_pct for item in indexes if item.change_pct is not None]
    index_component = mean(changes) if changes else 0.0
    breadth_component = 0.0
    if breadth and breadth.advancers is not None and breadth.decliners is not None:
        total = breadth.advancers + breadth.decliners
        if total > 0:
            breadth_component = (breadth.advancers - breadth.decliners) / total * 2
    volume_component = {
        "expanding": 1.0,
        "projected_high": 0.7,
        "normal": 0.0,
        "contracting": -0.8,
        "projected_low": -0.6,
    }.get(volume_state, -0.3)
    score = index_component + breadth_component + volume_component
    if score >= 2.0 and volume_state in {"expanding", "projected_high"}:
        label = "strong_risk_on"
    elif score >= 0.5:
        label = "risk_on_but_narrow" if breadth_component < 0.2 else "strong_risk_on"
    elif score <= -1.0:
        label = "risk_off"
    elif volume_state in {"contracting", "projected_low"}:
        label = "liquidity_weak"
    else:
        label = "mixed_rotation"
    confidence = "high" if coverage_status == "complete" else ("medium" if coverage_status == "partial_coverage" else "low")
    return {"score": round(score, 3), "label": label, "confidence": confidence}


def rank_hot_stocks(candidates: list[HotStockCandidate], limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(candidates, key=_stock_score, reverse=True)[:limit]
    return [
        {
            "rank": index,
            "symbol": item.symbol,
            "name": item.name,
            "market": item.market,
            "move_pct": item.move_pct,
            "volume_heat": item.volume_heat,
            "catalyst": item.catalyst or "unknown",
            "theme": item.theme or "unknown",
            "why_hot": _stock_reason(item),
            "user_relevance": item.user_relevance,
            "confidence": "medium" if item.catalyst else "low",
            "score": round(_stock_score(item), 3),
            "source": item.source,
        }
        for index, item in enumerate(ranked, start=1)
    ]


def rank_hot_industries(candidates: list[HotIndustryCandidate], limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(candidates, key=_industry_score, reverse=True)[:limit]
    return [
        {
            "rank": index,
            "industry": item.industry,
            "market": item.market,
            "performance_pct": item.performance_pct,
            "volume_heat": item.volume_heat,
            "representative_stocks": item.representative_stocks[:3],
            "catalyst": item.catalyst or "unknown",
            "theme_label": item.theme_label or item.industry,
            "why_it_matters": _industry_reason(item),
            "confidence": "medium" if item.catalyst else "low",
            "score": round(_industry_score(item), 3),
            "source": item.source,
        }
        for index, item in enumerate(ranked, start=1)
    ]


def _stock_score(item: HotStockCandidate) -> float:
    return (
        0.35 * _num(item.relative_move if item.relative_move is not None else item.move_pct)
        + 0.25 * _num(item.volume_heat)
        + 0.15 * (1.0 if item.catalyst else 0.0)
        + 0.15 * (1.0 if item.theme else 0.0)
        + 0.10 * (1.0 if item.user_relevance != "unavailable" else 0.0)
    )


def _industry_score(item: HotIndustryCandidate) -> float:
    return (
        0.30 * _num(item.performance_pct)
        + 0.25 * _num(item.volume_heat)
        + 0.20 * _num(item.breadth)
        + 0.15 * min(len(item.representative_stocks), 3)
        + 0.10 * (1.0 if item.catalyst else 0.0)
    )


def _num(value: float | None) -> float:
    return float(value or 0.0)


def _stock_reason(item: HotStockCandidate) -> str:
    parts = []
    if item.move_pct is not None:
        parts.append(f"moved {item.move_pct:.2f}%")
    if item.volume_heat is not None:
        parts.append(f"volume heat {item.volume_heat:.2f}x")
    if item.theme:
        parts.append(f"theme {item.theme}")
    if item.catalyst:
        parts.append(f"market discussion centered on {item.catalyst}")
    return "; ".join(parts) if parts else "Data is insufficient to explain the move."


def _industry_reason(item: HotIndustryCandidate) -> str:
    parts = []
    if item.performance_pct is not None:
        parts.append(f"sector performance {item.performance_pct:.2f}%")
    if item.volume_heat is not None:
        parts.append(f"turnover heat {item.volume_heat:.2f}x")
    if item.representative_stocks:
        parts.append("leaders " + ", ".join(item.representative_stocks[:3]))
    return "; ".join(parts) if parts else "Data is insufficient to explain industry heat."
