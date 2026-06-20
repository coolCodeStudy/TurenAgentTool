from __future__ import annotations

import json
import os
from typing import Any

import httpx

from investment_knowledge_mcp.model_providers.openai_provider import extract_response_text


RESPONSES_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.2"


def generate_decision_synthesis(
    context_pack: dict[str, Any],
    deterministic_ticket: dict[str, Any],
) -> dict[str, Any] | None:
    if os.getenv("OPENAI_ANALYSIS_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a cautious investment decision-support synthesizer. "
                    "Use only the provided structured context. Do not invent prices, filings, news, or data. "
                    "You cannot recommend more aggressively than the deterministic recommendation cap."
                ),
            },
            {"role": "user", "content": build_decision_synthesis_prompt(context_pack, deterministic_ticket)},
        ],
        "max_output_tokens": 1800,
    }
    with httpx.Client(timeout=120) as client:
        response = client.post(
            RESPONSES_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()

    parsed = _parse_json_object(extract_response_text(response.json()).strip())
    if not parsed:
        return None
    return validate_decision_synthesis(parsed, deterministic_ticket)


def build_decision_synthesis_prompt(context_pack: dict[str, Any], deterministic_ticket: dict[str, Any]) -> str:
    compact_context = {
        "stock": context_pack.get("stock"),
        "user_constraints": context_pack.get("user_constraints"),
        "portfolio_exposure": context_pack.get("portfolio_exposure"),
        "stock_card": context_pack.get("stock_card"),
        "valuation_pack": context_pack.get("valuation_pack"),
        "technical_pack": context_pack.get("technical_pack"),
        "chip_event_pack": context_pack.get("chip_event_pack"),
        "sector_pack": context_pack.get("sector_pack"),
        "market_pack": context_pack.get("market_pack"),
        "freshness_report": context_pack.get("freshness_report"),
        "open_questions": context_pack.get("open_questions"),
        "evidence_index": (context_pack.get("evidence_index") or [])[:25],
    }
    deterministic = {
        key: deterministic_ticket.get(key)
        for key in (
            "recommendation",
            "composite_score",
            "confidence",
            "freshness_status",
            "suggested_position",
            "score_components",
            "gates",
        )
    }
    return (
        "Return a JSON object only. Schema:\n"
        "{\n"
        '  "recommendation": "avoid|watch|wait|starter|normal_position|high_conviction_candidate|review_existing_holding|trim|reduce",\n'
        '  "confidence": "low|medium|high",\n'
        '  "reasons": ["3-5 concise reasons"],\n'
        '  "veto_conditions": [],\n'
        '  "entry_conditions": [],\n'
        '  "add_conditions": [],\n'
        '  "reduce_conditions": [],\n'
        '  "next_review_trigger": {"type": "...", "trigger": "..."},\n'
        '  "unresolved_questions": [],\n'
        '  "inferences": [{"type": "...", "content": "...", "confidence": 0.5}],\n'
        '  "candidate_insights": [{"target_type": "stock|sector|portfolio|strategy", "insight": "...", "reason": "..."}]\n'
        "}\n\n"
        "Do not exceed deterministic gates. If data is missing or stale, say so.\n\n"
        "DETERMINISTIC_TICKET:\n"
        f"{json.dumps(deterministic, ensure_ascii=False, default=str)}\n\n"
        "CONTEXT_PACK:\n"
        f"{json.dumps(compact_context, ensure_ascii=False, default=str)}"
    )


def validate_decision_synthesis(value: dict[str, Any], deterministic_ticket: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "avoid",
        "watch",
        "wait",
        "starter",
        "normal_position",
        "high_conviction_candidate",
        "review_existing_holding",
        "trim",
        "reduce",
    }
    if value.get("recommendation") not in allowed:
        value["recommendation"] = deterministic_ticket.get("recommendation")
    if value.get("confidence") not in {"low", "medium", "high"}:
        value["confidence"] = deterministic_ticket.get("confidence")
    for key in (
        "reasons",
        "veto_conditions",
        "entry_conditions",
        "add_conditions",
        "reduce_conditions",
        "unresolved_questions",
        "inferences",
        "candidate_insights",
    ):
        if not isinstance(value.get(key), list):
            value[key] = []
    if not isinstance(value.get("next_review_trigger"), dict):
        value["next_review_trigger"] = deterministic_ticket.get("next_review_trigger") or {}
    return value


def merge_synthesis(
    deterministic_ticket: dict[str, Any],
    synthesis: dict[str, Any] | None,
) -> dict[str, Any]:
    if not synthesis:
        return deterministic_ticket

    merged = {**deterministic_ticket}
    for key in (
        "reasons",
        "veto_conditions",
        "entry_conditions",
        "add_conditions",
        "reduce_conditions",
        "unresolved_questions",
    ):
        if synthesis.get(key):
            merged[key] = synthesis[key]
    if synthesis.get("next_review_trigger"):
        merged["next_review_trigger"] = synthesis["next_review_trigger"]
    merged["recommendation"] = deterministic_ticket["recommendation"]
    merged["confidence"] = _min_confidence(deterministic_ticket["confidence"], synthesis.get("confidence"))
    merged["model_name"] = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    merged["model_inferences"] = synthesis.get("inferences") or []
    merged["candidate_insight_proposals"] = synthesis.get("candidate_insights") or []
    return merged


def _parse_json_object(text: str) -> dict[str, Any] | None:
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _min_confidence(left: str, right: str | None) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    if right not in order:
        return left
    return left if order[left] <= order[right] else right
